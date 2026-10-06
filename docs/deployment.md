# Deployment gate

現時点で実機投入可能なClient Bridge PoCはない。通常認証によるSTA getterと、5GHz限定setterの一回適用・読み戻し・無効化・復元は成立したが、STA association、複数LAN端末のMAC変換/proxy、AP完全停止時のSTA維持、brick recoveryが未確立。
BE700は通常APとして扱う。4addr互換性は通常STA PoCの先行条件から外し、Full L2方式を選ぶ場合のみ確認する。
現在までの実機操作はUIの読み取り、機種/FW照合、限定したTCP接続確認、管理IP変更、DHCP停止、限定STA setter probeである。新規管理password作成はユーザー操作。未保存quick setupは適用せず終了。AP / EasyMesh / NAT / FWの変更は行っていない。setter probeの各試行は終了時にSTAを無効化し、開始時の設定へ戻した。
MLO対応SSIDを候補にした混在security mappingのreadbackまでは確認したが、MLO client negotiation、link aggregation、forwardingは未測定である。

## 条件が満たされた後の投入順序

1. 同版backupと有線管理/再起動rollback、BE5000のSTA/forwarding設定APIを確認。通常STA接続に必要なSSID・認証条件を確認し、BE700のhardware/FW調査を待たずに進める。
2. 既存EasyMeshとBE700直結のbaselineを測定。PCがWi-FiとBE5000直結を併用する際、同じ192.168.0.0/24とgateway192.168.0.1が両interfaceに存在することを今回観測した。試験時は実際の経路を固定/記録し、この競合を混同しない。
3. 隔離LANで検証済みruntime変更を一段ずつ実施。5GHz STA接続 → LAN forwarding → DHCP/NATなし → EasyMesh依存解消 → 全AP beacon停止の順に確認し、途中でmanagement / STAが失われたらrollback。
4. IPv4/IPv6、BE700側端末とのSMB/multicast/mDNS、復帰・再associationを確認。PC/NAS間のlocal switch通信だけで合格にしない。
5. 12〜24時間試験と再起動後の再現性を確認。合格後にstartup永続化の必要性を判断する。

[テスト計画](testing.md)。実interface、bridge、VLAN ID、driver setterやdaemon停止順序を推測して投入scriptにしない。復号解析copyをflashしない。
