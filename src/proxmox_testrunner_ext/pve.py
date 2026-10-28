"""The `pve` region: Proxmox VE on the rig's nodes, as a system under test (testrunner WP
testrunner-state-validation §10 B5b; D9).

One validator, and the one reading it judges from (a `look` fixture: one reading per act of
judging, shared by every value asked in that look):

    none       no expected node has Proxmox VE
    installed  every expected node has PVE with pve-cluster active, and none is in a cluster
    founded    the founder is quorate in a cluster whose member list is the founder alone; every
               other expected node is installed
    clustered  every expected node is quorate, in ONE cluster whose member list is exactly the
               expected nodes, all online

"Expected" is the CURRENT set: testrunner's declared data `expected` when the runner config
declares it (it follows addnode/rmnode), else the catalogue's cluster nodes. The founder is the
catalogue's `founder` role.

**Cannot tell, never a guess.** PVE is observable only while the rig's VMs run: when the `vms`
region (testrunner.ext.rig) is `halted` or `partial` — a node stopped, missing, or not answering
TCP/22 — every value answers "cannot tell". When it is `absent` (no VM exists at all), `none`
holds: no VM, no PVE — an observation, not a guess (user 2026-10-28). A node that answers TCP/22 but refuses the harness key
(stopping pve-cluster removes root's authorized_keys, which live in pmxcfs: measured 2026-10-28)
is also "cannot tell".

Declare `validate: {python: pve}` on a variable whose values are exactly those names, and
`observe: {order: [clustered, founded, installed, none]}` to read it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import shlex
from typing import Any

from testrunner import fixture, validator
from testrunner.proc import Proc

log = logging.getLogger(__name__)

VALUES = ("none", "installed", "founded", "clustered")

# what a node says about itself, one key=value per line (printf, never echo)
FACTS = r"""
if command -v pveversion >/dev/null 2>&1; then printf 'pve=%s\n' "$(pveversion 2>/dev/null | head -1)"; else printf 'pve=\n'; fi
printf 'pvecluster=%s\n' "$(systemctl is-active pve-cluster 2>/dev/null)"
if [ -f /etc/pve/corosync.conf ]; then printf 'corosync=yes\n'; else printf 'corosync=no\n'; fi
printf 'quorate=%s\n' "$(pvecm status 2>/dev/null | awk -F: '/^Quorate/{gsub(/ /,"",$2); print $2}')"
printf 'members=%s\n' "$(tr -d '\n' < /etc/pve/.members 2>/dev/null)"
"""

def classify(facts: dict) -> str:
    """One node's reading from its facts: none, half-installed, installed, unreadable-members,
    unquorate or clustered."""
    if not facts.get("pve"):
        return "none"
    if facts.get("pvecluster") != "active":
        return "half-installed"
    if facts.get("corosync") != "yes":
        return "installed"
    if "nodelist" not in facts:
        return "unreadable-members"
    if facts.get("quorate") != "Yes":
        return "unquorate"
    return "clustered"


def parse_facts(text: str) -> dict:
    facts = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    try:
        members = json.loads(facts.get("members") or "{}")
        facts["nodelist"] = {n: v.get("online") for n, v in (members.get("nodelist") or {}).items()}
    except ValueError:
        pass
    return facts


async def read_node(rig: Any, proc: Proc, node: str) -> tuple[str, dict]:
    ip = str(rig.catalogue.machines[node]["ip"])
    # the agent guards literally on the ssh line (a rig's agent-guard reads the call site, and an
    # option behind a variable cannot be checked there): never consult or write the operator's agent
    cmd = (f"ssh -i {shlex.quote(str(rig.key))} -o IdentityAgent=none -o AddKeysToAgent=no -o IdentitiesOnly=yes "
           f"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR -o ConnectTimeout=10 "
           f"root@{ip} {shlex.quote(FACTS)}")
    r = await proc.run(cmd, echo=False, timeout=60, ask_operator=False)
    if r.returncode != 0:
        return "unreachable", {"rc": r.returncode, "out": r.text.strip()[-200:]}
    facts = parse_facts(r.text)
    return classify(facts), facts


async def read_pve(rig: Any, expected: list[str], can_look: bool, why_not: str, no_vms: bool = False) -> dict:
    """One reading of PVE on the expected nodes — or none at all, when the VMs do not run. When no
    VM exists at all (vms=absent), that IS the reading: no PVE exists (user 2026-10-28)."""
    if no_vms:
        return {"expected": expected, "nodes": {}, "blind": "", "no_vms": True}
    if not can_look:
        return {"expected": expected, "nodes": {}, "blind": why_not}
    proc = Proc(rig.root, rig.logs)
    got = await asyncio.gather(*(read_node(rig, proc, n) for n in expected))
    nodes = dict(zip(expected, got))
    log.info("pve: %s", {n: rd for n, (rd, _) in nodes.items()})
    return {"expected": expected, "nodes": nodes, "blind": "", "founder": rig.catalogue.role1("founder")}


def judge(reading: dict, value: str) -> tuple[bool | None, str]:
    """pve=value on this reading: True, False, or None (cannot tell)."""
    if reading.get("no_vms"):
        # no VM exists at all: no PVE exists either — an observation (the VMs read absent), not a guess
        return value == "none", "no VM of the rig exists, so no Proxmox VE does"
    if reading["blind"]:
        return None, f"cannot look at PVE: {reading['blind']}"
    exp = reading["expected"]
    nodes = reading["nodes"]
    readings = {n: nodes[n][0] for n in exp}
    why = ", ".join(f"{n}={rd}" for n, rd in readings.items()) or "no expected node"
    if any(rd == "unreachable" for rd in readings.values()):
        return None, f"{why} (a node answers TCP/22 but not the harness: cannot tell)"
    if not exp:
        return False, why
    if value == "none":
        return all(rd == "none" for rd in readings.values()), why
    if value == "installed":
        return all(rd == "installed" for rd in readings.values()), why
    if value == "founded":
        f = reading["founder"]
        if readings.get(f) != "clustered":
            return False, f"{why}; the founder {f} is not in a cluster"
        members = set(nodes[f][1].get("nodelist", {}))
        if members != {f}:
            return False, f"{why}; the founder's member list {sorted(members)} is not [{f}]"
        others = {n: rd for n, rd in readings.items() if n != f and rd != "installed"}
        return (not others), (f"{why}; not installed: {others}" if others else why)
    if value == "clustered":
        if any(rd != "clustered" for rd in readings.values()):
            return False, why
        lists = [set(nodes[n][1].get("nodelist", {})) for n in exp]
        if any(m != set(exp) for m in lists):
            return False, f"{why}; member lists {[sorted(m) for m in lists]} != the expected {sorted(exp)}"
        offline = sorted({m for n in exp for m, on in nodes[n][1].get("nodelist", {}).items() if not on})
        return (not offline), (f"{why}; offline members {offline}" if offline else why)
    return False, f"{value!r} is not a pve value ({', '.join(VALUES)})"


@fixture(scope="look")
async def pve_reading(rig, machines_reading):
    """PVE on the expected nodes, read ONCE per look — only when the vms region is `running`
    (machines_reading is testrunner.ext.rig's, from the same look)."""
    from testrunner.ext.rig.regions import judge_vms
    absent, _ = judge_vms(machines_reading, "absent")
    running, why = judge_vms(machines_reading, "running")
    return await read_pve(rig, machines_reading["expected"], running, "" if running else f"the VMs do not all run ({why})",
                          no_vms=absent)


@validator("pve")
def pve(claim, pve_reading):
    """pve=<value>, judged on this look's reading (module docstring)."""
    return judge(pve_reading, claim.value)
