# Hardware evidence

確認日2026-10-06。本体ラベル写真は **Archer BE5000 JP/1.0**、有線接続した実機UIは **Archer BE5000 v1.0 / 1.2.0 Build 20260420 rel.13798(4A50)**。JP V1公開最新版と一致した。serial / MAC / WPS PIN / SSID / passwordと写真は公開しない。

| 項目 | 確認結果 | 証拠の範囲 |
| --- | --- | --- |
| SoC | FW対象はMediaTek MT7987A / MT7987 | 最新kernel FIT内のJP DTSとGPL製品設定が一致。実機刻印未確認 |
| Wi-Fi | vendor mt_wifi / mtk_hwifi、MT7992系列driver設定 | 最新rootfsにMT7992 MCU FW、MT7991/MT7976 BE5040 EEPROM候補。silicon/RF部品型番は未確認。generic driver名を実チップ型番としない |
| switch | GPLの対象DTSにmediatek,mt7531 | 実機認識・部品suffix未確認 |
| flash | 最新partition設定は128MiB、SPI NAND / NMBM構成 | 最新rootfs partition-table、kernel DTS、GPL。部品型番・実機bad block未確認 |
| RAM | FWのDTS設定は256MiB、開始0x40000000 | 最新FITのJP/US/KR DTSとGPLで一致。実機meminfo・部品型番未確認 |
| bootloader | GPLはMediaTek ATF + first/second U-Boot | 配布UBI volume0にsecond-boot uImage。現用boot partition・U-Boot version・console認証未確認 |
| UART | DTS ttyS0 / 115200n1、rootfs inittabもttyS0 login | 基板の位置・電圧・pinout・ログイン可否未確認 |
| JTAG | 未確認 | GPL ATF ENABLE_JTAG未設定。実機fuse/基板pinの証拠にはしない |
| Secure Boot | 未確認 | GPL CONFIG_MTK_SECURE_BOOT / ENABLE_SBC未設定。現用BL2・fuse・boot chain未確認 |

上記はFW / sourceに記録された対象構成。個体を開封して実装部品を確認した主張ではない。同名Xiaomi BE5000、Deco BE5000、他のArcherを互換性の根拠にしない。
[GPL path / SHA256](evidence/gpl-selected.json)、[最新rootfs path / SHA256](evidence/rootfs-selected.json)、[FIT内DTSの選択properties](evidence/fit-summary.json)。
