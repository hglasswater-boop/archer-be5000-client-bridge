# Archer BE5000 Client Bridge Investigation

日本向けArcher BE5000を、EasyMeshなしの5GHz STA → 有線PC/NAS用Ethernet Converterにできるか調査する。

Issue: https://github.com/hglasswater-boop/archer-be5000-client-bridge/issues/1

2026-10-06調査開始。地域は日本（ユーザー申告）、Hardware Ver.は不明、実機FWは「最新」（正確な版未確認）。
資料 → テスト → 最小実装 → 最終確認の順序を守る。復旧確立前に改造FWを書き込まない。
公開FWの解析候補はJP V1であり、対象個体への適合を意味しない。

## 資料

- [構成と確認条件](docs/architecture.md)
- [ハードウェア](docs/hardware.md)
- [公式FW・GPL解析](docs/firmware-analysis.md)
- [partition map](docs/partition-map.md)
- [bridge方式比較](docs/bridge-design.md)
- [boot・recovery・rollback](docs/recovery.md)
- [テスト計画](docs/testing.md)
- [実機投入条件](docs/deployment.md)

実機の接続・復旧・長時間試験を実施したという意味でのPoCは、条件が確認できるまで作成しない。
