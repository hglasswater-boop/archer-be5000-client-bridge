# Boot / recovery / rollback

## 状態

BE5000対象個体で確立済みのbrick recoveryはない。改造FW書込みは禁止。
[TP-Link公式FAQ 1482](https://www.tp-link.com/jp/support/faq/1482/)は一般的な復旧例を示すが、BE5000のrevision固有の復旧成功を証明しない。
factory resetは設定初期化であり、破損したbootloader/rootfsの復旧やFW downgradeではない。

| 手段 | 状態 | 成功条件 |
| --- | --- | --- |
| TFTP | 未確認 | 対象bootloader、要求ファイル名/IP、適切なimage、成功実績 |
| recovery Web UI | 未確認 | 対象revisionの入口、署名/版制限、純正FW復元実績 |
| serial / bootloader shell | 未確認 | UART位置/電圧、consoleアクセス、読取りbackup、復元手順 |
| dual image / fallback | 未確認 | 実機partition、切替条件、fallback実績 |
| SPI/programmer等 | 未確認 | flash種類/電圧、full backup、calibration保持、復元実績 |

## 先行確認

ラベルとFW文字列、合法的に取得できるboot log、同revisionのメーカー確認を収集する。
UARTを接続する前に電圧・pinoutを測定し、VCCを接続しない。安易なTFTP名やボタン手順を他機種から転用しない。
現用家庭内ネットワークでrecovery試験をしない。予備機・隔離LAN・安定電源で純正FW復元を確認する。

## rollback

runtime変更: 変更前の設定とdaemon状態を保存し、検証済みの有線管理経路から復元する。再起動で復元できることも事前確認する。
永続設定: 同FW版の設定backupを保存し、復元条件を確認する。
FW: 1.1.0以降に公式downgrade不可の記載あり。旧版への復帰をrollbackとして計画しない。
bootloader/calibration/factory変更は本PoC範囲外。
