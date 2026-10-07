# STAの起動と接続開始の境界

2026-10-07の公開FW静的解析と通常認証APIのread。実機STAは通常SSID/WPA2で有効維持し、今回のMesh診断では設定変更を行っていない。

## 確認できた経路

| 処理 | 公開FWの根拠 | 意味 |
| --- | --- | --- |
| STA section | 公開default-configのwifi-iface apclii0: ifname=apclii0、device=wifi1、mode=sta | 5GHz STA定義は存在する |
| mode取り込み | wifixのdescriptor 0x44bdb8: mode → struct+0x40、converter 0x410e7c | 起動条件のfieldを特定 |
| mode変換 | table 0x44a438、100 byte stride: ap=0、sta=1、adhoc=2、monitor=3、mesh=4 | init_vapのmode=1はSTAを意味する |
| update応答 | 0x40ebcc〜0x40ec58 | 内部updateの戻り値を判定せずsuccessを返信 |
| STA選択 | mtk_update_vap 0x42a430、find_vap_by_name 0x412210 | section/ifnameを大文字小文字無視の全長一致で検索 |
| radio再読み込み | 0x42a5d4〜0x42a5dc | 通常のSTAは所属radio名をreload_radioへ渡す |
| 無効化時の処理 | init_vapのstruct+0x48=false分岐、0x424a2c〜0x424bb0 | bridge detachとsupplicant remove等を行い、driver設定前にreturn |
| STA driver設定 | 0x425f54〜0x425f68 | mode=staのときconfig_wds_settingを呼ぶ |

extract_vap 0x413d38はUCI sectionの各optionをdescriptorに従ってstructへ変換する。config_init_vapsはwifi-iface sectionを読み、device名からradioへリンクする。config_link 0x414a08〜0x414a38はmode=1のVAPをbandごとのSTA slotへ置く。start_interface 0x427388〜0x4273dcはこのSTA slotに対してinit_vapを呼ぶ。実機のmode/device/slot値は未取得なので、この経路の実機到達はまだ証明していない。

## 接続開始を別処理に任せる候補

公開/etc/init.d/wifixは/lib/wifi/wifix_profile.iniを指定する。同profileのWLAN/FEATURE_HOSTAPD=yはwifi_init_profile 0x405100〜0x40510cでglobal+0x571=1に変換される。

init_vapの0x424bb4〜0x424c00はそのflagが有効でmodeがAP以外なら、wpa_supplicant_setup_vifとwpa_supplicant_enable_vifを呼ぶ。後者（0x416a8c）は生成済みconfが存在する場合に、以下の順で処理する。

1. global controlへinterface_add（0x416b64〜0x416b68）。
2. 対象interfaceのscan_intervalを30に設定（0x416c00〜0x416c04）。
3. 対象interfaceへ**disconnect**（0x416c90〜0x416c94）。

これらのsystem戻り値は既存helperで無視される。confがない場合も関数は0で終了する。このdisconnectはログ文字列だけでなく、実際にhelperを呼ぶ命令列まで確認した。

ただし、init_vapはその後0x425f68でconfig_wds_settingへ進み、ApCliEnable=1を設定する。このため、disconnectの存在だけで現在の実機が切断状態だとは断定できない。supplicantとdriverの処理順・実行結果・再接続指示の実機確認が必要である。

reload_radioは後続でmeshd.wifi_reload_completeイベントを送り、pidof meshdが空ならmeshdをstop/startする。公開meshdにはwpa_cli disconnect/reconnect双方の処理があり、mtk_reconfigSTAはsupplicantのSSID/PSK/SAE passwordを書き換えてreconfigureする。通常STA setterが、このMesh側の接続開始指示まで誘発するかは未確認。公開default-configではapclii0のmesh=onであり、通常STAとの共用を調べる根拠になるが、実機のmesh値と daemon状態は未取得である。

## Mesh側の再接続条件と実機read

2026-10-07 05:45:42 UTC、既知の `/admin/easymesh?form=easymesh_enable` のreadで **enable=on** を取得し、同じ診断で5GHz STA=onとlogout完了を確認した。公開Luaのread_easymesh_settingsはmeshd.meshd.enableを読み、設定を書かない。取得結果から保存された有効設定は確認できるが、daemonの稼働・role・association成功は判定できない。tmp_readは引き続きsignal=0 / internet_status=disconnectedで、純正ログ48件にも接続成否を判定する情報はなかった。

公開meshdの経路を次の範囲まで確定した。

| 処理 | 根拠 | 条件・限界 |
| --- | --- | --- |
| band別の再接続 | meshd_bmap_reconnect_sta 0x416f5c | 要求band maskをsupport_band_bmap（config+0x880）とANDし、対象STA名ごとに0x423090を呼ぶ |
| platform callback | global 0x4454a0の初期値=0x445390、callback+0x30=0x404148 | 0x423090はこのcallbackを呼ぶ。公開binaryの初期tableではmtk_connectへ直接到達する |
| 接続指示 | mtk_connect 0x404148、system 0x404194 | 対象interfaceへwpa_cli reconnect。systemの成否は無視し1を返す |
| 接続先選択 | meshd_scan_match_monitor 0x41a098〜0x41a124 | select_band_bmapとconnect_band_bmapが異なると、そのXORを再接続へ渡す |
| node情報との照合 | meshd_check_nodeid内0x418354 / 0x418724 / 0x418794 / 0x4187f4 | vendor IE/nodeid処理から再接続を呼ぶ。一般APに対する全分岐の適用条件は未確定 |
| radio完了イベント | handler 0x415c90 → 0x415ad4 | STA設定の再読込後、role=agentなら追加処理へ進む。完了イベントからの無条件reconnectではない |
| role取得 | 0x40ce88〜0x40cea4 | UCI meshd.meshd.roleを読む。読めない場合agent扱い。公開defaultもagentだが、実機roleは未取得 |

callback+0x28には別途disconnect→sleep(1)→reconnectの0x4041a4がある。上記band再接続は+0x30であり、このsleep付き経路と混同しない。

公開/etc/meshd_cfg.jsonはscan_before_connect_enable=trueで、apcli0/apclii0をそれぞれ2.4g/5gのbSTAとして定義する。JP向けmeshd_cfg_be260v1_jp.jsonにも同じSTA割当がある。実機が使用したJSONやruntime band maskは未取得。onemesh.onemesh.role=masterは別設定であり、meshdのrole判定には使わない。

この結果、単にEasyMeshがoffだから再接続しないという説明は現在の保存設定と合わない。通常STA setterからMeshの接続先選択・band再接続へ到達するかが次の調査対象である。driver enable後の接続成否は依然不明で、静的経路だけで障害原因を確定しない。disconnect/reconnect、radio reload、Mesh停止を実機で直接実行していない。

読み取り診断は `python -m tools.read_sta_diagnostics --source-ip 192.168.1.52 --probe-mesh` で実行する。Mesh routeへのwriteは許可せず、出力はenableのon/off/unavailableに限定する。76件の単体テストが成功し、未知値の非公開化・Mesh write拒否・後続診断失敗時のSTA維持/logoutも確認した。個体の診断JSONはignored local-evidenceに保持する。

## 公開ファイルのSHA256

- /usr/bin/wifix: 342ef2ffd55ec431796ac7bc6015c5893ce416bf0b2de9c8e670bd9ba82cdc06
- /usr/bin/meshd: 125f605392900e429cb7c83c2ac75450807786ba9824fab44fb5a6ea6284afd1
- /etc/init.d/wifix: f52fdffbf3bc2ca299ec9530eb461d1fa59a2806979c20398a44968a85a4df05
- /lib/wifi/wifix_profile.ini: 1e3f0ea9725eef4b9e38c8dfdb06f07a1544468afacde12417ad1088d98b47d3
- /etc/partition_config/default-config（公開暗号化データ）: a75a3c3a23144ddbb2a44b6a5732f5929ca945ab3d6b04d70032bb309e886e1f
- 同公開データの展開後: ee67627ad6497b2cdeccca48ff5c8f026853d50e74689edf8b3e364bf2eb6ae6
- /etc/meshd_cfg.json: c6b115abcd657fdb66690451c648bfd2e8407254dd0a3adf21d7c0b02d3124e3
- /etc/meshd_cfg_be260v1_jp.json: a953727275fabc89c16f7fa3cd7dbb5d7951e2c3cb6c7ff162ba6bbf7315fff3

default-configは公開GPLのencryptCfg定義を用いて復号・zlib展開した公開FWのデータであり、実機バックアップではない。全文はXML構文エラーを含むため、対象wifi-ifaceの範囲を単独XMLとして解析した。個体の設定・SSID/PSK・session情報はこの資料に含めない。元binary、展開全文、全命令listingはignored artifacts内に保持する。
