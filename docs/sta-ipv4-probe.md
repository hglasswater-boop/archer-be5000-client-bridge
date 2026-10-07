# IPv4 DHCP forwarding observation

対象はBE5000 JP/1.0、管理IP192.168.1.1、PC Ethernet index 7 / 192.168.1.52、管理Wi-Fi index 14。管理IP、PC address、route、DHCP clientの設定を変更せず、親機へのDHCP DISCOVERとOFFERだけを観測する。

## 通信と判定

1. Windows UDP socketのexclusive bindを0.0.0.0:68へ行い、IP_UNICAST_IFで送信interfaceを指定する。別processがportを使っていたら共有せず停止する。
2. random transaction IDと対象adapterのMACで、broadcast reply flagを付けたDHCP DISCOVERを255.255.255.255:67へ一回送る。ciaddr/giaddrはzero。実際のIP sourceは既存adapter addressであり、通常の未設定DHCP clientと完全に同じ条件ではない。
3. 最大8秒だけ受信。BOOTP reply、transaction ID、MAC、DHCP cookie、OFFER type、server identifier、非zero offered address、送信元port67を照合する。
4. WSARecvMsg / IP_PKTINFOから受信interfaceも照合する。同じtransactionのOFFERがWi-Fi側だけに届いても、Ethernet転送成功とは扱わない。切れたpayload/controlは採用しない。
5. Wi-Fi側controlでOFFERを確認してから、STA無効時のEthernet baselineを測定する。既知STA setterのreadback後さらに10秒待ち、Ethernetで一回測定。STA復元後にもEthernetで一回測定する。

DHCP REQUEST / RELEASE / DECLINEは送らず、leaseは取得・適用しない。DHCP serverがOFFERを短時間予約する可能性はある。個体MAC、transaction ID、server/offer address、packet本文をreportへ記録せず、固定した成否だけを保存する。

OFFERがEthernetへ返ればDHCPの両方向転送の証拠になるが、任意のIPv4 unicast、IP NATなし、複数端末、SMB、探索、長時間安定性の合格ではない。応答がなくてもSTA association失敗とは確定しない。

Windows APIの根拠は[IPPROTO_IP socket options](https://learn.microsoft.com/en-us/windows/win32/winsock/ipproto-ip-socket-options)、[IN_PKTINFO](https://learn.microsoft.com/en-us/windows/win32/api/ws2ipdef/ns-ws2ipdef-in_pktinfo)、[WSARecvMsg](https://learn.microsoft.com/en-us/windows/win32/api/mswsock/nc-mswsock-lpfn_wsarecvmsg)。vendor binaryを実行しない。

## 実行

```powershell
python -m tools.probe_sta_config --apply --source-ip 192.168.1.52 --security wpa3-transition --probe-ipv4
```

認証情報は既存の非表示promptへ入力する。IPv4/IPv6同時測定は拒否する。既知setterの復元とlogoutは通常probeと同じで、観測が失敗してもfinallyで実行する。

## 2026-10-07の実機結果

WPA2/WPA3混在mappingを使った限定STA試験で、以下を観測した。

| 測定 | 対象interfaceでのOFFER |
| --- | --- |
| Wi-Fi control | 受信 |
| Ethernet、STA有効化前 | なし |
| Ethernet、STA設定readbackから10秒待った後 | なし |
| Ethernet、開始時設定への復元後 | なし |

Ethernet測定では、同じtransactionに対する別interfaceのOFFERも受信していない。設定write/readback、STA無効化、開始時6 fieldの復元、logoutは成功し、rollback=verified。接続状態APIは有効時・復元後ともread-failedだった。

今回の条件と時間枠ではDHCP転送の成功を確認できなかった。通常のDHCP clientと異なるsource IP条件と短い待ち時間があるため、無線association失敗や恒久的な転送不能とは断定しない。IP leaseを適用せず、PC/BE5000の管理IPやrouteは変更していない。ローカルreportはlocal-evidence/sta-probe-20261007T045658760984Z.json。
