# Existing support

調査日2026-10-06〜07。似た機種やSoC対応をBE5000用install imageの証拠にしない。

| 対象 | 確認範囲と結果 |
| --- | --- |
| OpenWrt main | [公式Git tree API](https://api.github.com/repos/openwrt/openwrt/git/trees/main?recursive=1)、commit edc6b8f160c798cd211893bc5df25aec7cfca838、truncated=false。path中のBE5000 / BE260 / BE4600 / BE700の一致なし。専用board/image対応を確認できなかった |
| 同SoC | OpenWrt treeにMT7987、BPI-R4-Lite / Routerich BE7200関連がある。flash/無線/boot/partitionが異なり、そのimageをBE5000へ投入しない |
| Upstream kernel | [公式mediatek DTS directory](https://github.com/torvalds/linux/tree/master/arch/arm64/boot/dts/mediatek)のdirectory API確認ではmt7987名の一致なし。この限定検索はSoC全機能の未対応の証明ではない。OpenWrt downstream DTSと区別する |
| Vendor SDK | GPLにmtk798x/openwrt-21.02、Linux5.4.281、MT7987-MT7992-BE5040。最も直接的な対象資料だが、最新製品daemon sourceは完全でない |
| 同系TP-Link | 最新BIN/FIT support-listはBE260/BE5000/BE4600等を共有し、JP/US/KR configを持つ。共通packageは別revisionに任意imageを書ける根拠ではない |
| OpenWrt forum / device pages | Web検索でBE5000固有の実装/復旧の一次資料を確認できなかった。forum robots制限、OpenWrtページのbot challengeもあり、検索未発見を不存在と断定しない |

OpenWrt移植を最小PoCの既定案にしない。対応DTSやSoC supportだけではvendor Wi-Fi7 driver、calibration、署名付きupgrade、fallbackを解決しない。
