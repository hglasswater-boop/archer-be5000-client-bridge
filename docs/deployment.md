# Deployment gate

現時点で実機投入可能なClient Bridge PoCはない。安全なruntime設定経路、BE700側との4addr互換性、AP完全停止時のSTA維持、brick recoveryが未確立。
現在までの実機操作はUIの読み取り、機種/FW照合、限定したTCP接続確認。新規管理password作成はユーザー操作。未保存quick setupは適用せず終了。AP / EasyMesh / DHCP / NAT / FWの変更を行っていない。

## 条件が満たされた後の投入順序

1. 同版backupと有線管理/再起動rollbackを確認。両端の無線driver/API・BE700のhardware/FWを記録。
2. 既存EasyMeshとBE700直結のbaselineを測定。PCがWi-FiとBE5000直結を併用する際、同じ192.168.0.0/24とgateway192.168.0.1が両interfaceに存在することを今回観測した。試験時は実際の経路を固定/記録し、この競合を混同しない。
3. 隔離LANで検証済みruntime変更を一段ずつ実施。5GHz STA接続 → LAN forwarding → DHCP/NATなし → EasyMesh依存解消 → 全AP beacon停止の順に確認し、途中でmanagement / STAが失われたらrollback。
4. IPv4/IPv6、BE700側端末とのSMB/multicast/mDNS、復帰・再associationを確認。PC/NAS間のlocal switch通信だけで合格にしない。
5. 12〜24時間試験と再起動後の再現性を確認。合格後にstartup永続化の必要性を判断する。

[テスト計画](testing.md)。実interface、bridge、VLAN ID、driver setterやdaemon停止順序を推測して投入scriptにしない。復号解析copyをflashしない。
