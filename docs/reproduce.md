# Offline reproduction

Python3.11とNode.js標準cryptoを使用。4つのrepository toolは解析copyを読み書きするだけで、network / flash / firmware実行機能を持たない。
検証順は資料 → synthetic test → 最小実装 → 実配布物への適用。commit historyに各段階を記録した。
公式取得物とrootfs本文はartifacts/、個体の記録はlocal-evidence/に保存し、公開しない。

## 取得・hash照合

[公式FW](https://static.tp-link.com/upload/firmware/2026/202606/20260612/Archer%20BE5000_V1_260420.zip)をartifacts/jp-v1-260420.zip、[GPL](https://static.tp-link.com/upload/gpl-code/2026/202605/20260512/GPL_ArcherBE5000.tar.gz)をartifacts/GPL_ArcherBE5000.tar.gzに保存する。
hashはfirmware-analysis.mdと照合する。GPL archiveは約2.33GBで、stream走査にも時間が必要。vendor scriptを実行しない。

```powershell
Get-FileHash artifacts/jp-v1-260420.zip -Algorithm SHA256
Get-FileHash artifacts/GPL_ArcherBE5000.tar.gz -Algorithm SHA256
python -m unittest discover -s tests -v
python -m tools.inspect_firmware artifacts/jp-v1-260420.zip --output artifacts/raw-report.json
python -m tools.inspect_gpl artifacts/GPL_ArcherBE5000.tar.gz --output artifacts/gpl-reproduction --select '(^\./Readme\.txt$|/Iplatform/build/product_configs/be260v1/[^/]+$|/nvrammanager/(nm_fwup|rsaVerify)\.c$)'
```

inspect_gplはmember単体2MiB、選択payload計64MiB、宣言archive payload計32GiBを制限。全metadataはmembers.jsonl、完走した場合だけsummary.jsonが生成される。
pathはDATAとして保存し、hash名で通常fileだけを保存。link / deviceを辿らない。出力directoryは新規のみ。

## 認証後のcopy復号

上記summary.jsonで元path末尾/nvrammanager/nm_fwup.cのsaved_asを確認する。今回のnm source SHA256はc82430468775e35f508d04dae7a47d0b88133a811f032a25ef01d4558b73575d。

```powershell
python -m tools.decode_cloud artifacts/jp-v1-260420.zip --nm-source artifacts/gpl-reproduction/c82430468775e35f508d04dae7a47d0b88133a811f032a25ef01d4558b73575d.txt --output artifacts/decoded-reproduction.bin --report artifacts/decoded-report.json
python -m tools.read_ubi artifacts/decoded-reproduction.bin --start 0x1258 --peb-size 0x20000 --output artifacts/volumes-reproduction
```

decode_cloudは新規のdistinct output/reportのみ。署名認証・salt条件・AES extent・復号markerが一致した場合だけ出力する。key/IVはprocess引数/logへ出さない。
read_ubiはこのpackageのpristine static UBIに限定する。EC/VID/data CRC、sequence、logical blockを検証し、欠損や重複を停止する。一般raw NAND dumpの復旧toolではない。
decoded imageとvolumesは**解析専用で、flash不可**。新規出力が必須なので再実行時は別名を使う。

## SquashFSの選択読み取り

[dissect.squashfs公式source](https://github.com/fox-it/dissect.squashfs)のread-only parserを隔離targetへ導入した。UBI Readerもローカルで調べたがvolume復元には使用していないため必須依存に含めない。

```powershell
python -m pip install --target artifacts/python-libs -r requirements-analysis.txt
```

Pythonで次のように選択fileを読む。全file展開やvendor code実行を行わない。

```python
import sys, hashlib
from pathlib import Path
sys.path.insert(0, str(Path('artifacts/python-libs').resolve()))
from dissect.squashfs import SquashFS
with open('artifacts/volumes-reproduction/volume-2.bin', 'rb') as source:
    fs = SquashFS(source)
    node = fs.get('/etc/partition_config/partition-table')
    assert node.is_file()
    content = node.open().read()
    print(hashlib.sha256(content).hexdigest())
```

他の選択path/hashはrootfs-selected.jsonを参照。hostapd / wpa_supplicantはwpadへのimage内symlinkで、別々の実行fileと扱わない。ホスト上でsymlinkを生成しない。
単体テスト59件は解析toolと限定STA reader/probeの境界・既知vector・設定rollbackを検証する。実機boot / Client Bridge / 長時間安定性の合格を代用しない。
実機readerは[別の実行手順](read-sta-state.md)に従い、PC有線sourceと通常認証を使用する。offline解析commandへ個体passwordを渡さない。
