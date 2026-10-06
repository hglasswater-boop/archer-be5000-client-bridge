# Boot / recovery / rollback

BE5000 JP/1.0で確立済みbrick recoveryはない。改造FW書込みの停止条件が成立している。
[公式FAQ1482](https://www.tp-link.com/jp/support/faq/1482/)は一般的な復旧例で、BE5000固有の成功を証明しない。factory resetは設定初期化であり、破損FW復旧やdowngradeとは別。

| 手段 | 見つかった証拠 | まだ必要な確認 |
| --- | --- | --- |
| TFTP | GPL U-Boot CONFIG_CMD_TFTPBOOT有効 | 個体の起動入口、要求名/IP、適切なimage、純正復元成功。通常tftpbootコマンドと自動recoveryを混同しない |
| recovery Web UI | GPLにgeneric mtk_httpd source | 対象revisionでの入口とcallsite、image制限、純正復元実績 |
| serial / bootloader shell | DTS ttyS0 115200、inittab login | 電圧/pinout、shell認証、full backup、復元成功 |
| dual image / fallback | 最新partitionにubi0 / ubi1、GPL flash_type=nand_double_image | 実機active slot、切替条件、boot env、fallback成功。2領域があるだけでは復旧保証にならない |
| programmer | SPI NAND / NMBM設定 | NAND部品/電圧、ECC/OOB/bad-block扱い、full backup、calibration保持、復元実績。SPI NOR用手順を転用しない |

隔離LAN・予備機・安定電源でメーカー資料または検証可能な同revision手順を確立する。UART接続前に電圧とpinoutを測定し、VCCは接続しない。未知のボタン/TFTP filename/IPを他機種から転用しない。
公開up-all / 復号copy / static volumeはraw NAND全体のbackupではない。変更imageの署名受理も未確認。

## Rollbackの手順と成立条件

1. Runtime候補を実施する前に、現行同FW設定backup、daemon/bridge/interface/firewall状態を保存する。認証済み有線管理経路と再起動で純正状態へ戻ることを先に確認する。
2. 検証済みの一時変更だけを隔離LANで実施し、問題時は保存状態へ復元する。復元timer等を使う場合もその経路を先に試験する。現時点では具体driverコマンドを作成していない。
3. Startup永続化はruntime合格後のみ。変更を削除して再起動、同版設定を復元できることを確認する。RAMFS変更は永続overlayと同じではない。
4. Firmwareは公式1.1.0以降にdowngrade不可の記載あり。旧版への復帰を前提にしない。同版純正FW復元・slot fallbackも実証まで未確立扱い。

bootloader / env / calibration / factory変更はPoC範囲外。この資料は未検証のbrick復旧手順を完成済みとして提供していない。
