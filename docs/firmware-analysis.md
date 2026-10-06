# Firmware analysis

確認日2026-10-06〜07。対象はラベル/UIで照合済みJP/1.0。現在FW **1.2.0 Build 20260420 rel.13798(4A50)**。

## 取得物

[JP V1公式ページ](https://www.tp-link.com/jp/support/download/archer-be5000/v1/)の最新版1.2.0 Build20260420、公開日2026-06-12を取得。
[公式ZIP](https://static.tp-link.com/upload/firmware/2026/202606/20260612/Archer%20BE5000_V1_260420.zip) SHA256: 667ddb11a57bed203dc2950d48831af8362dc706d36a4976c35e3c851a568196。
内部BIN 49,156,696 bytes、SHA256: 2636aa5eb9fbb91c5840d9f16c25b7bf00e99640c1c626ff3c081957603dd0be。
BIN名はbe260v1-be5000v1-be4600v1-us-up-all-ver1-2-0-P1[20260420-rel13798]_2048_sign_2026-04-20_03.50.58.bin。
名前のus表記だけで不適合とせず、復号support-listの **BE5000 / 1.0.0 / special_id=4A500000 (JP)** を照合した。

[US公式ページ](https://www.tp-link.com/us/support/download/archer-be5000/)が提供する[GPL archive](https://static.tp-link.com/upload/gpl-code/2026/202605/20260512/GPL_ArcherBE5000.tar.gz)も取得。
2,327,878,345 bytes、SHA256: 82c5cdeddb98dfcef43559eaf5fc24166395cd382827f644cb539cf3c3366fad。
全225,226 TAR member、宣言payload計4,251,079,179 bytesをstreamで一覧化。対象sourceだけを上限付きで読み、vendor codeは実行していない。
GPL build名be260v1にBE5000 US/JP/KR適応とmulti-DTBを含む。掲載地域/revisionやREADME名だけでJP最新buildと同一とはしない。

## Container / 署名 / 暗号

先頭4 bytesのbig-endian値はimage長と一致。offset20にfw-type:Cloud、RSA version byte0x112=2、署名0x130..0x230。
GPL uboot-7987/uboot/lib/nvrammanager/nm_fwup.cとrsaVerify.cの手順を独立toolで再現。署名領域をzeroにしたoffset20以降を、GPL PUBLICKEYBLOBのRSA2048-PSS/SHA256で検証する。署名格納はlittle endian。
**最新配布BINの署名検証に成功**。検証済みPSS saltからAES128-CBC key/IVを取得し、0x230以降のblock aligned payloadをcopy上で復号。vendor plaintext markerも一致。
復号copy SHA256: d0f5b1dd5ccab3ba8fda57b162d6edb5a3678f2f8ae8606d441f688a60a94c6a。
copyの変更後payloadに対して署名は無効。**絶対にflashしない**。復号成功は変更imageの署名生成や受理を意味しない。
rawでfilesystemが見えなかったが、復号後にUBI/FIT/SquashFSを確認した。rawのgzip magic3候補は実streamではなかった。

| 項目 | 確認結果 / 未確認範囲 |
| --- | --- |
| FW署名 | 最新配布物のRSA2048-PSS/SHA256を実検証済み |
| FW暗号化 | 最新配布物のAES128-CBC payloadを実復号済み |
| Web UI署名検証 | firmware.luaはLua5.1 bytecode。fmupへの参照とrsa2048_enableあり。署名判定までの完全なcall chain/error pathは未確認。改造imageを投入して試験していない |
| Bootloader検証 | GPL handle_fw_cloud → rsaVerify、nm_upgradeFirmwareのreject pathを確認。現用bootloaderの同一性・起動時kernel検証は未確認 |
| Secure Boot | 未確認。GPL無効設定だけでfuse offとしない |
| rollback protection | 公式1.1.0 release notesにdowngrade不可。実装場所・同版復元可否未確認 |
| rootfs verification | UBI CRCは全検証済み。CRCは暗号的認証ではない。FITにhash設定があるが強制検証範囲やdm-verity等未確認 |
| writable overlay | GPL kernel CONFIG_OVERLAY_FS未設定。最新preinitは/etc、/lib/wifi、/lib/firmware、/usr/lib/luaをRAMFSへ複製する処理を持つ。変更の永続性・実mount状態未確認。通常OpenWrt overlayを仮定しない |

## 最新rootfs / init / network

EC/VID/static payload CRCとlogical block連続性を検証して3 UBI volumeを復元。
SquashFS4.0 / XZ (compression ID4)、inodes4732、directory entries4731。dissect.squashfs1.12のread-only APIで一覧と対象fileを読んだ。hostへ一括展開せず、symlinkを作らず、本文はhash名でローカル保存。

- Kernel: ARM64 FITのdescriptionとmodule directoryはLinux5.4.281。JPのconfig-be260_jp_v1とUS/KR DTBを含む。
- Userspace: BusyBox型rcS / rc.common / UCI / ubus / netifdのvendor OpenWrt派生。openwrt_releaseの12.09-rc1表記は古いまま。最新kernelやupstream対応の証拠にしない。
- Init: inittab → rcS、ttyS0 login。wifix S15、network S25、hostapd/wpa_supplicant S26、tpbr S40、apsd S99。
- Wireless: mt_wifi / mt_wifi_cmn / mtk_hwifi modules、hostapd、wpa_supplicant、iw、iwpriv、mwctlを含む。実interface active状態・iw4addr対応は未確認。
- Mesh: easymesh-agent、easymesh-controller、meshd、apsd、wifix、ieee1905、libmesh_db_api、tpbr.ko、tpbrctlを確認。GPL SDK選択のmapd/wapp/fwddがその名前で最新rootfsに存在するとは限らない。
- LAN/VLAN: network_arch.shはswitch UCIからport/VLAN mappingを取得。既定networkのeth0 bridgeや旧platform comment / placeholder MACから実機設定を決めない。
- Writable data: userconfig/tp_data mount、UBIFS hooks、RAMFS copy hooksを含む。実機で全hookが成功した証拠や永続startup追加経路は未確認。

## Backhaul → wired LAN

最新JP easymesh_cfg_be260v1_jp.json / meshd_cfg_be260v1_jp.jsonは **apclii0 = 5GHz bSTA**。apsdのHC設定にも5GHz pathとして登録。APはrai0、backhaul AP候補rai2でSTAと別VAP。wifix_profile.iniのbridge名はbr-lan。
apsd initはmesh_enable=offでreturn。開始時tpbrctl attach br-lan、停止時detach。tpbr initもmesh offでskipする。
**EasyMesh停止とforwardingの独立性は未確立**。wifixとproprietary mesh daemonが制御するため、最終frameが4addr / MAC repeater / tunnelのどれかは断定できない。

GPL SDKはAPCLI_SUPPORT / APCLI_SUPPLICANT_SUPPORT / WDS / MWDS / MAC_REPEATER / PROXYARPが有効。STA_MODE未設定でもAPCLIが有効なのでSTAなしとは言えない。一般的なiw4addrが動くとも言えない。
最新mt7992.5040.b0/b1.datにはApCliEnableとMACRepeaterEnの項目がある。template既定値と稼働時設定を区別する。

## GPL / binary差分

GPL image.mkのSOFTWARE_VERSION既定値V1.0.3P1に対し、実配布は1.2.0P1。rootfs iplatform.configのhashもGPL版と異なる。
Kernel5.4.281、MT7987、MT7992系SDK、physical partition extentとJP/US/KR適応は整合する。
しかしGPL source treeで製品のmesh / wifix / apsd daemonの完全な対応sourceは確認できず、最新binaryの完全再現buildとは言えない。firmware.lua / wireless.luaはbytecodeでありstringsのAPI名だけで処理を確定しない。

## 実機UI / 管理経路

PCから直結して現在版を照合。選択可能な動作モードはrouter / APの2つ。ワイヤレス設定、5GHz詳細、追加設定とWDS検索(0結果)でSTA/WDSの公開入口を確認できなかった。
shared frontendにはClient/Repeater componentやWDS storeがあるが、実機で選択可能な機能とは同義でない。
22/23 TCPへの各2秒の接続確認はtimeout、80/443は応答。SSH未実装の証明ではない。rootfsにdropbearがあり、initはknock_functionsで既定アクセスを制限。認証済みshellは確立していない。

[再現手順](reproduce.md)、[raw](evidence/jp-v1-260420-inventory.json)、[decoded](evidence/jp-v1-260420-decoded-inventory.json)、[UBI](evidence/ubi-volumes.json)、[GPL](evidence/gpl-selected.json)、[rootfs](evidence/rootfs-selected.json)。vendor archive / decoded BIN / rootfs本文 / 個体情報はgit対象外。実機FW未変更。
