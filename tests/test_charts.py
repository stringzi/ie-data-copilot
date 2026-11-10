# -*- coding: utf-8 -*-
import unittest

import matplotlib

matplotlib.use("Agg")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ie_copilot import charts  # noqa: E402


def make_df() -> pd.DataFrame:
    rows = []
    for line_index, line in enumerate(["A线", "B线", "C线", "D线"]):
        for day in range(3):
            rows.append(
                {
                    "日期": pd.Timestamp("2026-09-01") + pd.Timedelta(days=day),
                    "产线": line,
                    "工序": ["冲压", "焊接", "组装"][day],
                    "工时达成率": 0.9 + line_index * 0.02,
                    "UPPH": 20.0 + line_index + day,
                    "不良率": 0.02 + line_index * 0.005,
                }
            )
    return pd.DataFrame(rows)


class ChartTests(unittest.TestCase):
    def test_all_charts_return_figures(self) -> None:
        df = make_df()
        for maker in (
            charts.make_avg_achievement_rate_fig,
            charts.make_daily_upph_fig,
            charts.make_defect_rate_fig,
        ):
            fig = maker(df)
            self.assertIsNotNone(fig)
            charts.close_figure(fig)

    def test_dynamic_line_is_not_dropped(self) -> None:
        fig = charts.make_avg_achievement_rate_fig(make_df())
        self.assertIsNotNone(fig)
        self.assertEqual(len(fig.axes[0].patches), 4)
        charts.close_figure(fig)

    def test_empty_metric_returns_none(self) -> None:
        df = make_df()
        df["UPPH"] = np.nan
        self.assertIsNone(charts.make_daily_upph_fig(df))

    def test_missing_columns_return_none(self) -> None:
        self.assertIsNone(charts.make_defect_rate_fig(pd.DataFrame({"日期": [pd.Timestamp("2026-09-01")]})))


if __name__ == "__main__":
    unittest.main()
