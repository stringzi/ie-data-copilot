# -*- coding: utf-8 -*-
import unittest

import pandas as pd

from ie_copilot.sandbox import CodeExecutionError, UnsafeCodeError, run_generated_code

DF = pd.DataFrame(
    {
        "产线": ["A线", "B线"],
        "UPPH": [20.0, 30.0],
        "实际工时": [7.0, 8.0],
        "产量": [140, 240],
    }
)


class SandboxTests(unittest.TestCase):
    def test_allows_normal_pandas_code(self) -> None:
        result = run_generated_code(DF, 'result = df.groupby("产线")["UPPH"].mean().round(2)')
        self.assertAlmostEqual(float(result.loc["A线"]), 20.0)

    def test_allows_safe_builtins(self) -> None:
        self.assertEqual(run_generated_code(DF, "result = len(df)"), 2)
        self.assertEqual(run_generated_code(DF, "result = round(df['UPPH'].sum(), 1)"), 50.0)

    def test_blocks_import(self) -> None:
        with self.assertRaises(UnsafeCodeError):
            run_generated_code(DF, "import os\nresult = 1")

    def test_blocks_dunder_access(self) -> None:
        with self.assertRaises(UnsafeCodeError):
            run_generated_code(DF, "result = df.__class__")

    def test_blocks_file_write(self) -> None:
        with self.assertRaises(UnsafeCodeError):
            run_generated_code(DF, 'result = df.to_csv("leak.csv")')

    def test_blocks_os_reachable_from_pandas(self) -> None:
        with self.assertRaises(UnsafeCodeError):
            run_generated_code(DF, "result = pd.io.common.os.getcwd()")

    def test_blocks_import_builtin(self) -> None:
        with self.assertRaises(UnsafeCodeError):
            run_generated_code(DF, 'result = __import__("os").getcwd()')

    def test_requires_result(self) -> None:
        with self.assertRaises(CodeExecutionError):
            run_generated_code(DF, "value = df['UPPH'].sum()")

    def test_reports_friendly_error(self) -> None:
        with self.assertRaises(CodeExecutionError) as ctx:
            run_generated_code(DF, "result = df['不存在'].sum()")
        self.assertIn("字段", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
