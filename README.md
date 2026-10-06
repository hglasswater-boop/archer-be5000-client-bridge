# Archer BE5000 Client Bridge Investigation

Archer BE5000 **JP/1.0** を、EasyMeshなしの5GHz STA → 1GbE PC/NAS用Ethernet Converterにできるか調査する。
[Issue #1](https://github.com/hglasswater-boop/archer-be5000-client-bridge/issues/1)を先に作成し、資料 → テスト → 最小実装 → 矛盾/不要コード確認の順で進めた。

## 2026-10-06〜07の結論

**NOT PRACTICAL：現時点で安全なClient Bridge実機PoCを投入する条件が揃わない。**
STA機能の候補はあり、恒久的な実現不能と断定した結論ではない。復旧未確立のまま改造FWを書き込むことはしない。

- 本体ラベルと直結Web UIでJP/1.0、**1.2.0 Build 20260420 rel.13798(4A50)** を照合。JP最新版と一致。
- 公開FWのRSA2048-PSS/SHA256を検証し、copyのAES128-CBC payloadを復号。全UBI CRCを検証してkernel / rootfsを読んだ。
- 最新FWに5GHz bSTA **apclii0**、**br-lan**、vendor Wi-Fi driver、hostapd/wpa_supplicantのwpad、EasyMesh agent/controller、wifix / meshd / apsd / tpbrを確認。GPLにはAPCLI / MWDS / MAC_REPEATER機能がある。
- 実機UIの動作モードはrouter/APのみ。公開STA/WDS設定入口と使用可能な認証済みshellは確立できなかった。apsd停止はtpbr detachを伴うため、単純なmesh停止はforwarding維持を保証しない。
- 実機brick recovery、複数LAN端末の転送、AP完全停止とSTA維持、IPv6/SMB/multicast、12〜24時間安定性は未確認。
- 2026-10-07の優先方針: BE700を通常APとして通常STA + MAC変換/proxy経路をBE5000側で調べる。BE700 HW/FW・4addr調査はFull L2を選ぶ場合の追加項目。

## 成果物

| 資料 | 内容 |
| --- | --- |
| [Architecture](docs/architecture.md) | 目標、判定条件、調査中の配線 |
| [Hardware](docs/hardware.md) | 個体照合とFW/GPLのハードウェア証拠 |
| [Firmware analysis](docs/firmware-analysis.md) | 署名、暗号、userspace、mesh forwarding、GPL差分 |
| [Partition map](docs/partition-map.md) | physical flashとcontainer/UBI配置の区別 |
| [Existing support](docs/existing-support.md) | OpenWrt / upstream / SDKの調査範囲 |
| [Bridge design](docs/bridge-design.md) | 4addr、MAC NAT、relayd、backhaul再利用の比較 |
| [Recovery / rollback](docs/recovery.md) | 未確立の復旧手段、実施前条件 |
| [Testing](docs/testing.md) | baseline、IPv4/IPv6/SMB/探索、TCP reset、12〜24時間 |
| [Deployment](docs/deployment.md) | 条件が満たされた後の投入順序 |
| [Reproduction](docs/reproduce.md) | オフライン解析の再現コマンド、境界 |
| [Runtime investigation](docs/runtime-investigation.md) | 設定backup取得、実機ログ、STA設定経路とwifixの追加解析 |

実装したのは**オフライン解析PoC**（inspect_firmware / inspect_gpl / decode_cloud / read_ubi）。Client Bridge設定scriptや書込みimageは作成していない。
`python -m unittest discover -s tests -v`: **23 PASS、skipなし**。実配布物の署名/復号/UBI/SquashFS読み取りも成功。
firmware / GPL archive / 復号image / rootfs本文 / 個体情報はgit対象外。

## 判定項目

| 項目 | 結果 |
| --- | --- |
| Verdict | NOT PRACTICAL（現時点の安全な実機投入） |
| Recommended approach | BE700を通常APとして、純正FW/driverのAPCLI + MAC変換/proxyを優先。認証済み管理経路とrollback/recoveryを確立 |
| Firmware modification required | 未判定。今回の調査ではNo、目標構成で必要かは未確認 |
| Brick risk | 読み取り調査はLow、復旧未確立の改造flashはHigh |
| Recovery method | 対象個体で成功した手段なし。dual-image / TFTP / UARTは候補証拠のみ |
| L2 transparency | 未確認。4addr双方対応時Full候補、MAC NAT/relaydはPartial |
| IPv4 | 候補bridgeではNOT RUN |
| IPv6 | 候補bridgeではNOT RUN。upstream relaydだけでは要件を満たさない |
| SMB/NAS suitability | NOT RUN。BE700側有線端末との通信/探索が必要 |
| Expected stability | 未測定。EasyMeshとERR_CONNECTION_RESETの因果関係も未確定 |
| Remaining unknowns | runtime設定経路、AP/STA独立性、複数LAN端末のforwarding方式、実機boot chain/復旧、長時間試験。BE700 HW/FW・4addrはFull L2選択時のみ |

Issueは実機条件を追跡するためopenのまま。未実施の試験を完了扱いにしない。
