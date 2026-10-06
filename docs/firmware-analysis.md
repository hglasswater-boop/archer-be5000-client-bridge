# Firmware analysis

日付: 2026-10-06。資料作成を解析ツール実装より先に行う。

## 取得候補

- [JP V1公式ページ](https://www.tp-link.com/jp/support/download/archer-be5000/v1/)
- [US V1.60公式ページとGPL](https://www.tp-link.com/us/support/download/archer-be5000/)

JP V1の公開最新版は1.2.0 Build 20260420、公開日2026-06-12。実機revision・FW文字列との一致は未確認。
公式1.1.0の注意事項にダウングレード不可の記載。これは実装されたanti-rollbackの場所や方式を証明しない。
US公式ページのGPL_ArcherBE5000.tar.gzは参考ソース候補。JP実機との一致や1.2.0の完全な再現性は未確認。

## 解析手順

取得元・最終URL・サイズ・SHA256を記録し、ZIP/TAR一覧・header・埋め込みmagic・可読文字列をオフラインで調べる。
vendor code、build script、firmware内実行ファイルは実行しない。archiveを一括展開しない。
container offsetとflash offsetを混同しない。partition tableの候補は独立した構造証拠と照合する。
暗号化、署名、Secure Boot、rootfs検証は別項目。高エントロピーや読めないrootfsだけで暗号化・Secure Bootと断定しない。

## 確認待ち

container / partition / filesystem / kernel / userspace / init / network scripts / wireless / bridge / VLAN /
EasyMesh daemon / hostapd / wpa_supplicant / proprietary daemon / writable overlayはいずれも未確認。
Web UI署名検証、bootloader検証、rollback protection、encryption、rootfs verificationも未確認。
GPLとbinaryの差分は対象buildの対応確認後に評価する。

## 初回オフライン検査

JP公式ZIPを取得。内部BINは49,156,696 bytes、SHA256は`2636aa5eb9fbb91c5840d9f16c25b7bf00e99640c1c626ff3c081957603dd0be`。
内部ファイル名は`be260v1-be5000v1-be4600v1-us-up-all-ver1-2-0-P1[20260420-rel13798]_2048_sign_2026-04-20_03.50.58.bin`。
JP配布ZIP内の名称にusが含まれる事実を記録し、他地域配布物を代用しない。適合地域は配布ページ・support-list・対象個体の照合で確認する。
先頭4 bytesのbig-endian値はファイル長に一致、offset20に`fw-type:Cloud`。rootfs/FIT/ELF/UBI magicは未検出。
gzip magic候補3件は偶然一致の可能性があり未検証。`sign`という名前だけで署名が強制検証されるとは判断しない。
[inventory](evidence/jp-v1-260420-inventory.json)が再現可能な証拠。

## GPL inventory実装予定（先行資料）

2,327,878,345 bytesの公式GPL TAR.GZをstreamで読む。全archiveを展開せず、member名とサイズをJSONLで記録する。
選択した通常ファイルだけを上限付きで読み、NULを含むデータは本文を保存しない。symlink/hardlink/deviceは辿らない。
保存名は内容SHA256から生成するのでarchive内のpathをホストのpathとして利用しない。
個別2MiB・選択合計64MiB・tar展開合計32GiBを初期制限とし、超過で停止。vendor scriptを実行しない。

## Cloud decode実装の条件（先行資料）

GPL `uboot-7987/uboot/lib/nvrammanager/nm_fwup.c`はoffset0x130のRSA2048署名を保存し、その領域を0で埋めてoffset20以降をRSA-PSS/SHA256で検証する。
`rsaVerify.c`は署名のbyte orderを反転し、PSS saltを復元する。署名検証成功後、salt長が32より大きい条件でAES-128-CBCのkey/IVにsalt先頭32 bytesを使い、元imageのoffset0x230以降の16 byte単位のpayloadを復号する。
この手順を独立したオフライン解析ツールで再現し、署名が一致した場合だけ複製したpayloadを復号する。Node.js標準cryptoを使用し、元ZIP/BINを変更しない。署名生成・署名回避・flash writeは実装しない。
結果は公開FWに対する暗号的な一致の証拠であり、実機bootloaderが同一コードである証拠とは区別する。
