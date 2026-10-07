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


## First-pass static result

The comparison workflow successfully downloaded all four official JP V1 release packages, verified and decoded each package with the same documented verification path, reconstructed UBI static volumes with CRC validation, and read the selected SquashFS files.

### Core findings

- `/etc/init.d/wifix` is byte-identical in 1.0.2, 1.0.3, 1.1.0 and 1.2.0.
- `/etc/meshd_cfg_be260v1_jp.json` is byte-identical in all four releases and contains the same two `apclii0` occurrences in every release.
- `/usr/bin/wifix` exists in every release. All four versions retain the same counted STA-related markers: `ApCliEnable`=2, `wpa_cli`=7, `disconnect`=6, `tp_mesh_enable`=1.
- `/usr/bin/meshd` exists in every release. All four versions retain `reconnect`=3. 1.0.2/1.0.3 contain `wpa_cli`=16 and `disconnect`=13; 1.1.0/1.2.0 contain `wpa_cli`=19 and `disconnect`=14.
- `wifix_profile.ini` changes between 1.0.2 and 1.0.3, then is byte-identical from 1.0.3 through 1.2.0.
- generic `meshd_cfg.json` changes at the 1.0.3 -> 1.1.0 boundary, while the JP-specific `meshd_cfg_be260v1_jp.json` does not.

### Interpretation boundary

This rules out the simple hypothesis that current 1.2.0 removed the STA/APCLI implementation wholesale. It does not prove that 1.0.2 could associate as a standalone non-EasyMesh STA, and it does not rule out a runtime gating or reconnect-condition change inside the changed `wifix` / `meshd` binaries.

Next comparison should focus on:
1. the exact `wifix_profile.ini` 1.0.2 -> 1.0.3 diff;
2. the generic `meshd_cfg.json` 1.0.3 -> 1.1.0 diff;
3. filtered STA/APCLI-related string-table differences in `wifix` and `meshd`;
4. if needed, function-level diff around STA initialization and reconnect paths.
