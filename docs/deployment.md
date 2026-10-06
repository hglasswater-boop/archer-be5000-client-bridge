# Deployment gate

現時点で実機投入可能なPoCはない。

投入前: 個体revision/FW、管理用有線経路、STA/4addr機能、BE700側対応、復旧とrollback、テスト計画を確認。
順序: baseline測定 → 隔離LAN → 検証済みruntime設定 → IPv4/IPv6/SMB/multicast → 12〜24時間 → 永続化の要否を評価。
今はAPやEasyMesh daemonを止めない。無線interface名・LAN bridge名・VLAN ID・driver APIを推測しない。
実機情報が不足した場合は投入を止め、公開資料の調査結果と未確認項目を残す。
