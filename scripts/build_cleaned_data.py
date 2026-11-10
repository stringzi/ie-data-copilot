# -*- coding: utf-8 -*-
"""重新生成 data/processed/cleaned_data.csv 与清洗报告。

用法：python scripts/build_cleaned_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # 旧版终端可能不支持
    pass

from ie_copilot.cleaning import clean_dataframe  # noqa: E402
from ie_copilot.config import PROCESSED_CSV, RAW_CSV  # noqa: E402
from ie_copilot.data import read_csv_flexible, save_processed  # noqa: E402


def main() -> int:
    if not RAW_CSV.exists():
        print(f"未找到原始数据：{RAW_CSV}")
        return 1

    raw = read_csv_flexible(RAW_CSV)
    cleaned, report = clean_dataframe(raw)
    save_processed(cleaned, report)

    print("\n".join(report.summary_lines()))
    print(f"\n已保存：{PROCESSED_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
