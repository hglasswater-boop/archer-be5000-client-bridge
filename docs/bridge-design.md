# Bridge design

## 基本条件

[Linux Wireless iw docs](https://wireless.docs.kernel.org/en/latest/en/users/documentation/iw.html)では、STA背後のネットワークをbridgeする4addr方式にAP/STA双方の対応が必要と説明される。
通常の3addr STAにLinux bridgeを追加するだけでは複数の有線端末MACを透過できるという証拠にならない。
vendor WDSとLinux 4addrの互換性は別に確認する。

## 比較予定

| 方式 | L2 | IPv4 / DHCP / ARP | IPv6 | multicast / mDNS | SMB / NAS discovery | latency / stability |
| --- | --- | --- | --- | --- | --- | --- |
| A: 4addr / 互換WDS | 双方対応時にFull候補 | broadcast/unicast透過を実測 | RA / ND / DHCPv6実測 | snooping含め実測 | SMB、探索とも実測 | 未測定 |
| B: STA + MAC NAT | Partial、元MAC非透過 | DHCP識別子、ARP、複数端末mappingの実装依存 | ND / RA変換対応必須 | group転送の実装依存 | direct IP通信と探索を別評価 | 未測定 |
| C: relayd相当 | Partial、純粋L2でない | ARP / DHCP relay機能に依存 | IPv4用relayの成功からIPv6を推論しない | relayの対応範囲を確認 | IPv4 SMB成立でも探索は別条件 | 未測定 |
| D: backhaulデータ経路再利用 | 実装依存 | 実装依存 | 実装依存 | 実装依存 | 実装依存 | daemonの再設定依存を確認 |

## 推奨を確定する順序

Aの双方向4addr確認を優先。次にDの最小runtime再利用の独立性を調べる。
B/CはIPv6とNAS discoveryを含む要件を満たす証拠がある場合だけ採用候補にする。
STA作成、AP停止、EasyMesh停止、LAN接続、DHCP停止、NAT停止の具体コマンドは、実機driver・管理経路が分かるまで作らない。
