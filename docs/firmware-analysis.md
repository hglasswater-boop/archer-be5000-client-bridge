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

container / header / partition / filesystem / kernel / userspace / init / network scripts / wireless / bridge / VLAN /
EasyMesh daemon / hostapd / wpa_supplicant / proprietary daemon / writable overlayはいずれも未確認。
Web UI署名検証、bootloader検証、rollback protection、encryption、rootfs verificationも未確認。
GPLとbinaryの差分は対象buildの対応確認後に評価する。
