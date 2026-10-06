# Bridge design

[Linux Wireless公式iw docs](https://wireless.docs.kernel.org/en/latest/en/users/documentation/iw.html)の4addr bridgeはAP/STA双方の対応が必要。通常3addr STAをLinux bridgeへ追加しただけではLAN複数MACの透過を保証しない。vendor WDS / MWDSと標準的4addr互換性は別の確認項目。

| 方式 | L2 | IPv4 / DHCP / ARP | IPv6 | multicast / mDNS | SMB / NAS探索 | latency / stability |
| --- | --- | --- | --- | --- | --- | --- |
| A: 4addr / 互換WDS | 双方対応時Full候補 | broadcast/unicast透過を実測 | RA / ND / DHCPv6実測 | snooping含め実測 | SMBと探索を別に実測 | 未測定 |
| B: STA + MAC NAT | Partial、元MAC非透過 | 複数端末mapping、DHCP識別子・ARPの実装依存 | ND / RA等の対応必須 | group転送の実装依存 | direct IPが通っても探索は別条件 | 未測定 |
| C: relayd相当 | Partial | proxy ARP / DHCP relayの実装依存 | upstream relaydはIPv4のpseudo bridge、IPv6を満たさない | IPv4 relay成功から透過を推論しない | IPv4 SMB成立でもIPv6/探索要件が残る | 未測定 |
| D: 既存backhaul data path | 実装依存 | 実装依存 | 実装依存 | 実装依存 | 実装依存 | daemonによる上書き・再設定を確認 |

relaydの範囲は[公式source](https://github.com/openwrt/relayd)を確認。LAN複数MACの扱い、ARP、DHCP、ND、multicast、TCPをそれぞれ検証し、IP NATなしとMAC変換なしを区別する。

## 推奨設計

**純正kernel / driver / FWを保ち、隔離LANでAPCLIによるruntime構成を検証する**方針を優先する。Aの双方対応と、Dの制御を切り離せるかを先に確認する。BはIPv6/探索を含む実測が揃えばPartialとして評価。Cは現要件のIPv6を満たさず既定案にしない。

最新FWには5GHz bSTA apclii0とbr-lan、GPLにAPCLI / MWDS / MAC_REPEATERがあり、候補の存在は確認できる。しかし以下の壁がある。

- 実機UIで選択可能なモードはrouter/APのみ。WDS設定入口は確認できず、画面内検索も0件。
- 現時点のSSH/Telnet接続はtimeout。合法的に使える認証済みshell / runtime設定経路がない。
- apsd停止時にtpbrをdetachするため、mesh daemon全停止とLAN forwardingの維持は両立が実証されていない。
- 5GHz AP VAPの停止時にSTA/PHYも停止するか、driver再起動を誘発するか不明。SSID非表示だけではAP停止要件を満たさない。
- BE700側のhardware/FWと4addr互換性、WPA2/WPA3/PMF/DFSでの再接続動作が未確認。

このため具体STA setter / bridge / kill scriptはまだ出さない。rootfs再packやbootloader変更に進む理由はなく、先に実機アクセス・管理rollback・recoveryを確立する。**現時点の安全な実機投入はNOT PRACTICAL**。技術的にSTA bridgeが永続的に不可能と断定したものではない。
