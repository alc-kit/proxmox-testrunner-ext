# proxmox-testrunner-ext

Proxmox VE as a **system under test**, for [testrunner](https://github.com/alc-kit/testrunner).
This repository holds what testrunner needs to know about Proxmox VE, and nothing generic.

## What lives where

| concern | where | why |
|---|---|---|
| the runner, the state machine, validators, observers, the `machine:` notation | [testrunner](https://github.com/alc-kit/testrunner) | generic: knows nothing about Proxmox |
| VMs: do the rig's machines exist and run (`vms` region) | testrunner `ext.rig` | generic to any libvirt/Vagrant rig |
| the generic part of support machines (they exist and answer) | testrunner `ext.rig` | generic |
| **Proxmox VE: installed, clustered, joined, quorum, membership** (`pve` region) | **here** | Proxmox is the system under test, not the framework |

A rig (for example a lab or a gate) vendors this repository as a subtree next to testrunner and
imports it as `proxmox_testrunner_ext`.

## The `pve` region

`proxmox_testrunner_ext.pve` provides one validator and the one reading it judges from:

| value | holds when |
|---|---|
| `none` | no expected node has Proxmox VE |
| `installed` | every expected node has PVE with pve-cluster active, and none is in a cluster |
| `clustered` | the founder is quorate and online in a cluster whose member list is the founder alone; every other expected node is installed |
| `clustered_m` | at least **two** expected nodes, every one quorate, in **one** cluster whose member list is exactly the expected nodes, all online |

- **A one-node cluster is as complete as any** (user 2026-10-28): `form` makes the cluster
  `clustered`, whatever the node count, and `join` makes it `clustered_m` (the nodes joined to the
  founder's). With one expected node `clustered_m` never holds, so at most one value holds on any
  reading. A rig's machine writes `installed --> clustered : form [passed]` and
  `clustered --> clustered_m : join [passed]`.

- **Expected** is the *current* set: testrunner's declared data `expected` when the runner
  config declares it (so it follows `addnode`/`rmnode`), else the catalogue's cluster nodes. The
  founder is the catalogue's `founder` role.
- **Cannot tell, never a guess.** PVE is observable only while testrunner's `vms` region is
  `running`. A node that answers TCP/22 but refuses the harness key also means "cannot tell"
  (stopping pve-cluster removes root's `authorized_keys`, which live in pmxcfs).
- Each look reads every expected node **once**, over SSH by the catalogue's IP, and judges every
  value from that reading.

In a rig's `testrunner.yml` (the rig vendors this repository as a subtree):

```yaml
modules: [actions/, proxmox-testrunner-ext/src/proxmox_testrunner_ext/pve.py]
pythonpath: [actions/, proxmox-testrunner-ext/src]
ext:
  rig: {...}                 # testrunner.ext.rig: the vms region this one depends on
states:
  pve:
    values: [none, installed, clustered, clustered_m]
    validate: {python: pve}
    observe: {order: [clustered_m, clustered, installed, none]}
```

## Tests

```sh
TESTRUNNER_SRC=../testrunner/src python3 -m pytest -q tests
```

testrunner is not on PyPI, so the tests import it from a checkout and refuse to run without one.
There is no CI here (user 2026-10-28): run the tests locally, against the testrunner the rigs
vendor.

## Content guard (optional, local)

`tools/content-guard` refuses private IPv4 addresses and internal host names. It can also
refuse a list of names, given from outside the repository (`CONTENT_GUARD_NAMES`, or
`~/.config/content-guard/names`). Nothing requires it: run it when you want it.

## License

Apache License 2.0; see [LICENSE](LICENSE).
