# Firmware STA/APCLI version comparison

Issue: #2

## Purpose

Verify whether Archer BE5000 JP firmware changed the internal STA/APCLI path between the first public firmware and the current firmware. The comparison must distinguish:

- implementation removed;
- implementation still present but disabled by profile/feature state;
- association/reconnect trigger changed;
- EasyMesh became a required control-plane dependency;
- only configuration/API compatibility remained while runtime association stopped.

Do not infer a working STA from strings or configuration fields alone.

## Firmware set

Compare all public JP V1 releases currently listed by TP-Link:

| Version | Build | Published |
| --- | --- | --- |
| 1.0.2 | 20250603 | 2025-08-22 |
| 1.0.3 | 20250825 | 2025-10-17 |
| 1.1.0 | 20260108 | 2026-02-02 |
| 1.2.0 | 20260420 | 2026-06-12 |

1.1.0 is the first release whose official notes state that downgrade is unsupported. This is a comparison boundary, not evidence that STA behavior changed there.

## Files and markers

For each decoded firmware, compare at minimum:

- /usr/bin/wifix
- /usr/bin/meshd
- /lib/wifi/wifix_profile.ini
- /etc/init.d/wifix
- /etc/meshd_cfg.json
- /etc/meshd_cfg_be260v1_jp.json

Record SHA-256 and size. For binary files, record occurrence counts of these byte markers without treating presence as reachability proof:

- apclii0
- ApCliEnable
- wpa_cli
- reconnect
- disconnect
- MACRepeater
- tp_mesh_enable

## Decision rules

- If a core binary is byte-identical across versions, behavior changes cannot be attributed to code changes in that binary.
- If markers disappear, inspect the changed binary before claiming feature removal.
- If the runtime binaries remain but profiles/configuration change, prioritize a disabled/configuration-path hypothesis.
- If wifix/meshd changes at one version boundary, inspect the STA initialization and reconnect call path around that boundary.
- No old firmware is flashed. Static comparison only until downgrade/recovery safety is independently established.

## Test-first implementation

Add synthetic tests for marker counting, deterministic hashing, version ordering, and missing-file handling before adding the comparison implementation.

## Output

The comparison produces JSON only from decoded local analysis copies. Firmware, decoded images, rootfs contents, credentials, device-specific values, and vendor archives are not committed.
