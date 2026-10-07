# Archer BE5000 Client Bridge Investigation

Archer BE5000 **JP/1.0** を、EasyMeshなしの5GHz STA → 1GbE PC/NAS用Ethernet Converterにできるか調査する。
[Issue #1](https://github.com/hglasswater-boop/archer-be5000-client-bridge/issues/1)を先に作成し、資料 → テスト → 最小実装 → 矛盾/不要コード確認の順で進めた。

## 2026-10-06〜07の結論

**日常利用できるClient Bridgeは未成立。限定STA設定試験とIPv4 DHCP観測まで実施済み。**
STA機能の候補はあり、恒久的な実現不能と断定した結論ではない。復旧未確立のまま改造FWを書き込むことはしない。

**現在の実機状態:** 2026-10-07 06:08ZのreadbackでMesh off、通常2.4GHz/5GHz AP off、radio全体のdisabled_all=off、5GHz STA on、管理IP192.168.1.1、DHCP offを確認。06:21Zに試験用の通常SSID / WPA2へ適用・readback成功。設定成功後の無効化・復元は省く。Ethernet DHCPはOFFERなしで、接続状態と転送成功は未確立。guest/MLO/backhaulの全BSS停止、NAT停止は未確認。[実機切り分け](docs/converter-runtime.md)。

PCで見えたMLO接続はWPA3-Personal(H2E)、5GHz channel 124と6GHz channel 69。比較用の通常SSIDが見つからなかったため、空白なしの通常5GHz/WPA2試験SSIDを依頼した。準備中に試験SSIDのWPA2表示を確認し設定したが、その後のBSSID指定試験では対象が見つからず、設定write前に停止。親機側の準備完了を待つ。BE5000の5GHz surveyは成功応答だが0件。AP/radio getterはbodyにformを含めてreadすることで値を取得できた。

通常管理認証のadministration/login/app_user_agreeで有線PCだけのSSH許可を要求し、20001/TCPのdropbear待受けと既存管理パスワードによる認証を確認した。ただしexec、PTY、shell要求は拒否されたため、実機コマンド実行やshell取得は成立していない。

追加比較でBSSID固定解除fieldを明示したwriteはHTTP応答拒否となり、失敗処理で一時STA offになった。受理実績のある6 fieldへ戻して再適用し、05:33ZにSTA onのreadbackと有効維持を確認済み。Ethernet DHCPは引き続きOFFERなし。保存BSSIDがgetterから隠れる条件と、driver起動に至るwifix update経路を[解析記録](docs/sta-link-observation.md)へ追記した。

起動処理の静的解析では、STA mode変換とradio再読み込みの経路を特定。公開設定で有効なsupplicant経路はinterface登録後にdisconnectを送り、後でdriver enableへ進む。Mesh側にも別のreconnect処理があり、通常STAの接続開始を調べる具体的な候補になった。実機での到達・原因確定は未確認。[起動経路の根拠](docs/wifix-sta-startup.md)。

05:45Zの読み取り診断で実機EasyMesh enable=onと5GHz STA=onを確認。公開meshdでは、対象band maskで絞ったSTAへのreconnectが接続先選択・node情報の処理から呼ばれる。radio再読み込み完了だけでの無条件再接続ではない。daemon稼働・実機role・associationは未確認。`python -m tools.read_sta_diagnostics --source-ip 192.168.1.52 --probe-mesh` は保存されたMesh有効状態だけを追加取得し、設定を書き換えない。

- 本体ラベルと直結Web UIでJP/1.0、**1.2.0 Build 20260420 rel.13798(4A50)** を照合。JP最新版と一致。
- 公開FWのRSA2048-PSS/SHA256を検証し、copyのAES128-CBC payloadを復号。全UBI CRCを検証してkernel / rootfsを読んだ。
- 最新FWに5GHz bSTA **apclii0**、**br-lan**、vendor Wi-Fi driver、hostapd/wpa_supplicantのwpad、EasyMesh agent/controller、wifix / meshd / apsd / tpbrを確認。GPLにはAPCLI / MWDS / MAC_REPEATER機能がある。
- 実機UIの動作モードはrouter/APのみ。通常loginでSTA設定のbackend getterに到達し、両bandのSTA=offを確認した。5GHz限定setterはWPA2/AES候補とWPA2/WPA3混在候補で一回ずつ受理・読み戻しでき、無効化と開始時設定へのrollbackも確認した。association、複数LAN端末の転送、AP停止は未確認。実機の公開featureはWDS=false。apsd停止はtpbr detachを伴うため、単純なmesh停止はforwarding維持を保証しない。
- 実機brick recovery、IPv4の複数LAN端末転送、AP完全停止とSTA維持、SMB/multicast、12〜24時間安定性は未確認。IPv6は今回の要件から外す。
- 2026-10-07の優先方針: BE700を通常APとして通常STA + MAC変換/proxy経路をBE5000側で調べる。MLO対応SSIDでも設定値の受理までは確認できたが、MLO client negotiation・link aggregationは未測定。BE700 HW/FW・4addr調査はFull L2を選ぶ場合の追加項目。

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
| [Testing](docs/testing.md) | baseline、IPv4/SMB/探索、TCP reset、12〜24時間 |
| [Deployment](docs/deployment.md) | 条件が満たされた後の投入順序 |
| [Reproduction](docs/reproduce.md) | オフライン解析の再現コマンド、境界 |
| [Runtime investigation](docs/runtime-investigation.md) | 設定backup取得、実機ログ、STA設定経路とwifixの追加解析 |
| [Read STA state](docs/read-sta-state.md) | 通常認証による限定getterの仕様・実行方法。対象実機のlogin・read・logoutが成功 |
| [STA config probe](docs/sta-config-probe.md) | 5GHz限定setter、security mapping、rollback、IPv4試験の範囲 |
| [IPv4 DHCP probe](docs/sta-ipv4-probe.md) | leaseを取得しないDISCOVER/OFFER観測、受信interface照合、実機結果 |
| [STA link observation](docs/sta-link-observation.md) | 既知tmp_readによるBSSIDの有無・信号・channelの限定観測 |
| [Wired management](docs/wired-management.md) | 管理IP分離、PC固定IP、DHCP復元手順 |

実装したのは**オフライン解析PoC**（inspect_firmware / inspect_gpl / decode_cloud / read_ubi）、通常認証で既知STA getterを読む限定client（read_sta_state）、既知の5GHz setterを一回だけ適用してrollbackする限定probe（probe_sta_config）である。Client Bridgeの永続化scriptや書込みimageは作成していない。
`python -m unittest discover -s tests -q`: **74 PASS、skipなし**。実配布物の署名/復号/UBI/SquashFS読み取り、限定clientの実機公開feature preflight・通常login・STA read・logout、およびsetter probeの失敗時rollback境界、DHCP応答/interface照合、tmp_read観測の個体値除外、有効状態の維持、ログ分類と読み取り失敗時logoutを検証した。
firmware / GPL archive / 復号image / rootfs本文 / 個体情報はgit対象外。

## 判定項目

| 項目 | 結果 |
| --- | --- |
| Verdict | 日常利用構成は未成立。限定STA設定の受理・復元を確認、DHCP転送成功は未確認 |
| Recommended approach | BE700を通常APとして、純正FW/driverのAPCLI + MAC変換/proxyを優先。認証済み管理経路とrollback/recoveryを確立 |
| Firmware modification required | 未判定。今回の調査ではNo、目標構成で必要かは未確認 |
| Brick risk | 読み取り調査はLow、復旧未確立の改造flashはHigh |
| Recovery method | 対象個体で成功した手段なし。dual-image / TFTP / UARTは候補証拠のみ |
| L2 transparency | 未確認。4addr双方対応時Full候補、MAC NAT/relaydはPartial |
| IPv4 | 限定DHCP観測でWi-Fi controlはOFFER受信、EthernetはSTA有効中もOFFERなし。ARP/unicast/SMBは未測定 |
| IPv6 | 今回の要件外。限定probeのlink-local結果は診断記録のみ |
| SMB/NAS suitability | NOT RUN。BE700側有線端末との通信/探索が必要 |
| Expected stability | 未測定。EasyMeshとERR_CONNECTION_RESETの因果関係も未確定 |
| Remaining unknowns | MLO/STA associationの実証、wds_modeのdriver側意味、AP/STA独立性、複数LAN端末のforwarding方式、実機boot chain/復旧、長時間試験。BE700 HW/FW・4addrはFull L2選択時のみ |

Issueは実機条件を追跡するためopenのまま。未実施の試験を完了扱いにしない。
