# -*- coding: utf-8 -*-
import unittest

import numpy as np
import pandas as pd

from ie_copilot.cleaning import CleaningError, clean_dataframe


def make_raw() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-09-01", "2026-09-01", "2026-09-02", "2026-09-03", "bad", None],
            "产线": ["A线", "A线", "B线", None, "A线", "B线"],
            "工序": ["冲压", "冲压", "焊接", "冲压", "冲压", "焊接"],
            "标准工时": [8.0, 8.0, 7.5, 7.0, 6.5, 6.0],
            "实际工时": [7.5, 7.5, None, 7.0, 6.0, 6.5],
            "产量": [100, 100, 90, None, 80, 70],
            "不良数": [5, 5, 4, 3, 2, 1],
            "停机时长": [0.5, 0.5, None, 0.2, 0.1, 0.0],
        }
    )


class CleaningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.clean, self.report = clean_dataframe(make_raw())

    def test_row_counts_and_report(self) -> None:
        self.assertEqual(self.report.rows_in, 6)
        self.assertEqual(self.report.duplicates_removed, 1)
        self.assertEqual(self.report.invalid_date_rows_removed, 2)
        self.assertEqual(self.report.rows_out, 3)
        self.assertEqual(len(self.clean), 3)

    def test_category_filled_from_group(self) -> None:
        row = self.clean.loc[self.clean["日期"] == pd.Timestamp("2026-09-03")].iloc[0]
        self.assertEqual(str(row["产线"]), "A线")

    def test_missing_output_kept_as_na(self) -> None:
        row = self.clean.loc[self.clean["日期"] == pd.Timestamp("2026-09-03")].iloc[0]
        self.assertTrue(pd.isna(row["产量"]))
        self.assertTrue(pd.isna(row["UPPH"]))

    def test_hours_filled_by_global_median_when_group_is_empty(self) -> None:
        row = self.clean.loc[self.clean["日期"] == pd.Timestamp("2026-09-02")].iloc[0]
        self.assertAlmostEqual(float(row["实际工时"]), 7.25)
        self.assertAlmostEqual(float(row["UPPH"]), 90 / 7.25, places=6)

    def test_metrics_are_correct(self) -> None:
        row = self.clean.loc[self.clean["日期"] == pd.Timestamp("2026-09-01")].iloc[0]
        self.assertAlmostEqual(float(row["工时达成率"]), 8 / 7.5, places=6)
        self.assertAlmostEqual(float(row["不良率"]), 0.05, places=6)

    def test_zero_downtime_filled(self) -> None:
        row = self.clean.loc[self.clean["日期"] == pd.Timestamp("2026-09-02")].iloc[0]
        self.assertEqual(float(row["停机时长"]), 0.0)

    def test_no_infinite_rates(self) -> None:
        rates = self.clean[["工时达成率", "UPPH", "不良率"]].astype("float").to_numpy()
        self.assertFalse(np.isinf(rates).any())

    def test_missing_columns_raise(self) -> None:
        with self.assertRaises(CleaningError):
            clean_dataframe(pd.DataFrame({"日期": ["2026-09-01"]}))

    def test_zero_actual_hours_gives_na_rates(self) -> None:
        raw = pd.DataFrame(
            {
                "日期": ["2026-09-01"],
                "产线": ["A线"],
                "工序": ["冲压"],
                "标准工时": [8.0],
                "实际工时": [0.0],
                "产量": [100],
                "不良数": [5],
                "停机时长": [0.0],
            }
        )
        clean, report = clean_dataframe(raw)
        self.assertTrue(pd.isna(clean.loc[0, "工时达成率"]))
        self.assertIn("实际工时小于等于 0", report.invalid_rows)

    def test_summary_lines(self) -> None:
        lines = self.report.summary_lines()
        self.assertTrue(lines)
        self.assertTrue(any("输入 6 行" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
