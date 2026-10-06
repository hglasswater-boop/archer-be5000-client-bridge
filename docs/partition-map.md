# Partition map

解析前。実機flashのpartition mapは未確認。
containerのpayload配置、GPLのboard定義、実機/proc/mtdは別々に記録し、対応を照合する。
bootloader、calibration、factory、MAC、config領域を上書きしない。offsetを推測して書込みコマンドを作らない。
