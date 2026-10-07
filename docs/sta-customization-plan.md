# 通常STAのカスタム化候補

2026-10-07、通常管理APIだけの比較では親機へのassociationを実証できていない。AP onでLED点灯と保存AP名のPC scanへの出現を確認したため、無線機能全体が動かないという説明は採らない。親機側の無線端末一覧にはAP on、channel一致、STA off/on、BE5000 Mesh一時onの各比較中も現れないとのユーザー観測がある。この一覧観測と独自DHCPのOFFERなしは、supplicantの実行状態を直接取得した証拠とは区別する。

## 変更前に必要な実機観測

実際の2g STA interface、supplicant control socket、wpa_state、生成されたnetwork設定、driverのSTA有効状態を確認する。SSID/PSK/MACはRAM内で照合し、公開記録には状態ラベルと一致boolだけを残す。通常SSHは認証できてもshell/execが拒否されるため、現在この観測・RAM変更の経路を確立できていない。UARTなどの別経路も対象個体では未確認。

## 最小変更の検証順

1. 保存設定と実際に生成されたsupplicant設定の一致を確認する。APIの保存成功と実行中の設定一致を分ける。
2. 設定を変更せず、実際のSTAへ一度だけreconnectを送り、wpa_stateの遷移と親機側associationを観測する。公開wifixはinterface_add後にdisconnectし、driver enableへ進むが、通常STAでその後のreconnectに到達するかは未確認。
3. 接続できなければ、生成設定のtp_mesh_enableをRAM上で0にした比較を行う。候補であり、修正効果は未証明。公開wifixは1を無条件に生成する一方、EasyMeshの通常設定offはこの値を変更する根拠がない。
4. association成立後に通常APをoffにし、STA維持、実際のLAN DHCP、IPv4 unicast、NATなし、複数LAN端末を順に検証する。独自DHCPは管理IP1.52環境から送信する制約があり、最終判定には実際のLAN端末での試験が必要。
5. RAM試験で必要変更が絞れた後に、起動処理へ組み込む。全面的なOS交換やdriver再ビルドが必要かはその時点で判断する。

## tp_mesh_enableのソース上の意味と限界

公開GPLの`Iplatform/openwrt/package/hostapd/src/wpa_supplicant/config.h`は、tp_mesh_enable=0をdefault/disable、1をmesh enabled/filter tpieと説明する。config.c:5130は0/1を受け付け、wpa_supplicant.c:1174と6586で実行状態へ取り込む。

ただしevents.c:578以降はTP IEがある場合にnode idやlevelで候補を絞り、IEがないだけでは必ずreturn 0しない。events.c:1652〜1710の選択処理にもIEなし候補のfallbackがある。従って「tp_mesh_enable=1なら普通APをすべて除外する」という結論は誤り。radio survey 0がこの処理の結果だとも証明していない。

ctrl_iface.c:12205以降にはTP_MESH_ENABLE getter/setterがあるが、setter dispatchの引数offsetに不整合が見られる。現行binaryでの同一性や安全な呼び出しを未確認なので、この文字列をそのまま実機コマンドとして提供しない。公開GPLと現行FWは同一buildと確認していない。

取り出したソースはローカルignoredの`artifacts/sta-tpmesh-source/`に置き、vendor codeは実行していない。

| ソース | SHA256 |
| --- | --- |
| config.c | b20f4397aeacf45f7982e725d3d116b0ecbebf98e9b1f936f962e06e74282a03 |
| events.c | 07fdac7850cd9e8db4c3ebdb928144b66d9e012f5b5bb656805a89e4e407f510 |
| ctrl_iface.c | 33bc53c2da03b26654fd507fbc3b83f24019d649b3067cb0c9a31e7a469a48b5 |
| wpa_supplicant.c | 2e948b469b59c6f87d4a3885bea20efc00c174da724e8b066546664288a95a4c |

## Firmwareへの投入経路

純正配布物のRSA2048-PSS署名は検証済みだが、変更imageの署名生成・受理は未確立。GPLだけで現行FW全体を完全再現できることも確認していない。設定backupは取得済みだが、破損FWからの復旧手段は対象個体で未確立。[復旧の確認状況](recovery.md)と[署名・RAMFSの確認状況](firmware-analysis.md)を参照する。

現段階で改造imageやbootloaderを書かず、実機観測とRAMでの最小変更を先に成立させる。まだ接続を保証する修正やflash可能なimageを作成した段階ではない。
