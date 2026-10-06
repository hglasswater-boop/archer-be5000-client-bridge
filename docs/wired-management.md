# PC有線管理の準備と復元

2026-10-07、ユーザーがBE5000のLAN管理IPを192.168.0.1から192.168.1.1/24へ変更した。
PCの有線DHCP addressが192.168.1.210になり、sourceを固定したpingと本体MAC照合に成功。
通常loginでLAN IP / DHCP / sysmode / STA設定を読み取れた。
この管理用subnet変更は、転送するPC/NASを親機と同一subnetにする最終構成の検証とは別の操作。

## PC固定IP

tools/prepare_wired_management.ps1は管理者権限が必要なPC側の限定helper。
対象Ethernetのindex、現在のDHCP IP、BE5000の本体MACを照合してから、192.168.1.52/24をActiveStoreへ設定する。
新しいgateway/DNSを追加せず、Wi-Fi adapterは変更しない。reportはlocal-evidenceだけへ保存する。
現在のBE5000配布範囲192.168.1.100〜249から外した管理用IPであり、親機のLANに永久割当てするIPではない。

初回は3秒のaddress確認で停止し、DHCPへ戻す処理が成功した。
待機上限を10秒に変更した再試行ではPreferred状態と管理IPへの到達を確認し、pin-completeとなった。
本番のhelperにvendor binary実行やpasswordは含まれない。

```powershell
# 管理者PowerShell。MAC値は本体ラベルから入力する（公開資料へ保存しない）。
.\tools\prepare_wired_management.ps1 -Mode Pin -InterfaceIndex 7 -CurrentAddress 192.168.1.210 -ExpectedRouterMac '<label MAC>'
```

その後、BE5000のWeb UIでDHCPをoffへ保存し、再読込でoffを確認した。
PCの192.168.1.52から有線管理を継続できる。STAはまだoff。

## 元のPC DHCPへ戻す順序

1. 5GHz STAを停止し、親機と橋渡ししていないことを確認する。
2. BE5000のWeb UIでDHCPを再び有効にする。LAN管理IPを1.1に保つなら範囲100〜249。
3. 管理者PowerShellでhelperのRestoreDhcpを使う。
4. PCの有線DHCP leaseと管理画面への到達を別途確認する。

```powershell
.\tools\prepare_wired_management.ps1 -Mode RestoreDhcp -InterfaceIndex 7 -ExpectedRouterMac '<label MAC>'
```

RestoreDhcpは1.52のManual addressだけを削除し、同じEthernetのDHCPを再有効化する。
結果dhcp-enabledはlease取得成功ではない。router DHCPを先に有効にしないとaddressを取れない。
ActiveStoreは今回の一時管理用で、PC再起動後の管理到達を保証しない。DHCP停止後にPCを再起動する前は、固定管理IPの維持か上の復元を行う。
全設定backupは管理IP変更前のもの。backup復元を行う場合、192.168.0.1へ戻る可能性も別に扱う。
