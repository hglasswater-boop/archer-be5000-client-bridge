# Hardware evidence

日付: 2026-10-06。実機未接続。

| 項目 | 状態 | 確認方法 |
| --- | --- | --- |
| 地域 | 日本（ユーザー申告） | 本体ラベルとの照合待ち |
| 正確なhardware revision | 未確認 | 本体ラベル、管理画面 |
| 現在FW | 最新との申告、版文字列未確認 | 管理画面 |
| SoC | 未確認 | 対応GPL board設定、device tree、実機boot log、チップ刻印 |
| Wi-Fi chipset | 未確認 | 対応driver/board設定と実機識別 |
| switch chipset | 未確認 | DTS、boot log、刻印 |
| flash / RAM | 未確認 | DTS、boot log、部品刻印。imageサイズから容量を推測しない |
| bootloader | 未確認 | image・GPL・実機boot log |
| UART / JTAG | 未確認 | 対応基板の写真、測定、公式資料 |
| Secure Boot | 未確認 | fuse状態・boot chain検証経路。SDKの機能だけで有効とはしない |

同名Xiaomi BE5000、Deco BE5000、他のArcherは別機種。互換性の根拠にしない。
