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
modelのwriteにはmesh関連operation / sysmode / profile条件によるwifi reloadやswitch_mode rtorの分岐がある。後述の追加追跡で、普通のrootap writeとmesh専用operationを区別した。
未検証の任意writeを総当たりする方法は採らず、既知のrootap routeに6 fieldだけを渡す一回限りのprobeと、開始時値への明示的なrollbackを先に設計した。

1. controller / model / wifixの処理を追い、JP/1.0の通常STAを設定できる認証済み経路と必要な入力を確定する。
2. 有線管理を維持し、変更前のruntime状態を読み取れることを確認する。backupの存在だけでこの条件を満たしたとは扱わない。
3. 有線管理IPの重複を解消し、PC固定管理IPを確保してDHCPを先に停止する。その後、限定setterとrollback → 5GHz association → LAN転送 → AP停止を段階的に実測する。

現段階では未確認setterへの要求、firewall解除、無認証login、flash変更は実施していない。
既知routeの5GHz限定setterは後述のprobeで受理・読み戻し・無効化・開始時値への復元まで確認した。association、LAN forwarding、AP停止を含むClient Bridge実機PoCはNOT RUNのまま。

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
再起動だけで戻る計画にはできない。既知rootap routeの限定STA設定変更は後述のprobeで確認したが、Client Bridge PoCはNOT RUN。

## 追加追跡: 普通のrootap writeとMAT driver

controller/write_rootapのsuffix loopは_2g / _5gのfieldだけを新tableへ変換し、operationはApcfgへ渡さない。
sysmode=hotspotの場合だけAP側の暗号fieldへcopyする。現在のrouter modeではこのcopy分岐を通らない。
model/52（Apcfg.write）のoperation既定は空文字。commit後、mesh operationでなければpc931のapplyへ分岐する。
onemesh2_support=noのpc934もapply。switch_mode rtorはonemesh_write / easymesh_writeのrouter/AP専用分岐。
従って、**普通のrootap setterが必ずrtor mode switchを行うという解釈は広すぎる**。これは追跡したbytecodeの静的推論であり、実機でのsetter成功とは別。
model/48のapplyは変更action/sectionに応じて/sbin/wifiを組み立て、VAP actionにはsleep 3を挟む。
5GHz rootap mappingのcfgはSTA用13、actionはVAP用5。複数groupを渡すconstructorだけでAP全停止やmesh解除を主張しない。

最新公開/lib/modules/5.4.281/mt_wifi.koはAArch64 ET_REL、15,400,056 bytes。
SHA256 dbc2528195c22bd61bc0856cb3e63a401b27dc44ce7d632fc97af53bf466da5b。
Capstone 5.0.9 / pyelftools 0.32で限定したsection/symbol/relocationだけを読む。vendor moduleをload/runしない。
既知AArch64 RET命令のdecodeを先に確認し、ET_RELのcallをrelocationで照合した範囲に限定する。
公開profileにはsupport_wifi7=yes、support_mlo_host=yes、ra4/rai4のMLO host interface名があり、mt_wifi.koの静的stringsには802.11be/MLO/EMLSR/EMLMRがある。これはBE5000のAP host/driver候補を示す静的証拠で、5GHz ApCliがMLO clientとして交渉・集約することや、実機のlink stateを証明しない。

| 確認対象 | 静的に確認できた処理 | まだ確認できないこと |
| --- | --- | --- |
| MATEngineTxHandle | EtherType IPv4 / ARP / IPv6 / PPPoE / VLANを判定し、protocol tableのcallbackへ渡す実装 | JP実機でMATが有効になっているか、実際の転送 |
| MATEngineRxHandle | 同種protocol dispatchと、callbackの返した6-byte MACのEthernet宛先へのcopy | 複数LAN端末・IPv6 ND/RA・multicastの対応範囲 |
| MATEngineInit | protocol init callback群を走査し、成功時のenable field更新 | 実機での初期化成功・有効flag |
| MATProtoIPHandle / ARPHandle / IPv6Handle | 32-byte STT_OBJECTのcallback table。短いstub functionではない | callback名だけでprotocol全体の正しさを判定しない |
| Set_EthConvertMode_Proc | dongle / clone / hybridの文字列判定とmode bit設定 | 現在のmode、実機用iwpriv setterの可否 |

driverにはEthConvertMode=dongleを含むtemplateもあるが、文字列だけからactive profileや実機状態を確定しない。
wifixのconfig_wds_setting付近はApCliMeshRule=1のcommand文字列を参照する一方、同じ配布物のmt_wifi.ko本文にそのcommand名は見当たらない。
互換性の疑問として記録する。command errorの処理、実機のSTA接続、後続ApCliSsid/Enableの成否をまだ測定していないため、これだけで接続不能とは断定しない。
QCA用wifix.shのwds_mode=2→extapという意味をMTK binaryへ移さない。

## 管理subnet変更と接続前準備

ユーザーがBE5000を192.168.1.1/24へ変更し、有線sourceから到達・本体MAC一致を確認した。
通常認証のLAN/DHCP/STA getterで、DHCP on、配布範囲1.100〜249、STA両band off、wds_mode=2、locktoap=off、psk/rsn/aesを確認。
PC管理IPを一時的に1.52へ固定し、Web UIでDHCPをoffへ保存・再読込確認した。[準備と復元](wired-management.md)。
親機と管理IP/DHCPが競合する状態でSTAを有効にしない。
[限定STA設定試験の手順](sta-config-probe.md)を実装前に作成し、setter拒否・応答喪失・割込み・restore失敗をoffline testで確認した。
association / forwarding / AP完全停止の合格とは区別する。

## 限定STA setterの実機結果

有線管理IPを分離し、BE5000 DHCPをoffへ保存した状態で、通常認証の既知routeに対して5GHzだけを一度writeした。WPA2/AES候補と、公開frontendが示すWPA2/WPA3混在の`psk_sae` / `sae_transition` / AES mappingをそれぞれ使い、4秒後のreadbackで6 fieldと2.4GHz offを確認した。

各試行は最初に5GHzをoffへ戻し、開始時の6 fieldをwriteし直して4秒後に初期値・両band offを照合した。どちらも `configuration-probe-complete`、`disable_accepted=true`、`restore_accepted=true`、`rollback=verified`、logout completeだった。最新の混在候補の記録はローカルの[sta-probe report](../local-evidence/sta-probe-20261006T223014392560Z.json)にあり、個体SSID/PSK/tokenは保存していない。

同じ試行のIPv6 link-local controlでは、管理Wi-Fi側のcontrol replyは得られたが、BE5000直結Ethernet側のreplyは有効期間中も得られなかった。Ethernet側にRA/IPv6 addressがないため、この結果だけでSTA association、ND変換、bridge forwardingのどれかを失敗と特定できない。reportの`association`は`not-measured`、`forwarding`は`IPv6-link-local-probe-only`のままである。

設定getterは接続状態フィールド自体を返さず、この時点のreportの`status_after_write`/`status_after_restore`も`unavailable`だった。MLO client negotiation、複数LAN端末の転送、MAC変換、AP停止後のSTA維持、再起動後の永続性は未測定である。

## IPv4だけの受入条件への変更

2026-10-07にユーザーがIPv6を使用していないと明示したため、IPv6を受入条件から外した。今後はIPv4 DHCP/ARP、親機側との双方向通信、SMB、IPv4 multicast/mDNS、長時間TCPを評価する。過去のIPv6 probeは診断記録であり、候補を不合格にする根拠にしない。IPv4 relay/proxy方式も制約を実測した上で候補に含める。

IPv6測定を省いた追加probeは設定readback、無効化、開始時値への復元、logoutに成功した。既知の`/admin/wireless?form=wireless_connect_status` readは有効時・復元後とも失敗し、接続状態は`read-failed`、associationとIPv4 forwardingは未測定のまま。記録はlocal-evidence/sta-probe-20261006T223857030087Z.json。PCの一時host route追加もOSの権限不足で拒否されたため、転送試験は成立していない。

## IPv4 DHCPの限定転送観測

続いて[IPv4 probe](sta-ipv4-probe.md)を実装し、route/IP設定を変更せずに一回ずつDHCP DISCOVERを送信した。Wi-Fi controlは受信interfaceを照合したOFFERを受信。BE5000直結EthernetはSTA有効化前、有効中、復元後ともOFFERなし。別interfaceからの同じtransactionのOFFERもなかった。WPA2/WPA3混在候補の設定write/readbackとrollback、logoutは成功した。記録はlocal-evidence/sta-probe-20261007T045658760984Z.json。

これでIPv4の観測自体は実施できたが、DHCP転送の成功は得ていない。DISCOVERのIP sourceが既存の管理subnet addressとなる条件、および短い待ち時間がある。無線association、ARP/unicast、複数端末、SMB、安定性の成否はこの結果から特定できない。lease取得やAP停止は行っていない。

### 接続状態APIの静的な不一致候補

公開FWのcontrollerはwireless_connect_status/readをconnect_rootap_statusへdispatchする。このcallbackは2g/5gのsta_connect_rootap_statusを呼び、最大値からconnected/connecting/disconnectedを返す。後者はUCI profileの`wireless_sta_ifname_` + bandを取得し、そのsectionのenable/ifnameを参照する。有効時はwpa_cli statusのwpa_stateを読む。

復号済み公開profileには`wireless_sta_config_2g=apcli0`、`wireless_sta_config_5g=apclii0`がある一方、`wireless_sta_ifname_2g/5g`はない。参照名の不一致はAPI失敗の候補である。ただし実機profile mergeやget_profileの補完を確認していないので、nil値による例外や実機failureの原因と断定しない。controller/sta_connect_rootap_statusのpc12〜18、pc22〜46、pc47〜71を追跡した静的推論であり、実機でwpa_cliを実行した証拠ではない。
