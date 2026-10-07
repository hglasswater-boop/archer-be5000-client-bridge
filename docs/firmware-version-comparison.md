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


## Focused diff result

A second successful comparison extracted only firmware-public configuration and STA/APCLI-related string-table differences.

### 1.0.2 -> 1.0.3: wifix profile

The only `wifix_profile.ini` change is addition of country-dependent TPC/thermal duty-control settings:

- `FEATURE_TPC_CTRL_BY_CNTRY=y`
- temperature thresholds for 2.4/5 GHz
- duty values for 2.4/5 GHz

No STA/APCLI enable/disable, supplicant, reconnect, bSTA, WDS, or MAC-repeater setting changed in this file.

### 1.0.3 -> 1.1.0: generic meshd config

The generic `meshd_cfg.json` keeps `scan_before_connect_enable=true` and the same bSTA interface assignments. The changes add:

- RSSI thresholds for 2.4/5/6 GHz;
- thread-pool thread count and stack size.

The JP-specific `meshd_cfg_be260v1_jp.json` remains byte-identical across all four releases.

### STA/APCLI-related binary strings

`wifix` has no filtered STA/APCLI string change between 1.0.2 -> 1.0.3 or 1.0.3 -> 1.1.0. Between 1.1.0 -> 1.2.0 it adds, rather than removes:

- `ApCliAuthMode=OWE`
- `ApCliAuthMode=WPA2PSKMIXWPA3PSK`
- `ApCliAuthMode=WPA3PSK`
- `ApCliEncrypType=AES`

The existing `ApCliEnable=0`, `ApCliEnable=1`, `ApCliBssid`, WPA/WPA2 auth modes, supplicant control interface, and `config_wds_setting` strings remain.

`meshd` has no filtered STA-related string change between 1.0.2 -> 1.0.3 or 1.1.0 -> 1.2.0. Between 1.0.3 -> 1.1.0 it adds:

- a disconnected-role transition log;
- `wpa_cli ... list_networks`;
- `wpa_cli ... set_network ... bssid <MAC>`;
- `wpa_cli ... set_network ... bssid any`.

Existing `disconnect`, `reconfigure`, `reconnect`, scan/status and EasyMesh supplicant commands remain.

## Current conclusion

The static evidence does **not** support either of these simple explanations:

1. "STA/APCLI existed only in old firmware and was removed from current firmware."
2. "A visible profile/config switch disabled STA in current firmware."

Current 1.2.0 retains the STA/APCLI control path and adds authentication/encryption support. The public JP bSTA mapping and wifix init script are unchanged from 1.0.2.

The remaining version-sensitive hypothesis is narrower: internal control flow, runtime state, or EasyMesh/reconnect gating inside changed binaries may differ even though the commands and configurations remain. A function-level comparison is required before attributing the live association failure to a firmware regression. Static presence also does not prove that 1.0.2 ever supported standalone non-EasyMesh association.


## Function-level analysis plan

The next pass compares executable control flow rather than string presence.

Targets in `wifix`:
- STA mode conversion / `init_vap`;
- `wpa_supplicant_setup_vif` and `wpa_supplicant_enable_vif`;
- `config_wds_setting`;
- VAP update / radio reload path.

Targets in `meshd`:
- platform STA connect callback;
- band-map reconnect path;
- disconnect/reconnect helper;
- scan-before-connect / BSSID-selection path.

For every release, record ELF architecture/build metadata, available function symbols, function start/size where symbols exist, and normalized AArch64 disassembly. Compare normalized instruction bodies across adjacent releases. Absolute addresses alone are not treated as behavior changes.

If target names are stripped, fall back to string-reference neighborhoods and call-site comparison; do not invent function identity from nearby strings alone.


## Deep control-flow result

The production `wifix` and `meshd` executables are stripped, so target function names are not available from their ELF symbol tables. Function identity below is based on exact string references, AArch64 call/control-flow neighborhoods, and the already-established current-firmware analysis. Absolute address shifts are not treated as behavior changes.

### Stable since 1.0.2: wpa_supplicant registration/disconnect

The `wifix` function that registers the STA with wpa_supplicant and ends by issuing `wpa_cli ... disconnect` has the same 153-instruction mnemonic sequence in all four JP releases.

Approximate function bounds:

| Version | Bounds | Instructions |
| --- | --- | ---: |
| 1.0.2 | 0x415ec0–0x416120 | 153 |
| 1.0.3 | 0x416154–0x4163b4 | 153 |
| 1.1.0 | 0x416958–0x416bb8 | 153 |
| 1.2.0 | 0x416a8c–0x416cec | 153 |

The sequence `interface_add -> scan_interval 30 -> disconnect` therefore predates 1.1/1.2 and is not a newly introduced current-firmware regression.

### Stable since 1.0.2: meshd reconnect helper

The small `meshd` helper that formats and executes `wpa_cli -p /var/run/wpa_supplicant -i %s reconnect` is 23 instructions in every release and has the same mnemonic/control-flow sequence. It still invokes `system()` and returns success independently of the shell command result.

The helper itself was not removed or materially rewritten.

### Stable since 1.0.2: band-map reconnect dispatcher

The `meshd` band-map reconnect routine is 54 instructions in every release and retains the same branch/call topology. The larger config structure in 1.1+ moves field offsets, but no reconnect-dispatch branch disappears.

### Stable core, extended in 1.2: APCLI driver enable

The `wifix` APCLI/WDS driver setup routine is 591 instructions in 1.0.2, 1.0.3 and 1.1.0. It expands to 839 instructions in 1.2.0 because of additional WPA3/OWE handling.

Critically, the final path that writes the SSID and then `ApCliEnable=1` has the same 45-instruction mnemonic sequence in every release. The current firmware did not remove the APCLI enable tail.

### Material change at 1.1.0: scan candidate selection before reconnect

The major version-sensitive change is upstream of the stable reconnect dispatcher.

In 1.0.2/1.0.3, the scan-selection block contains an explicit BSS matcher. It:
- uses band-specific RSSI thresholds;
- iterates scan BSS entries;
- compares SSID;
- records RSSI, TP IE presence and level;
- explicitly handles the "not match any BSS" and "select BSS" cases.

The old helper logs include `rssi_threshold=%d`, `match BSS...`, `not match any BSS` and `select BSS...`. Its scan-entry observations include candidates with TP IE absent / level zero; this is evidence of the old selector's input model, not proof of successful standalone association.

At the 1.1.0 boundary this block is replaced by a substantially smaller/different selection path. The 1.1/1.2 implementation:
- builds/uses a neighbor candidate structure;
- selects a `best_nbr`;
- evaluates TP IE support, level and node ID/controller-related state;
- then derives band-map reconnect actions.

The new logs include `match_count=%d` and `best_nbr: ... tpie_support=%d, level=%d, nodeid=...`. The old direct `rssi_threshold / match BSS / select BSS` corpus disappears.

Approximate combined selection/monitor block sizes:

| Version | Bounds | Instructions | reconnect calls |
| --- | --- | ---: | ---: |
| 1.0.2 | 0x417554–0x418400 | 940 | 3 |
| 1.0.3 | 0x4175b4–0x418460 | 940 | 3 |
| 1.1.0 | 0x419d54–0x41a6ac | 599 | 3 |
| 1.2.0 | 0x419dec–0x41a744 | 599 | 3 |

The reconnect helper and dispatcher remain; what changes is the decision path that selects a candidate and reaches those calls.

## Revised conclusion

The old-vs-current hypothesis is **partly supported, but not as feature removal**.

- STA/APCLI implementation was not removed in current firmware.
- The supplicant disconnect sequence was already present in 1.0.2.
- The APCLI `Enable=1` path and reconnect helper remain.
- A real behavioral boundary appears at **1.1.0** in `meshd` scan/candidate selection and reconnect gating.

This makes a 1.1-era control-plane change the strongest firmware-regression candidate currently identified for the observed standalone STA failure. Static analysis alone does not prove that 1.0.2/1.0.3 successfully associated to an ordinary non-EasyMesh AP, nor that the 1.1 change is the cause on the live unit. It does justify testing the legacy candidate-selection semantics against the current runtime before considering any downgrade.


## 1.1+ ordinary-AP path verification

A closer read of the 1.2.0 `meshd_match_select_bss` and `meshd_scan_match_monitor` control flow narrows the 1.1 regression hypothesis further.

- The scan matcher still compares the configured SSID and creates a neighbor candidate when TP-IE support is **absent**. The `tpie_support == 0` branch allocates a candidate record instead of discarding the BSS.
- In `meshd_scan_match_monitor`, `best_nbr->tpie_support == 0` has an explicit non-TP-IE branch.
- If the selected non-TP-IE candidate's band is not already present in `connect_band_bmap`, that branch calls the same band-map reconnect dispatcher used elsewhere.
- Current 1.2.0 field mapping is confirmed from its diagnostic output code: support_band_bmap=global+0x880, connect_band_bmap=+0x884, select_band_bmap=+0x888, scan_band_bmap=+0x88c.

Therefore the 1.1+ redesign does **not** simply require TP-Link/EasyMesh TP-IE and does not statically forbid an ordinary AP. The redesign remains behaviorally different, but TP-IE filtering alone cannot explain the live failure.

The next version comparison must include daemon startup/gating scripts. Since reconnect policy lives in `meshd`, compare `/etc/init.d/meshd`, `/etc/init.d/apsd`, and `/etc/init.d/tpbr` across releases to determine whether EasyMesh-off behavior changed.


## Daemon startup/gating comparison

The daemon init scripts were extracted from all four verified/decoded JP releases and compared byte-for-byte.

| Path | 1.0.2 -> 1.2.0 |
| --- | --- |
| `/etc/init.d/meshd` | byte-identical |
| `/etc/init.d/apsd` | byte-identical |
| `/etc/init.d/tpbr` | byte-identical |
| `/etc/init.d/wifix` | byte-identical |

The common `meshd` init script has no `meshd.meshd.enable` guard in `start()`; it simply launches `/usr/bin/meshd`. Its `START=50` line is commented out, so automatic boot ordering must not be inferred from rc.common alone.

The common `apsd` and `tpbr` init scripts explicitly read `meshd.meshd.enable` and return immediately when it is `off`. In addition, `apsd stop` executes `tpbrctl detach br-lan`.

All four `wifix` binaries also contain the same control strings:
- `ubus send meshd.wifi_reload_complete`
- `pidof meshd`
- `/etc/init.d/meshd stop`
- `/etc/init.d/meshd start`

This rules out a firmware-version regression in the daemon gating scripts. The EasyMesh-off data-plane problem is architectural and was already present in the first JP release: disabling Mesh also prevents the standard `apsd/tpbr` startup path, while `meshd` contains reconnect logic that can handle non-TP-IE candidates.

## Updated firmware-level conclusion

The static firmware evidence now supports the following:

1. Current 1.2.0 did not remove or globally disable STA/APCLI.
2. Ordinary non-TP-Link AP candidates are not statically rejected by 1.1+/1.2 `meshd`; a non-TP-IE candidate can reach the band reconnect dispatcher.
3. The 1.1.0 candidate-selection redesign is real, but TP-IE gating alone does not explain the current failure.
4. The Mesh-off gating of `apsd/tpbr` is identical from 1.0.2 through 1.2.0, so downgrading does not restore a separate legacy non-Mesh forwarding path.
5. Association and Ethernet forwarding must now be separated experimentally. A missing Ethernet DHCP OFFER can be explained by a detached/unused `tpbr` path even if the STA were associated; conversely the current public status APIs are not sufficient to prove association.

The next practical firmware question is no longer “which old version still has STA?” but “what is the smallest current-firmware runtime combination that keeps STA reconnect and LAN forwarding while removing EasyMesh control-plane behavior?”


## GPL driver follow-up: ApCliMeshRule

All four `wifix` binaries set `ApCliMeshRule=1` immediately before `ApCliSsid` and `ApCliEnable=1`. Because this is identical from 1.0.2 through 1.2.0 it is not a firmware-version regression, but its driver semantics may distinguish ordinary APCLI from a Mesh-specific data path.

Next step: scan the published GPL archive in streaming/read-only mode for the exact token `ApCliMeshRule` and nearby definitions/handlers. Do not extract the full archive and do not infer semantics from the command name alone.


### GPL exact-token result

A bounded full-stream search of the published GPL archive found **zero** regular-text members containing the exact token `ApCliMeshRule`.

This means the product binary's `iwpriv ... ApCliMeshRule=1` command cannot currently be mapped to a published GPL handler by name. Possible explanations include a product-only driver patch or a source branch not represented by the published GPL tree; no one explanation is assumed.

Continue from published driver tokens that are independently present in the firmware/GPL feature set: `ApCliEnable` and `MACRepeaterEn`. Their handlers/configuration should establish whether a non-EasyMesh APCLI forwarding mode exists independently of `tpbr`.


## Production Wi-Fi driver comparison

The published GPL does not contain the exact product command tokens `ApCliMeshRule` or `ApCliEnable` in regular text members, so it cannot establish the production command semantics by name.

Compare the actual production kernel module `/lib/modules/5.4.281/mt_wifi.ko` from each verified JP firmware. Record byte hash/size and the exact command markers `ApCliMeshRule`, `ApCliEnable`, `MACRepeaterEn`, and related APCLI tokens. This comparison takes precedence over GPL naming for the shipped behavior.


### Production mt_wifi first-pass result

The production `mt_wifi.ko` module is present in all four JP releases and changes by version:

| Version | Size | SHA-256 |
| --- | ---: | --- |
| 1.0.2 | 15,339,272 | a1b5106f5f1c79b2f4b3ee5fa678c4e13fa85e5c7ae55549027c0df3880d8007 |
| 1.0.3 | 15,339,272 | 979d5ad986b24b198c401ad2f81dcd8903157ba0aaf88ee1a51a850bca31db0a |
| 1.1.0 | 15,405,776 | 841e41125ad0db4d6c37b2290b55e82d5e705e0268169ba2f6a57791a0d32846 |
| 1.2.0 | 15,400,056 | dbc2528195c22bd61bc0856cb3e63a401b27dc44ce7d632fc97af53bf466da5b |

Every release contains four exact `ApCliEnable` markers. No release contains the exact `ApCliMeshRule` or `MACRepeaterEn` marker in this module.

This confirms that the userspace `wifix` command `ApCliMeshRule=1` is not a current-only addition and cannot be mapped to an exact string handler in the production `mt_wifi.ko`. Since the wifix command helper ignores command exit status and continues to SSID/`ApCliEnable=1`, a rejected MeshRule command alone does not prove association failure.

Next: extract the production driver's APCLI/WDS/repeater string corpus across releases to identify the actual supported private controls and whether a separate MAC-repeater forwarding control is exposed under another name.
