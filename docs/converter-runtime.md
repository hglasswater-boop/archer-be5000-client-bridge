# Ethernet Converter実機切り分け

## 20:03〜20:17 JSTの再開後比較

ユーザーが親機EasyMeshをoffにした後、PC scanで接続先2g channelが5から4に変わっていた。11:08Z、既知radio setterでchannel4へ合わせ、保存STA設定一致を確認。Ethernet OFFERなし、Wi-Fi対照あり。

2g AP一時onの比較は、最初channel5、次に親機と一致するchannel4で実施。channel4の試験ではPC scanに保存AP名と親機がともに現れ、ユーザーもWi-Fi LED点灯とAP名の出現を確認した。親機無線端末一覧には現れないとの観測で、Ethernet OFFERもなし。さらにSTA off/onをreadbackで確認した試験でも同じ結果。BE5000だけMeshを一時onにし、STA off/onをした比較でも親機には現れず、Ethernet OFFERなし。

各比較後にAP offをreadback。最後の11:17Z比較はMesh off、通常両band AP off、disabled_all off、STA2g on/5g off、保存設定維持を確認しlogout完了。channel2gは4を保持する。比較toolは`tools/probe_ap_sta_2g.py`、`--restart-sta`と`--probe-mesh-start`は通常設定での一時比較を追加する。原則として親機設定は変更せず、試験終了時はMesh/AP off、STA onを検証する。

公式JP QIGでは電源の下から2.4GHz、5GHzのWi-Fi LEDで、機能動作時の点灯と説明される。LED点灯を親機へのassociation完了と扱わない。[公式ガイド](https://static.tp-link.com/upload/manual/2025/202507/20250718/7100000076%20Archer%20BE260-5000-3600%20Pro(JP)_QIG_V1.pdf)。

AP側の動作は観測できたがSTA接続は未成立のため、次は実機supplicant状態と起動/reconnect処理の観測を優先する。[カスタム化候補と投入前の確認](sta-customization-plan.md)。

## ユーザー指定の2.4GHz比較

06:50Zにユーザーが再指定したWi-Fiキーをhidden入力で比較し、保存済み2gキーと既に一致していたことを確認。既知7 fieldで再適用・readback成功、Ethernet OFFERなし（Wi-Fi対照あり）。管理用passwordとは別に扱い、値はコード/ファイル/reportへ保存しない。

06:47Zの3 field BSSID固定要求と、06:51Zの保存SSID/security/keyを含む要求はともに失敗応答。後者の同一session診断でlocktoap_2g=off、STA2g on/5g off、Mesh off、通常AP両band off、disabled_all offを確認。BSSID固定が成立したとは扱わない。

06:53ZにPCの更新scanで保存対象の2.4GHz/channel 5を選び、wireless_2gの通常writeへform、wireless_2g_channel=5、wireless_2g_enable=off、wireless_2g_disabled_all=offを指定。公開model pc0414〜0418はchannelをradio cfg/actへmappingし、controller/wireless_predefined_formsはbody formでApcfgを選ぶことを静的確認した。channel/AP/radioのreadback後にSTAの保存済み7 fieldを再適用、保存一致を確認した。Ethernet OFFERなし、Wi-Fi対照あり。channel 5は保持する。

06:54Zの読取り診断は2g survey成功0件、tmp_read信号0/internet_status disconnected、wireless_connect_status APIはHTTP response rejected。後者はSTA ifname profileとwpa_cliに依存し、tmp_readのprofile依存とは別。PCで対象APが見えるためsurvey 0をAP不在と扱わず、これらのAPI結果からassociation失敗も確定しない。

`python -m tools.update_sta_2g_key` は指定済み2g対象へローカルhidden入力のWi-Fiキーを反映する。`--align-scan-channel` はキーを新規入力せず、保存済みWPA2設定を保持し、PC scanの対象channelへradioを合わせる。いずれも通常login一回でSTA readback、DHCP観測、Mesh/両radio/link/log診断、logoutを行う。`pin_sta_target --diagnose-after`も同じsession内で成功・失敗後の診断を行う。passwordの永続保存はしない。

ユーザーが通常2.4GHz SSIDへの接続を指定。現在の5GHz STAをoff、2.4GHzをonとする既知rootap setterを一回要求する。rootap_2gは同じenable/ssid/encryption/psk_version/psk_cipher/psk_key mappingを持ち、WPA2/AESを使う。Wi-Fi鍵は現在の5GHz保存値をRAM内で引き継ぎ、他のパスワードを推測しない。Mesh/AP/管理LAN/DHCPは変更せず、両bandの有効状態と2.4GHzの6 fieldをreadback後にDHCP観測する。失敗でも通常終了時の復元は行わない。2.4GHzで成立しても当初の5GHz性能要件と区別する。

06:30Zのwrite/readbackで2.4GHz STA on、5GHz STA offを確認。PCのWlanScanを明示的に要求すると通常2.4GHz AP/WPA2/channel 5と試験5GHz APが見えた。Windowsのnetsh一覧が見えない状態はキャッシュ/scanタイミングの影響もあり、SSID消失を断定しない。2.4GHz試験もEthernet OFFERなし（Wi-Fi controlあり）。BSSID指定toolへ--band 2gとWlanScan更新を追加し、SSID一致とprimary Bandの一致を要求する。colocated APのBand/Channelを選択に使わない。

## 通常認証からのローカルSSH診断

公開administration controllerのform=login/operation=app_user_agreeはlogin_update_ssh_enableへdispatchする。ssh_is_enable=1はREMOTE_ADDRだけをknock_functions.sh addへ渡し、accountmgnt.admin.ssh_is_enable=1を保存する。パスワード・ユーザー名・WAN remote設定は変更しない。公開dropbear設定はPort=20001、SysAccountLogin=off、PasswordAuth=on。Web管理と同じ認証からPC 192.168.1.52だけのSSH許可を要求し、その後に既存管理パスワードによる通常SSH認証を一回試す。APIや認証の失敗を突破するためのパスワード推測は行わない。

GPL dropbear/src_2019_78ではsessionEnableの既定値=0、起動option -Lだけが1にする。最新公開initでは-Lを追加する処理がコメントアウトされている。sessionEnable=0のときPTY/shellを拒否し、execは固定SCP commandだけを許可して末尾をNULで切る。最新公開binaryの許可SCP対象は3G/フィルター/画像ファイルで、STA状態や任意コマンドではない。これが実機の認証後拒否と整合する。SSH認証成功をshell取得と扱わない。公開binary SHA256: 29bffb8827817939310da3fccc455b5d2079b9c5495e007e9accde1182dd33c9。

PCの接続確認で実際のMLO接続先はWPA3-Personal(H2E)、5GHz channel 124/6GHz channel 69。通常SSIDの比較候補はPCの一覧では見つからなかった。公開rootap mappingはencryption=psk_saeとpsk_version=sae_onlyを許す。wifixにはsae_pwe=2とieee80211w=2が存在する。従来のWPA2/WPA3混在と区別してWPA3専用候補を一回適用し、保存設定・IPv4 DHCPを観測する。MLO client機能やSAE交渉成功はこの設定から推定しない。

目標は通常5GHz STAから有線LANへのIPv4転送。Mesh不要という要件に沿って、通常認証の既知EasyMesh設定APIでenable=offを保存し、保持中の通常STAを6 fieldだけ再適用する。FW・PCのIP/route・管理LAN/DHCP・AP設定はこの段階で変更しない。APIが成功しても通信成立とは扱わない。

公開write_easymesh_settingsはonemesh/meshdのenableを更新し、masterの場合にwifi onemesh、meshd stop、apsd_mesh_switch offを呼ぶ。後者はapsd/tpbrのstopで、tpbrctl detach br-lanを伴う。Linuxのbr-lan削除や管理IP/DHCP変更をこのcallback内では確認していない。ただし一時通信断はあり得るので、有線管理をreadbackで確認する。STAの保存値が維持されてもradioの実動作が変わる可能性があり、既知setterを一回再適用する。

実施順はrouter mode、192.168.1.1、DHCP off、5GHz STA on/2.4GHz offを確認→Mesh offを一回write→15秒待ち→Mesh/LAN/DHCP readback→開始時6 fieldを一回write→15秒待ち→STA readback→IPv4 DHCP DISCOVER/OFFER観測→logout。個体のSSID/PSKはRAMのみ、reportは固定ラベルとboolのみ。失敗時も自動でMesh on/STA offへ復元せず、最後に確認できた状態を残す。

追加の`--probe-radio`は既知wireless_2g/5gのreadを使用し、各bodyにformを明示して両bandのAP/radioのenable/disabled_all/channelを限定取得する。STA設定も両bandをsanitizeし、SSID/PSKは存在形態だけを記録する。APのSSID・鍵や未知値をreportへコピーしない。AP停止とradio停止は別なので、getter結果のfield名を維持する。

`configure_converter --apply-mesh-off --disable-aps`はwireless_2g/5gの既知writeへform、wireless_<band>_enable=off、wireless_<band>_disabled_all=offを送る。公開mappingでは5GHz enableはAP用cfg=3/act=VAP、STAはcfg=13、radioはcfg=19で別。controllerはdisabled_allが要求に**ない**場合にenableから補完するため、AP offではradio停止のonへ補完される。Lua TESTの分岐を読み違えた初回2.4GHz要求でこの条件をreadback guardが検出し、5GHz変更前に停止した。radio維持にはdisabled_all=offの明示が必要であり、修正した。各APのoffとdisabled_all=offをreadback後、保持STAを再適用し管理LAN/DHCP/STAを照合する。MLO/guest/backhaulの全BSS停止は別途確認が必要。

## 2026-10-07実機結果

- 06:37Z: 公開管理API取得も失敗。PC有線IPv4は169.254.149.145、管理用192.168.1.52へのsocket bindはWinError 10049。認証前のPC側アドレス問題を確認した。06:34Zの失敗時点のIPは観測していないため、同じ原因だったと断定しない。
- 06:38Z: ユーザーが有線固定IPを再設定後、192.168.1.52をsourceにした公開feature preflightが成功。管理アクセスの復旧と、STA association・LAN転送は別に判定する。
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
