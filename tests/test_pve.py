"""The pve region (testrunner WP §10 B5b). Every value both ways, from the cases measured on a lab rig
(WP §8.1–8.2): a founder-only cluster, a stale member list, an unquorate node, an unreachable node,
a stub install — and judged against the CURRENT expected nodes."""
import asyncio

import pytest

from proxmox_testrunner_ext import pve
from proxmox_testrunner_ext.pve import VALUES, classify, judge, parse_facts


def cl(members, online=1):
    return ("clustered", {"nodelist": {m: online for m in members}})


def reading(nodes, expected=("a", "b"), founder="a", blind=""):
    return {"expected": list(expected), "nodes": nodes, "founder": founder, "blind": blind}


CASES = [
    ("none", {"a": ("none", {}), "b": ("none", {})}, "none"),
    ("installed", {"a": ("installed", {}), "b": ("installed", {})}, "installed"),
    ("founded", {"a": cl("a"), "b": ("installed", {})}, "founded"),
    ("clustered", {"a": cl("ab"), "b": cl("ab")}, "clustered"),
    ("half-installed", {"a": ("installed", {}), "b": ("half-installed", {})}, None),
    ("a stub install", {"a": ("half-installed", {}), "b": ("half-installed", {})}, None),
    ("the wrong node founded", {"a": ("installed", {}), "b": cl("b")}, None),
    ("founder lists b, b only installed (stale)", {"a": cl("ab"), "b": ("installed", {})}, None),
    ("a foreign cluster", {"a": cl("ab"), "b": cl("bz")}, None),
    ("a stale member list", {"a": cl("abc"), "b": cl("abc")}, None),
    ("an offline member", {"a": cl("ab", 0), "b": cl("ab", 0)}, None),
    ("one node unquorate", {"a": cl("ab"), "b": ("unquorate", {})}, None),
]


@pytest.mark.parametrize("name,nodes,holds", CASES, ids=[c[0] for c in CASES])
def test_at_most_one_value_holds(name, nodes, holds):
    held = [v for v in VALUES if judge(reading(nodes), v)[0]]
    assert held == ([holds] if holds else []), (name, held)


def test_clustered_is_judged_against_the_current_expected_nodes():
    # after rmnode a, addnode c: the cluster b, c is whole for expected [b, c] ...
    nodes = {"b": cl("bc"), "c": cl("bc")}
    assert judge(reading(nodes, expected=["b", "c"], founder="b"), "clustered")[0]
    # ... and not for the catalogue's fixed [a, b] (the defect D9 found)
    assert not judge(reading({"a": ("none", {}), "b": cl("bc")}, expected=["a", "b"]), "clustered")[0]


def test_an_unreachable_node_cannot_tell():
    r = reading({"a": cl("ab"), "b": ("unreachable", {"rc": 255})})
    assert all(judge(r, v)[0] is None for v in VALUES)


def test_no_vms_means_no_pve():
    # vms=absent (no machine exists): pve=none HOLDS, every other value does not — destroy's
    # claim pve -> none can be confirmed (user 2026-10-28)
    r = {"expected": ["a", "b"], "nodes": {}, "blind": "", "no_vms": True}
    assert [v for v in VALUES if judge(r, v)[0]] == ["none"]
    assert all(judge(r, v)[0] is False for v in VALUES if v != "none")


def test_read_pve_with_no_vms_contacts_nothing(monkeypatch):
    async def run(self, cmd, **kw):
        raise AssertionError("looked at PVE although no VM exists")
    monkeypatch.setattr(pve.Proc, "run", run)
    r = asyncio.run(pve.read_pve(FakeRig(), ["a", "b"], False, "absent", no_vms=True))
    assert judge(r, "none")[0] is True


def test_blind_when_the_vms_do_not_run():
    r = reading({}, blind="n2=shutoff")
    assert all(judge(r, v)[0] is None for v in VALUES)
    assert "n2=shutoff" in judge(r, "clustered")[1]


@pytest.mark.parametrize("facts,want", [
    ({"pve": ""}, "none"),
    ({"pve": "pve-manager/9.0", "pvecluster": "inactive"}, "half-installed"),
    ({"pve": "pve-manager/9.0", "pvecluster": "active", "corosync": "no"}, "installed"),
    ({"pve": "pve-manager/9.0", "pvecluster": "active", "corosync": "yes"}, "unreadable-members"),
    ({"pve": "pve-manager/9.0", "pvecluster": "active", "corosync": "yes", "nodelist": {}, "quorate": ""}, "unquorate"),
    ({"pve": "pve-manager/9.0", "pvecluster": "active", "corosync": "yes", "nodelist": {}, "quorate": "Yes"},
     "clustered"),
])
def test_classify(facts, want):
    assert classify(facts) == want


def test_parse_facts_reads_the_member_list():
    text = ('pve=pve-manager/9.0\npvecluster=active\ncorosync=yes\nquorate=Yes\n'
            'members={"nodename":"a","nodelist":{"a":{"online":1},"b":{"online":0}}}\n')
    f = parse_facts(text)
    assert f["nodelist"] == {"a": 1, "b": 0} and classify(f) == "clustered"
    assert "nodelist" not in parse_facts("members={not json\n")


class Result:
    def __init__(self, rc, text):
        self.returncode, self.text = rc, text


class FakeRig:
    root = logs = key = "/nonexistent"

    class catalogue:
        machines = {"a": {"ip": "192.0.2.1"}, "b": {"ip": "192.0.2.2"}}

        @staticmethod
        def role1(name):
            return "a"


def test_read_pve_reads_each_expected_node_once_over_ssh(monkeypatch):
    calls = []

    async def run(self, cmd, **kw):
        calls.append(cmd)
        node = "a" if "192.0.2.1" in cmd else "b"
        members = '{"nodelist":{"a":{"online":1}}}' if node == "a" else ""
        return Result(0, f"pve=pve-manager/9.0\npvecluster=active\ncorosync={'yes' if node == 'a' else 'no'}\n"
                         f"quorate={'Yes' if node == 'a' else ''}\nmembers={members}\n")
    monkeypatch.setattr(pve.Proc, "run", run)
    r = asyncio.run(pve.read_pve(FakeRig(), ["a", "b"], True, ""))
    assert len(calls) == 2 and all("IdentityAgent=none" in c and "root@192.0.2." in c for c in calls)
    assert [v for v in VALUES if judge(r, v)[0]] == ["founded"]


def test_read_pve_does_not_look_when_the_vms_do_not_run(monkeypatch):
    async def run(self, cmd, **kw):
        raise AssertionError("looked at PVE although the VMs do not run")
    monkeypatch.setattr(pve.Proc, "run", run)
    r = asyncio.run(pve.read_pve(FakeRig(), ["a", "b"], False, "b=shutoff"))
    assert judge(r, "clustered")[0] is None
