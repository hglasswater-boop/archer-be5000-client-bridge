# STAの起動と接続開始の境界

2026-10-07の公開FW静的解析。実機STAは通常SSID/WPA2で有効維持したまま、この解析では実機への要求・設定変更を行っていない。

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

**次の切り分け対象:** Mesh側のreconnect呼び出し条件、通常STAへの適用条件、既知の通常認証APIで観測できる範囲。disconnect/reconnect、radio reload、Mesh停止を実機で直接実行していない。

## 公開ファイルのSHA256

- /usr/bin/wifix: 342ef2ffd55ec431796ac7bc6015c5893ce416bf0b2de9c8e670bd9ba82cdc06
- /usr/bin/meshd: 125f605392900e429cb7c83c2ac75450807786ba9824fab44fb5a6ea6284afd1
- /etc/init.d/wifix: f52fdffbf3bc2ca299ec9530eb461d1fa59a2806979c20398a44968a85a4df05
- /lib/wifi/wifix_profile.ini: 1e3f0ea9725eef4b9e38c8dfdb06f07a1544468afacde12417ad1088d98b47d3
- /etc/partition_config/default-config（公開暗号化データ）: a75a3c3a23144ddbb2a44b6a5732f5929ca945ab3d6b04d70032bb309e886e1f
- 同公開データの展開後: ee67627ad6497b2cdeccca48ff5c8f026853d50e74689edf8b3e364bf2eb6ae6

default-configは公開GPLのencryptCfg定義を用いて復号・zlib展開した公開FWのデータであり、実機バックアップではない。全文はXML構文エラーを含むため、対象wifi-ifaceの範囲を単独XMLとして解析した。個体の設定・SSID/PSK・session情報はこの資料に含めない。元binary、展開全文、全命令listingはignored artifacts内に保持する。
