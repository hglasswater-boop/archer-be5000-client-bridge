# Runtime configuration investigation

2026-10-07。BE700は通常APとして扱い、BE5000側の通常STA + 複数LAN端末転送を先に調べる。

## 調査の順序

1. Web UIの全設定backupとsystem logを取得し、個体情報を含むためlocal-evidence/へ保存する。
2. 最新公開rootfsのwireless / sysmode / wifix / 管理アクセス設定を静的に読む。製品binary/scriptをホストで実行しない。
3. 認証済みの設定経路と、有線管理・再起動rollbackが成立する場合だけruntime PoCを設計する。
4. setterの挙動・入力値・依存性を確認し、実行前に試験とrollbackを資料化する。未知APIに変更要求を送らない。

## 実機の記録

全設定backupのUIは、種類選択後に新しい暗号化passwordを要求する。password作成はユーザー操作に引き継いだ。保存完了とファイルを確認するまでbackup取得済みとは扱わない。
Web UIの設定backupはflash full dumpやbrick recoveryではない。実機ログはfirmware内のstatic設定やstringsと区別する。

ユーザーが保存した全設定backupを2026-10-07に確認した。35,392 bytesで、local-evidence/のcopyと元fileのSHA256が一致。
個体backupの本文・hash・passwordは公開資料へ含めない。ルートに置かれた元fileも/router-backup-*.binでgitignoreした。
復元は実施しておらず、復元成功を確認したbackupという意味ではない。

System Logの「すべて」を画面から読み取り、local-evidence/system-log-visible.txtへ保存した。
nativeの「ローカルに保存する」downloadは完了eventと保存fileを確認できなかったため、取得したものは**表示本文の転記**として区別する。
内容はNAT / firewall / DHCPC等の起動記録が中心で、driver / kernel / STA forwarding状態は得られない。
ルーター時刻が2026-04-20のため、log内timestampを実際の収集日2026-10-07と混同しない。

認証済みUIの「管理」はpassword変更・回復、HTTP(S)ローカル管理、リモート管理の項目。SSH enable項目は見当たらない。
PC有線source IPへbindしたTCP20001の接続は2秒でtimeout。以前の22/23 timeout、80/443 openとは別に記録する。
timeoutはservice不在の証明でも、firewallのREJECT動作の証明でもない。

## 公開FWの検証方針

Lua5.1 bytecodeのconstantsやfunction名だけでは、setterの実行条件や暗号・認証条件を確定しない。
管理経路を調べる際、SSH executableの存在・port到達・shell権限・製品CLIに限定されたsessionを区別する。
MAC変換 / virtual STA / proxyの実装と、DHCP・ARP・IPv6 ND/RA・multicastの対応範囲を別々に確認する。
profileの共通機能名・frontendの共通componentをBE5000で利用できる機能と同一視しない。

## 最新JP rootfsの追加結果

sourceは既に署名・UBI CRCを検証した最新配布物のvolume-2。追加path/hashは[evidence/runtime-paths.json](evidence/runtime-paths.json)。
vendor fileを実行せず、選択読み取りとASCII文字列の抽出を行った。

| Path | 確認結果と意味 |
| --- | --- |
| /sbin/wifi | wifixが存在するbranchではvap/hostapd/mldをubus wifix updateのvnameへ、modeをrnameへ渡す。startup / reloadもwifix制御。**down専用caseはコメント化され、wildcard reloadへ入る**ため、一般的なwifi downをAP停止手順として使用しない |
| /usr/bin/wifix | ELF内にApCliEnable / ApCliSsid / ApCliBssid / ApCliAuthMode / ApCliWPAPSK、config_wds_setting、repeater、ubus update/mode/cfgの文字列。STA接続処理の候補は最新binary内にもある。ApCliMeshRule=1もあるため、通常STAとmeshの分岐・実行条件を追う必要がある |
| /lib/wifi/config_model.json | 5GHzを含むSTA_VAP定義にvifname、enable、rootapssid。設定model候補であり、認証済み外部setterの存在を証明しない。配布fileにはJSONとしてcomma欠落があり、parser failureを実機wifix故障と扱わない |
| /sbin/netifd_wireless_cmd | 有効wireless VAPのifnameをWAN/WANv6へ設定してinternet reloadするhelper。routed wireless WAN経路であり、目標LAN bridgeの証拠ではない |
| /usr/lib/lua/luci/controller/admin/wireless.lua | Lua bytecode内にwireless_sta_2g / wireless_sta_5g / sta_connect_rootap_status / repeater。method名の存在だけでBE5000のUI公開、setter条件、認証方式を確定しない |
| /usr/lib/lua/luci/model/wireless.lua | Lua bytecode内にwds_status / get_wds_status / repeaterとmesh関連呼出し。通常STAの独立性を追う対象 |
| /sbin/knock_functions.sh | TCP20001のREJECTとclient単位ACCEPTを扱う。ただし**gdpr_hmac_sign=yesまたはcountry=SGの場合に限定**されるscript。JP実機への適用、listen service、認証手順は未確認 |
| /etc/init.d/dropbear | Port既定22、SysAccountLogin条件、knock scriptの呼出し。実機の生成設定・起動引数・login権限は未確認。20001が実際のSSH portとは断定しない |

## 次の実機試験へ進める条件

GPL内のLua loader / opcode定義を追加取得した。loaderのheader末尾4はLNUM_INT32の整数幅、string長はunsigned int。
命令番号も標準Lua5.1と異なり、GPLはGETTABLE=0 / GETGLOBAL=1 / LOADK=8 / CLOSURE=33 / CALL=34。
標準disassemblerの出力をそのまま使わない。次の静的読み取りはこれらの定義で、合成chunkと末尾位置一致を検証してからfunction単位のconstants/命令を調べる。
このGPLと最新FWの完全対応は未証明のため、解釈した命令と実機動作は別に扱う。

追加の限定readerをartifacts/で使用した。合成chunkのstring/int読み取り、truncation・trailing data・過大countの拒否を先に確認。
最新controllerは161 function / 123,433 bytes、modelは149 function / 94,243 bytesで、末尾まで一致して読めた。
readerはLuaを実行しない。function所属と命令の解釈は、source上の定義と選択callsiteの手動照合を行った範囲に限定する。
全disassemblyを公開せず、判定に必要な処理名と原file/hashを記録する。

静的callsiteから次の連鎖が候補として追えた。

```text
wireless_connect_to_network.read  -> read_rootap
wireless_connect_to_network.write -> write_rootap
tmp_write_rootap                  -> write_rootap
write_rootap                      -> Apcfg({rootap_2g, rootap_5g, wireless_2g, wireless_5g}):write(...)
```

これはcontroller内のdispatch table名であり、実機で受理されたHTTP URL/APIではない。
tmp_write_rootapはenable_5g / ssid_5g / bssid_5g / encryption_5g / psk_key_5g等を処理し、pskをAES/RSN、psk_saeをsae_transitionへ変換する。
read_rootapはprofileのwireless_sta_5gを取得し、Apcfg:get_root_ap_statusを呼ぶ。sysmodeのclient / repeater / hotspot分岐もある。
共通binaryの分岐なので、BE5000のmodeをclientへ変更できる証明ではない。

**Apcfg.writeにはcommitが含まれる。** write_rootapをRAMだけの一時setterと扱わない。
modelのwriteにはmesh関連operation / sysmode / profile条件によるwifi reloadやswitch_mode rtorの分岐がある。
単純なwriteを実行してから副作用を確かめる方法は採らず、section mapping・apply条件・認証dispatch・復元経路を先に追う。

1. controller / model / wifixの処理を追い、JP/1.0の通常STAを設定できる認証済み経路と必要な入力を確定する。
2. 有線管理を維持し、変更前のruntime状態を読み取れることを確認する。backupの存在だけでこの条件を満たしたとは扱わない。
3. 一時変更とrollbackを先に資料化・確認し、5GHz associationのみから始める。AP停止、LAN転送、DHCP停止は独立した段階で実測する。

現段階では未確認setterへの要求、firewall解除、無認証login、flash変更は実施していない。
バックアップ取得は完了したが、Client Bridge実機PoCはNOT RUNのまま。

## 追加調査: Web API / 機種profile / apply条件

次に公開rootfsのfrontend圧縮JSとLua dispatchを選択読み取りする。JSを実行せず、gzip単体4MiB・総量32MiBの上限で読む。
ConnectNetworkRepoは/admin/wireless?form=wireless_connect_to_networkのread/writeを使う。機種対応は画面部品の存在とは別に確認する。
最新rootfsの/etc/partition_config/profileは本文がplaintextではない。GPLのbe260v1/common.mkにencryptCfgがあり、zlib圧縮後AES256-CBCで生成する。
公開image内のprofileのみを対象に、既知AES256-CBC vectorを先に照合してcopyを読み取る。個体設定backupをこの処理に渡さない。
復号・展開が成功しても実機で生成されたprofileと同一とは扱わない。

実機の最初のAPI確認は、frontendの公開login用sysmode readに限定する。
POST /cgi-bin/luci/;stok=/login?form=sysmode、body operation=read、PC有線IPへbind、timeout3秒、response上限64KiB。
管理session/token/passwordを取り出さず、write・login・password回復・knockは送らない。エラーならURLの推測総当たりをせず、処理定義へ戻る。

### 公開profileと実機の公開getter

公開profile copyの復号・zlib展開に成功した。XMLは22,767 bytes。
base profileのoperation_modeはrouter,ap、gdpr_hmac_sign=yes、wireless_sta_config_5g=apclii0、wireless_sta_config_2g=apcli0。
wds_show=yesだが、これは実機のWDS対応を証明しない。country等のprofile mergeがあり、最新の実機feature flagを優先する。
原file・frontend・追加Luaのhashは[evidence/runtime-web.json](evidence/runtime-web.json)。
AES検証には[NIST CBC example](https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Standards-and-Guidelines/documents/examples/AES_ModesA_All.pdf)の既知vectorを使用した。

sourceをPC Ethernetへbindし、192.168.0.1のMACが既に照合した本体labelと一致することを再確認した。
実機へ既知frontendと一致する公開readだけを送った結果:

| 要求 | 実際の結果 |
| --- | --- |
| /login?form=sysmode | HTTP200、success=true、support=yes、mode=router |
| /device_config?form=config | HTTP200、success=true。supportOperationMode=[router,ap]、supportDwds=false、supportWdsDualmode=false、supportJPFeatures=true |
| 同上 | supportNDProxy=true、supportMulticastForwarding=false。STA転送時のIPv6成功・multicast全遮断を意味しない |
| 同上 | certification=[SG CLS L1 STAGE2]。JP実機でもこの共通protocol flagが使われる |
| /login?form=keys、/login?form=auth | 公開RSA鍵・sequenceのresponse構造を確認。認証成功ではない |
| /admin/wireless?form=wireless_connect_to_network（未認証） | HTTP200、{"data":""}。このresponseからroute不存在やSTA設定値を判定しない |

### 認証と変更経路の境界

最新frontendの通常local loginはpasswordのRSA PKCS#1 v1.5と、signatureのRSA OAEP/SHA1を別に使用する。
観測したcertificationではlogin hashがSHA256、認証後readはciphertext hashとHMAC-SHA256になる。
Lua dispatcherはcookie、stok、client IP等を照合する。browserの認証情報抽出や認証の回避は行わない。

[限定clientの仕様と実行方法](read-sta-state.md)を先に資料化し、offline test後にtools/read_sta_stateを実装した。
公開featureのpreflight-onlyが実機で成功した後、ユーザー指定の既存passwordを非表示の対話入力へ渡し、通常login・両getter・logoutも成功した。
passwordをfile、環境変数、command引数へ保存していない。出力はallowlistで値を制限し、PSK・SSID・BSSID・token・cookieを保存しない。
認証済み結果はmode=router、enable_2g=off、enable_5g=off、encryption_2g/5g=psk。
このenableは**root AP接続用STA**の設定であり、クライアント向けAPの停止を意味しない。
非対話実行がpasswordを要求せず停止することも確認した。setterは持たず、失敗時の再試行・confirmによるsession強制解除は行わない。

追加の静的callsiteではsys.configのmerge_wds_config_for_wifixが、通常AP側のwdsをoff、STA/mesh側をonへ設定してcommit_without_write_flashする。
同じmoduleのmerge_rtor_wireless_configにはuser-config partitionのerase/writeがある。
**一部のRAM更新処理の存在から、mode switch全体を再起動で戻る一時操作と扱わない。** これらの変更処理は実行していない。

認証済みgetterが成立したため、「runtime情報を読む入口がない」という障壁は解消した。
残る変更前条件はsetterのsection mapping・wds_modeのdriver側意味、apply条件、変更後も維持する有線管理と実証可能な復元経路。
5GHz rootap mappingにはwds_modeの許容値0/1/2があるが、数字から3addr/4addrの意味を推測しない。
Apcfg.writeはcommit後need_applyを判定し、operation/mode/profileに応じてapply・wifi reload・switch_mode rtorへ分岐する。
再起動だけで戻る計画にはできない。Client Bridge PoC・実機のSTA設定変更はNOT RUN。
