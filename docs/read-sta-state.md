# 認証済みSTA状態の読み取り

JP/1.0、1.2.0 Build 20260420 rel.13798(4A50)の公開frontendを静的に追った、限定的な実機調査用client。
**2026-10-07に対象実機で通常login・両getter・logoutが成功**。通常のlocal loginを一度だけ行い、既知のgetterを読む。
STA setter、mode変更、再起動、firewall変更、firmware書込みを持たない。
通常loginに伴うsession・login counter・製品側の通知metadataの更新はあり得るため、完全に無副作用とは扱わない。

## 使用する経路

| 経路 | 要求 |
| --- | --- |
| /device_config?form=config | operation=read、公開機能flagの照合 |
| /login?form=keys | operation=read、password用公開RSA鍵 |
| /login?form=auth | operation=read、signature用公開RSA鍵とsequence |
| /login?form=login | operation=login、既存passwordのRSA暗号文。confirmを送らない |
| /admin/system?form=sysmode | operation=read、認証済み動作mode |
| /admin/wireless?form=wireless_connect_to_network | operation=read、root AP/STA設定 |
| /admin/network?form=lan_ipv4 | --network-baseline時だけoperation=read、LAN管理IP |
| /admin/dhcps?form=setting | --network-baseline時だけoperation=read、DHCP server設定 |
| /admin/system?form=logout | 空payload、自分で作成したsessionの終了を一度試す |

URLは/cgi-bin/luci/;stok=に続く通常のWeb UI経路。
公開情報のcertificationがSG CLS L1 STAGE2、JP feature=true、mode候補がrouter/APであることを確認する。
異なるprotocolへfallbackしない。既存sessionとの衝突、login失敗、未知response、timeoutでは停止し、再試行・強制loginを行わない。
logout失敗だけは取得結果と区別して記録する。通常のsession timeoutは製品側に任せる。

## 暗号の照合範囲

公開frontendのlocal loginはSHA256("admin" + password)を使う。
password自体はRSA PKCS#1 v1.5、login signatureは53文字ずつのRSA OAEP/SHA1。
payloadは16桁ASCII数字のkey/IVによるAES128-CBC/PKCS7で、Base64化したciphertext。
認証後のreadではciphertextのSHA256をhashに置き換え、53文字ずつHMAC-SHA256でsignする。
sequenceはchallengeの値 + Base64 ciphertextの文字数。初期値は保持する。
この実装はvendor JSを実行せず、Python標準libraryとNode.js標準cryptoのみを使用する。

AESの既知vector、RSA paddingの相違、signature境界、HMAC、失敗時の停止、書込み要求の拒否をoffline testする。
暗号unit testの成功と実機試験を区別する。今回の実機結果はrouter mode、enable_2g=off、enable_5g=off、暗号種別は両bandともpsk。
STA設定のreadが受理されたことは、setterの安全性、association、LAN forwardingの成功を証明しない。

## 実行

PCをBE5000へ直接有線接続したまま、source IPと対象MACが一致することを先に確認する。
管理IP変更前はWi-Fi側にも192.168.0.1があるため、source IP省略を許さない。
ユーザーがBE5000を192.168.1.1/24へ変更した後も、有線sourceへのbindを必須とする。
--target-ipは確認済み管理候補192.168.0.1 / 192.168.1.1だけを許可し、sourceが同じ/24にない場合は通信前に停止する。
既存の管理画面はユーザー自身でlogoutしておくとsession衝突を避けられる。clientは衝突を強制解除しない。

```powershell
Set-Location C:\Ddrive\project_BE5000
python -m tools.read_sta_state --source-ip 192.168.0.52
```

今回の管理IP変更後、PCの有線固定IPで読む場合:

```powershell
python -m tools.read_sta_state --target-ip 192.168.1.1 --source-ip 192.168.1.52 --network-baseline
```

既存の管理passwordはこのPCのterminalで一度だけ入力する。入力を表示せず、chat・引数・環境変数・fileから受け取らない。
非対話環境ではpasswordを要求せず停止する。
nodeがPATHにない場合は--nodeで実行fileを指定する。依存packageの追加installは不要。
--preflight-onlyはpassword/loginを使わず、公開feature照合だけを行う。
--network-baselineは既知frontendのLAN・DHCP getterを追加する。
LAN/DHCPのIP範囲はlocal-evidence内のreportへ記録し、個体のSSID/PSK等は引き続き除外する。
2026-10-07に変更後のLAN IPとDHCP設定を通常認証で読み取れた。
共通wireless_connect_status getterを含めた初回試行はHTTP応答拒否で停止し、logoutは成功した。
このgetterはwireless_sta_ifname profileとwpa_cliに依存し、最新公開profileで必要なkeyが見当たらない。
製品によるHTTP status/sizeの詳細を初回clientが保持していないため、具体的なerror codeは未確定。
失敗したgetterをbaselineから外し、LAN/DHCP/通常STA設定の4 getter・logoutの成功を別試行で確認した。
失敗はdriverのassociation失敗を意味しない。read_sta_stateの通常baselineはこの共通status経路を要求しない。別のprobe_sta_configはSTA有効時と復元後にこのread-only経路を一度ずつ要求し、失敗を固定ラベルread-failedとして記録する。

出力はrepository内のgitignoreされたlocal-evidence/へ新規作成する。既存fileは上書きしない。
password・PSK・暗号key・token・cookieをreport/consoleへ保存しない。未知fieldは値を保存せずfield名だけを記録する。
SSID/BSSIDもこのreportでは保存しない。consoleは成否とreportの保存先のみを表示する。
応答は64KiB、要求timeoutは5秒。redirectは追わず、source IPv4をbindする。
reportは読み取りの結果であり、STA接続やLAN転送の動作確認ではない。
