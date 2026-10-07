# STA tmp_read observation

公開FW controllerのwireless_connect_to_networkはoperation=tmp_readをtmp_read_rootapへdispatchする（pc1049〜1053）。write/tmp_write/tmp_write_onoffは別callbackであり、今回追加する観測はtmp_readだけを使用する。

tmp_read_rootapは既存STA設定をreadし、profileのwireless_sta_2g/5g（なければ空文字）を用いてApcfg.get_root_ap_statusを呼ぶ。model/39はiwinfoから対象interfaceのBSSID、channel、signal、assoclist等を読む。callbackはさらにonline-testを呼び、その終了値をinternet_statusへ変換する。従って設定を書き込むoperationではないが、ルーター内のオンライン確認処理も伴う。

最新公開profileにはwireless_sta_2g/5gがなく、wireless_sta_config_2g/5gのみがある。get_profile（uci/8）はinst_profile:get_firstから値を読み、on/offと型を変換する。確認した範囲に別名へのfallbackはない。実機profileのmergeや補完は未確認である。

tmp_readの成功だけでassociationを判定しない。BSSIDの非zero値の有無、signalの0〜3、channelの0〜233、internet_statusの固定値だけを記録する。個体BSSID/SSID/PSKや未知field値を保存しない。BSSIDありでも設定した親機との一致は未証明、signal=0でも未接続とは断定しない。

`python -m tools.probe_sta_config --apply --source-ip 192.168.1.52 --security wpa3-transition --probe-link` は次の順で動く。

1. 通常認証、管理IP/DHCP/STA設定の前提確認。
2. tmp_readを一度要求。失敗時はSTA write前に停止しlogout。
3. 既知5GHz setterを適用・readback。
4. 45秒待ち、tmp_readを一度要求。失敗してもfinallyでdisableと開始時設定への復元。
5. 復元readback後にtmp_readを一度要求しlogout。復元後の観測失敗はrollback成功と分けて記録。

PCのIP、route、lease、ルーターのAP/modeは変更しない。IPv4/IPv6観測との同時指定は拒否する。秘密は既存の非表示promptからのみ入力する。

ユーザーの2026-10-07の指示により、以後は`--keep-enabled`を指定して設定readback成功後のSTAを有効のまま維持する。観測失敗時も無効化しない。write応答喪失や設定readback不一致の場合だけ復旧のためrestoreする。通常の限定probeは従来のrestore既定動作を残す。

最初のtmp_read観測は有効前・45秒後・復元後ともsignal_2g/5g=0、internet_status=disconnected。BSSID/channelは返らなかった。tmp_read要求・設定readback・rollback/logoutは成功。local-evidence/sta-probe-20261007T050639662897Z.json。profile依存があるのでassociation失敗とは断定しない。

## 純正システムログの読み取り

公開syslog controller（SHA256 f16f482af82e3231e677320fb6590768027059e77567a1fae934a2aa176bc035、6,355 bytes）のpc209〜213はform=log / operation=loadをread_logへdispatchする。read_logは既存filter/localeを読み、logreadのrowsを返す。filter変更・ログ削除・保存archive生成・メール送信は別callbackで、今回使用しない。

`python -m tools.read_sta_diagnostics --source-ip 192.168.1.52` は通常認証でSTA設定read、tmp_read、`/admin/syslog?form=filter`のread、`/admin/syslog?form=log`のoperation=load、logoutだけを行う。filterは全type/全levelかというboolだけを記録。STAを再適用・無効化しない。HTTP上限64KiB/timeout5秒は従来clientと同じで、超過や未知構造は停止する。

ログ本文はRAM内で分類し、公開reportにはrow数とapcli/supplicant/association/authentication/disconnection/failureの語に合致した件数のみ保存する。SSID/PSK/MAC/IPや自由文は保存しない。件数は現在のfilterとログ期間に依存するため、0件でもdriverエラー不存在とは断定しない。association語は接続成功・失敗を区別しない。必要に応じて確認済みの特定エラーを固定ラベルで分類する。
