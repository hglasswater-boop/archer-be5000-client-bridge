# Architecture

## 入力と目標

現在: Internet → Archer BE700 → EasyMesh wireless backhaul → Archer BE5000 → 1GbE PC / 1GbE NAS。
目標: BE700の5GHz AP → BE5000 STA/client → wired LAN。BE700側LANと同一ネットワーク、NATなし、BE5000 DHCP serverなし、クライアント向けAPなし、EasyMeshなし。
SMB、IPv6、multicast、長時間TCPの安定性を優先する。

BE5000は本体ラベルJP/1.0、実機UIもv1.0、FWは1.2.0 Build 20260420 rel.13798(4A50)で照合済み。
BE700のrevision、FW、4addr対応は未確認。PCのWi-FiとBE5000直結LANに192.168.0.0/24があり、それぞれ別MACのgateway192.168.0.1が見える。
これは今回の調査中の構成であり、過去のERR_CONNECTION_RESETの原因と断定しない。試験時は経路を記録して切り分ける。
ERR_CONNECTION_RESETとEasyMeshの因果関係は未確認。resetを消せると約束しない。

## 調査の判定条件

1. 個体・地域・revision・FWが一致する証拠。
2. STA機能とBE700/BE5000双方の4addr・暗号化条件を確認。
3. 管理用有線経路、変更前の構成とrollback、復旧方法を確認。
4. 資料とテストを先に更新する。
5. 検証済みruntime設定で最小試験。起動永続化・overlay・rootfs・repack・bootloader変更の順に慎重に評価。

未確認は非対応を意味しない。4addrがBE5000だけで有効でもBE700で受信できなければ純粋L2は成立しない。
