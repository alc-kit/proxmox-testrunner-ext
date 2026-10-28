# proxmox-testrunner-ext

Proxmox VE as a **system under test**, for [testrunner](https://github.com/alc-kit/testrunner).
This repository holds what testrunner needs to know about Proxmox VE, and nothing generic.

## What lives where

| concern | where | why |
|---|---|---|
| the runner, the state machine, validators, observers, the `machine:` notation | [testrunner](https://github.com/alc-kit/testrunner) | generic: knows nothing about Proxmox |
| VMs: do the rig's machines exist and run (`vms` region) | testrunner `ext.rig` | generic to any libvirt/Vagrant rig |
| the generic part of support machines (they exist and answer) | testrunner `ext.rig` | generic |
| **Proxmox VE: installed, founded, clustered, quorum, membership** (`pve` region) | **here** | Proxmox is the system under test, not the framework |

A rig (for example a lab or a gate) vendors this repository as a subtree next to testrunner and
imports it as `proxmox_testrunner_ext`.

## Status

Empty. The first content is the `pve` region's probes. Each probe reads a node once and judges
every value from that one reading. Values are judged against the rig's *current* expected nodes
(testrunner's declared data), never a fixed list. A node that cannot be looked at answers
"cannot tell", never a guess.

## License

Apache License 2.0; see [LICENSE](LICENSE).
