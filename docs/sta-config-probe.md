# 限定した5GHz STA設定試験

設定getterの成功後に行う、通常認証の既知setter受理とrollbackの試験。資料 → offline tests → 実装 → 実機の順で進める。
この試験だけではassociationやClient Bridgeの成功を判定しない。

## 前提

- BE5000 JP/1.0、対象FW 1.2.0 Build 20260420 rel.13798(4A50)、PC直接有線接続。
- 管理IP 192.168.1.1/24、本体MAC照合済み、PCは有線192.168.1.52/24固定。
- BE5000のDHCPがoff。親機へDHCPを持ち込むことを防ぐため、STA enableより先に停止する。
- mode=router、STA両band=off、encryption=psk、version=rsn、cipher=aes、wds_mode=2、locktoap=off。
- 保存済みSSID/PSKはRAM内に原値を保持して戻す。空値または限定ASCIIの復元可能な値だけを許し、mask・未知形式・有効な既存STAは上書きせず停止する。

管理IP/DHCPはWeb UIの通常設定で変更した。PC固定IPの手順は[wired-management](wired-management.md)。
親機はWPA2/WPA3混在の通常APとして扱い、security mappingを選んだ5GHz接続候補を使う。親機の暗号設定は変更しない。`wpa2`は`psk/rsn/aes`、`wpa3-transition`はfrontendが示す`psk_sae/sae_transition/aes`である。後者の受理はMLO client negotiationを意味しない。

## 要求とrollback

既知frontendとcontrollerの/admin/wireless?form=wireless_connect_to_networkへ、通常の暗号化operation=writeを送る。
変更fieldはenable_5g、ssid_5g、encryption_5g、psk_version_5g、psk_cipher_5g、psk_key_5gの6個に限定する。
2.4GHz、wds_mode、locktoap、クライアント用AP、sysmode、LAN、DHCPはこのtoolから変更しない。
controllerの普通のwrite経路はApcfgへmesh operationを渡さない。静的なapply分岐は[runtime investigation](runtime-investigation.md)を参照。
**設定はcommitされる。RAMだけの試験ではなく、再起動だけで戻るという前提を置かない。**

1. 公開featureを照合し、既存passwordで1回だけ通常loginする。session衝突を強制解除しない。
2. LAN/DHCP/sysmode/STAをreadして前提を確認。getterのSSID/PSK原値はRAM内だけで保持し、接続先SSID/PSKは非表示でPC terminalから入力する。
3. 6 fieldを一度writeし、4秒後のgetterで同じ値と2.4GHz offを確認する。
4. 最大45秒の観測時間を置く。設定が一致してもassociation成功とは扱わない。
5. writeの応答が失われた場合も、試行した後はfinallyでrollbackを実行する。
6. 最初にenable_5g=offだけをwriteし、続いて保存した6 fieldの初期値をwriteする。
7. 4秒後のgetterで初期値・両band offを照合し、logoutする。

writeの自動再試行は行わない。rollbackの2段階は接続停止と初期値復元の別要求。
rollbackに失敗した場合は成否を区別し、それ以上の接続・転送試験へ進まない。
有線管理を失った場合はこのHTTP clientだけでは復元不能であり、未検証のflash/recoveryを代行しない。

初回の実機前提確認では「SSID/PSKが空」という条件で停止した（write_attempted=false）。
secretを保存しない追加readで、両bandに保存値があることだけを確認した。本文やhashは記録しない。
最新bytecodeのrootap psk_key mappingにcvtがなく、Apcfg.read_data→get_option→UCI getとcontrollerのsuffix copyで値が返ることを追跡した。
独自get_psk_key/mask処理はこのmodel/controllerの定義に見当たらない。
そのため、disabled STAの復元可能な保存値をRAM snapshotとして扱う条件へ修正し、保存値を復元するoffline testを追加した。

SSIDはshell metacharacterを除く限定ASCII文字（空白を含む）だけ、PSKは空白なしの限定ASCII文字だけを許す。対象SSID/passwordの詳細は公開資料へ記載しない。
secret・token・cookie・PSKのhashを出力しない。比較の成否、段階、固定したerrorだけをlocal-evidenceへ保存する。

実行予定:

```powershell
python -m tools.probe_sta_config --apply --source-ip 192.168.1.52
```

WPA2/WPA3混在の候補を使う場合は次のように指定する。

```powershell
python -m tools.probe_sta_config --apply --security wpa3-transition --probe-ipv6 --source-ip 192.168.1.52
```

管理password → 対象SSID → Wi-Fi passwordの順に非表示入力。--applyがなければ通信や設定変更をしない。
FWの書込み、SSH/firewall変更、mesh daemon停止、AP停止は対象外。

## 実機結果

WPA2/AES候補とWPA2/WPA3混在候補を一度ずつ実行し、どちらも設定writeの受理、4秒後の6 field readback、5GHz無効化、開始時設定へのrestore、logoutを確認した。最新の混在候補は`configuration-probe-complete`、`rollback=verified`で終了した。getterは既知の接続状態フィールドを返さず、status observationは`unavailable`だった。設定値の受理・復元までであり、association、MLO link aggregation、IPv4 forwarding、AP停止、再起動後の永続性は未測定である。

以前のIPv6 probeは診断記録としてのみ残す。IPv6は今回の受入条件から外し、以後の実機判定はIPv4へ絞る。

IPv4 forwardingはまだ測定していない。PCのWi-Fi側に親機サブネットのdefault routeがあり、有線側は管理用の別サブネットなので、通常のpingだけでは無線uplinkの転送を判定できない。2026-10-07の一時host route追加はOSの権限不足で拒否され、routeは追加されなかった。BE5000経由のrouted pingだけでも同一ネットワークのbridge成立を証明できない。次の通信試験は管理用アドレスを維持しつつ、有線側で親機のDHCP取得または重複しない同一サブネットの試験アドレスを用意し、Wi-Fi経由の迂回を除外して行う。

IPv6測定を省いた最新試行では、既知のread-only route `/admin/wireless?form=wireless_connect_status` をSTA有効時と復元後に一度ずつ要求した。両方ともreadに失敗し、`status_after_write` / `status_after_restore` は`read-failed`だった。設定write・readback・rollback・logoutは成功した。接続状態readの失敗からassociation失敗とは判定しない。

## 参考: IPv6の限定試験（今回の受入対象外）

--probe-ipv6を指定した試行では、PCのEthernet index 7とWi-Fi index 14のlink-local address、Wi-Fi側のIPv6 default gatewayをPCから読み取る。
全addressをlink-localとして検証し、pingのsourceとdestinationに明示したinterface scopeを付ける。
管理者権限、追加IPv4 address、route設定変更は不要。addressの詳細は公開reportへ入れない。
STA write前のEthernet疎通とWi-Fi疎通をcontrolとして記録し、設定readback成功の後、rollback開始前にEthernet疎通を最大3回試す。
rollback確認後の同じEthernet疎通も記録する。
getter読出しとpingの順序は同じprocess内で固定し、復元後のpingを有効期間の観測へ数えない。
replyがなくても、association失敗 / IPv6 ND変換 / bridge設定のどれが原因かはこの試験だけでは判定できない。
IPv4、複数LAN端末、SMB、multicast、AP停止、長時間安定性の合格を代用しない。
