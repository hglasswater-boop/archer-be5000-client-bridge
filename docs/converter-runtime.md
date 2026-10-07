# Ethernet Converter実機切り分け

## 通常認証からのローカルSSH診断

公開administration controllerのform=login/operation=app_user_agreeはlogin_update_ssh_enableへdispatchする。ssh_is_enable=1はREMOTE_ADDRだけをknock_functions.sh addへ渡し、accountmgnt.admin.ssh_is_enable=1を保存する。パスワード・ユーザー名・WAN remote設定は変更しない。公開dropbear設定はPort=20001、SysAccountLogin=off、PasswordAuth=on。Web管理と同じ認証からPC 192.168.1.52だけのSSH許可を要求し、その後に既存管理パスワードによる通常SSH認証を一回試す。APIや認証の失敗を突破するためのパスワード推測は行わない。

GPL dropbear/src_2019_78ではsessionEnableの既定値=0、起動option -Lだけが1にする。最新公開initでは-Lを追加する処理がコメントアウトされている。sessionEnable=0のときPTY/shellを拒否し、execは固定SCP commandだけを許可して末尾をNULで切る。最新公開binaryの許可SCP対象は3G/フィルター/画像ファイルで、STA状態や任意コマンドではない。これが実機の認証後拒否と整合する。SSH認証成功をshell取得と扱わない。公開binary SHA256: 29bffb8827817939310da3fccc455b5d2079b9c5495e007e9accde1182dd33c9。

PCの接続確認で実際のMLO接続先はWPA3-Personal(H2E)、5GHz channel 124/6GHz channel 69。通常SSIDの比較候補はPCの一覧では見つからなかった。公開rootap mappingはencryption=psk_saeとpsk_version=sae_onlyを許す。wifixにはsae_pwe=2とieee80211w=2が存在する。従来のWPA2/WPA3混在と区別してWPA3専用候補を一回適用し、保存設定・IPv4 DHCPを観測する。MLO client機能やSAE交渉成功はこの設定から推定しない。

目標は通常5GHz STAから有線LANへのIPv4転送。Mesh不要という要件に沿って、通常認証の既知EasyMesh設定APIでenable=offを保存し、保持中の通常STAを6 fieldだけ再適用する。FW・PCのIP/route・管理LAN/DHCP・AP設定はこの段階で変更しない。APIが成功しても通信成立とは扱わない。

公開write_easymesh_settingsはonemesh/meshdのenableを更新し、masterの場合にwifi onemesh、meshd stop、apsd_mesh_switch offを呼ぶ。後者はapsd/tpbrのstopで、tpbrctl detach br-lanを伴う。Linuxのbr-lan削除や管理IP/DHCP変更をこのcallback内では確認していない。ただし一時通信断はあり得るので、有線管理をreadbackで確認する。STAの保存値が維持されてもradioの実動作が変わる可能性があり、既知setterを一回再適用する。

実施順はrouter mode、192.168.1.1、DHCP off、5GHz STA on/2.4GHz offを確認→Mesh offを一回write→15秒待ち→Mesh/LAN/DHCP readback→開始時6 fieldを一回write→15秒待ち→STA readback→IPv4 DHCP DISCOVER/OFFER観測→logout。個体のSSID/PSKはRAMのみ、reportは固定ラベルとboolのみ。失敗時も自動でMesh on/STA offへ復元せず、最後に確認できた状態を残す。

追加の`--probe-radio`は既知wireless_5g/readを使用し、5GHz AP/radioのenable/disabled_all/channelだけを限定取得する。APのSSID・鍵や未知値をreportへコピーしない。AP停止とradio停止は別なので、getter結果のfield名を維持する。

`configure_converter --apply-mesh-off --disable-aps`はwireless_2g/5gの既知writeへform、wireless_<band>_enable=off、wireless_<band>_disabled_all=offを送る。公開mappingでは5GHz enableはAP用cfg=3/act=VAP、STAはcfg=13、radioはcfg=19で別。controllerはdisabled_allが要求に**ない**場合にenableから補完するため、AP offではradio停止のonへ補完される。Lua TESTの分岐を読み違えた初回2.4GHz要求でこの条件をreadback guardが検出し、5GHz変更前に停止した。radio維持にはdisabled_all=offの明示が必要であり、修正した。各APのoffとdisabled_all=offをreadback後、保持STAを再適用し管理LAN/DHCP/STAを照合する。MLO/guest/backhaulの全BSS停止は別途確認が必要。

## 2026-10-07実機結果

- 05:53Z: survey_5gの成功応答は空Lua table（JSONの{}）。0件として処理。設定変更なし。
- 05:56Z: Mesh off保存・readback、管理LAN/DHCP確認、通常STA再適用に成功。Ethernet OFFERなし、Wi-Fi control OFFERあり。
- 05:59Z: 実際にPCで接続したMLO SSIDへWPA3専用候補を適用・readback成功。STA有効維持、Ethernet OFFERなし。
- 06:02Z: radio getterのbodyへform=wireless_5gを指定してAP enable=on/disabled_all=off/channel=autoを取得。form省略の空結果をradio停止と解釈しない。
- 06:06Z: 初回2.4GHz AP offでdisabled_allの補完をreadback guardが検出し停止。06:08Z、明示disabled_all=offで両帯域AP offとradio維持、STA onと管理LAN/DHCP offを確認。Ethernet OFFERなし、Wi-Fi control OFFERあり。個体reportはlocal-evidence/converter-20261007T060834951968Z.json。
- 06:10Z: 通常認証SSH許可APIはsuccess応答後に20001/TCPが開いた。callback boolがJSON data={}へ変換されたため初回toolはunexpected valueで停止したが、待受けが開いた事実を確認し、toolの成功判定を修正。SSH bannerはdropbear_2019.78。管理パスワードでの認証後、exec/PTY/shell要求が拒否された。shellは取得していない。

公開wifixのsupplicant設定生成0x416330〜0x416344はtp_mesh_enable=1を無条件で書く。Mesh設定offからこの行が消えるという推定はしない。この生成関数にはsae_pwe設定の書き込みが見当たらず、別のhostapd側にはsae_pwe=2がある。STAのH2E交渉可否はcompiled defaultも関係するため未確定。

通常5GHz/WPA2/空白なしSSIDをユーザーが準備中。現在のMLO専用接続先の条件とSTA接続開始の問題を分けるための試験である。設定成功をEthernet Converter成立と扱わず、IPv4転送・NATなし・全AP停止・複数LAN端末・NAS・安定性は未合格。

## 実在5GHz APへのBSSID指定

06:21Z、PCで試験SSIDの存在とWPA2-Personalを確認し、通常STAへ適用・readback成功、Ethernet DHCP OFFERなし。次にWindowsのscan結果から保存SSIDに一致しband=5 GHzのBSSIDだけをRAMで選ぶ。公開rootap mappingのbssidはraw option、locktoapはon/offで、controllerの空BSSID補完はlocktoap=offの場合だけ。既知STA routeのwriteへenable_5g=on、bssid_5g=<選んだMAC>、locktoap_5g=onを一回要求する。SSID/PSK/暗号方式を変更せず、BSSID文字列をreportへ保存しない。readbackの一致・STA維持を照合し、失敗でもSTA offへ戻さない。これはassociation成功ではなく、保存BSSIDと選択条件の比較である。

06:23ZのBSSID指定toolは、その時点のWindows scanに対象5GHz BSSIDがなく、write前に停止/logoutした。その後のscanにも試験SSIDは見つからなかった。親機側準備中の試験なので、安定して存在するAPへの接続を検証し終えたとは扱わない。最後の受理済みSTA設定は通常試験SSID/WPA2/on、locktoap=offのまま。
