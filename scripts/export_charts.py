# -*- coding: utf-8 -*-
"""导出三张分析图到 assets/charts/（用于 README 与设计稿）。

用法：python scripts/export_charts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from ie_copilot.charts import export_all  # noqa: E402
from ie_copilot.data import load_default_dataframe  # noqa: E402

OUTPUT_DIR = ROOT / "assets" / "charts"


def main() -> int:
    df = load_default_dataframe()
    written = export_all(df, OUTPUT_DIR)
    if not written:
        print("没有生成任何图表，请检查数据。")
        return 1
    for path in written:
        print(f"已保存：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
