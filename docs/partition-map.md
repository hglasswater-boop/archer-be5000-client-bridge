# Partition map

最新JP FWの/etc/partition_config/partition-tableで30 records、flash=128Mを確認。SHA256: 6c03f37cdf8d0f2aa14ce87e8c507e2ecc21b9c6c165dcfe269d51ed96fe8c34。
GPLのJP/base設定・US設定とも下記6つのphysical extentは一致。US設定は29 recordsでmetadata record差分あり。実機/proc/mtdとの照合未実施。書込みアドレスとして使用しない。

| physical領域 | flash offset | size | 注意 |
| --- | --- | --- | --- |
| boot | 0x00000000 | 0x00200000 (2MiB) | first boot chain。配布UBI volume0とは別 |
| u-boot-env | 0x00200000 | 0x00100000 (1MiB) | 最新JP設定のenv名はuboot-env_be260_jp_v1.bin |
| ubi0 | 0x00300000 | 0x03200000 (50MiB) | primary候補 |
| ubi1 | 0x03500000 | 0x03200000 (50MiB) | second image候補。実機fallback動作未確認 |
| userconfig | 0x06700000 | 0x00800000 (8MiB) | 個体設定/calibration等virtual recordsの保護対象 |
| tp_data | 0x06f00000 | 0x00800000 (8MiB) | vendor data、保護対象 |

終端0x07700000と128MiBとの差9MiBの用途はこの表だけで確定しない。offset0のcertificate / default-mac / pin / device-id / support-list / profile / user-config / radio等はvirtual metadataで、独立したphysical領域ではない。

## 配布container

復号解析copyの **0x1258** から375 PEBのUBI。PEB=0x20000、VID offset=0x800、data offset=0x1000。EC/VID/static dataの全CRCを検証。368 static data PEB + 2 layout PEB + 5 erased reserve PEBを認識。container offsetとflash offsetは異なる。

| static ID | GPL上の用途 | 最新配布物 | size |
| --- | --- | --- | --- |
| 0 | uboot | second-boot uImage magic | 1,105,760 bytes |
| 1 | kernel | ARM64 FIT / Linux5.4.281、JP/US/KR DTS | 3,848,807 bytes |
| 2 | rootfs | SquashFS4.0 / XZ | 41,558,016 bytes、bytes_used=41,555,948 |

[Volume SHA256](evidence/ubi-volumes.json)。NAND full backupではない。boot/env/calibrationを含むraw recovery imageを生成したとは扱わない。
