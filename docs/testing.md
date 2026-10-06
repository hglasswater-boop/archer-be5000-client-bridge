# Test plan (before implementation)

日付2026-10-06。実機テストは未実施。下記の合格はまだ得ていない。

## オフライン解析テスト

公式archiveを使う前にsynthetic fixtureでheader offset検出、partition候補の範囲検証、truncated data、重複magic、archive path traversal、巨大展開の制限をテストする。
imageを変更しない、通信やflash writeを行わない、未知形式を既知と断定しない設計にする。
GPL TARにはpath traversal・リンク無視・member/合計の読取り制限・stream途中失敗をsynthetic fixtureで確認する。
Cloud decodeにはPSSの不正hash・marker・trailerの拒否とRSA public blob構造検証、NIST AES-CBC既知ベクトルを使用する。失敗時に復号しない。

## 比較構成

1. PC → BE700有線のbaseline。
2. 現在のEasyMesh（FWと設定を固定）。
3. 条件確認後のみ候補Client Bridge。

BE700側有線端末を1台追加する。PC↔NASだけではBE5000内switchを通る可能性があり、無線uplinkの検証にならない。
試験開始/終了、構成、版、channel、RSSI、DFS/channel change、PC/NAS IPと管理経路を記録する。

## 接続試験

| 項目 | 合格条件 | 証拠 |
| --- | --- | --- |
| PC / NAS DHCPv4 | BE700のlease各1件、異なるMAC/client ID、同一prefix | lease + DHCP capture |
| IPv6 | RA/SLAAC、必要ならDHCPv6、DAD成功、双方向通信 | RA/ND/DHCPv6 capture |
| gateway / DNS / Internet | IPv4/IPv6、名前解決とTCP/HTTPS成功 | 各endpoint log |
| PC ↔ NAS | IPv4/IPv6到達、SMB読書き成功 | ping + SMB hash |
| BE700 LAN ↔ PC / NAS | 双方向TCP/SMB成功 | 両側capture |
| ARP / ND renewal | cacheの失効後も双方向成功 | neighbor table + capture |
| multicast / mDNS / NAS discovery | 両方向のサービス探索・announceを確認 | UDP5353 / 対象NASプロトコルcapture |
| no NAT / no DHCP server | original IP保持、BE700以外のDHCPOFFERなし | 両側capture + rule確認 |
| AP / EasyMesh OFF | クライアント向けbeaconなし、制御停止後もuplink維持 | 無線capture + daemon/interface状態 |
| Full L2候補 | PC/NASそれぞれのMACをuplink両側で保持 | Ethernet/無線capture、FDB |

## 12〜24時間の安定性試験

各比較構成で同じ条件・期間で測定する。pingはgateway、BE700側有線端末、NAS、外部endpointを分けて記録。
iperf3をBE700側有線端末とPC/NAS間で正逆、単一/複数TCPに実施する。SMBは合意済み試験directoryで大容量copyとhash比較。
long-lived TCP、DHCP renew、ARP renewal、IPv6 ND、Wi-Fi reassociationとbackhaul切断を監視する。
loss、RTT分位、throughput、unexpected TCP reset、転送失敗、再接続回数を数値化。初期受入目標は予期しないreset・hash不一致・自発的reassociationが0。
packet lossはbaselineとの比較と用途上の許容値を記録し、無線で絶対0を無条件に保証しない。

## ERR_CONNECTION_RESETの切分け

captureのtcp.flags.reset == 1を抽出し、5-tuple、時刻、送信元、直前のretransmission、各構成を照合する。
終端アプリによる通常のRSTと予期しないRSTを分ける。ブラウザエラーだけでWi-Fi原因としない。
PCとBE700側の両側captureでreset発生位置を調べ、driver/offloadで観測できない場合はその限界を記録する。
IPv4/IPv6、LAN内/Internet、SMB/HTTPSを分ける。TLS本文やcredentialを公開しない。

結果欄はNOT RUN。12〜24時間の実機成功をsynthetic単体テストで代用しない。
