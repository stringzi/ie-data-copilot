# -*- coding: utf-8 -*-
import unittest
from types import SimpleNamespace

import pandas as pd

from ie_copilot import ai_query

DF = pd.DataFrame(
    {
        "日期": pd.to_datetime(["2026-09-01", "2026-09-10"]),
        "产线": ["A线", "B线"],
        "工序": ["冲压", "焊接"],
        "UPPH": [20.0, 30.0],
    }
)


def fake_client(content: str):
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response))
    )


class AiQueryTests(unittest.TestCase):
    def test_prompt_contains_data_profile(self) -> None:
        prompt = ai_query.build_prompt(DF, "本周 A 线表现如何？")
        self.assertIn("2026-09-01", prompt)
        self.assertIn("2026-09-10", prompt)
        self.assertIn("不要使用系统当前日期", prompt)
        self.assertIn("A线", prompt)
        self.assertIn(ai_query.UNANSWERABLE_TOKEN, prompt)

    def test_extract_code(self) -> None:
        self.assertIn("result", ai_query.extract_code("说明\n```python\nresult = 1\n```"))
        self.assertIsNone(ai_query.extract_code("UNANSWERABLE: 缺少字段"))
        self.assertIsNone(ai_query.extract_code("UNANSWERABLE：缺少字段"))

    def test_unanswerable_message(self) -> None:
        message = ai_query.friendly_unanswerable("UNANSWERABLE: 缺少不良数以外的字段")
        self.assertIn("缺少不良数以外的字段", message)

    def test_validate_answer_truncates(self) -> None:
        answer, warnings = ai_query.validate_answer(pd.DataFrame({"x": range(300)}))
        self.assertEqual(len(answer), ai_query.MAX_RESULT_ROWS)
        self.assertTrue(warnings)

    def test_validate_empty_result(self) -> None:
        _, warnings = ai_query.validate_answer(pd.DataFrame({"x": []}))
        self.assertTrue(warnings)

    def test_ask_data_without_question(self) -> None:
        result = ai_query.ask_data("")
        self.assertEqual(result.status, "error")

    def test_ask_data_end_to_end_with_fake_client(self) -> None:
        client = fake_client("```python\nresult = round(df['UPPH'].mean(), 2)\n```")
        result = ai_query.ask_data("平均 UPPH 是多少？", df=DF, client=client)
        self.assertEqual(result.status, "ok")
        self.assertAlmostEqual(result.answer, 25.0)
        self.assertIn("result", result.code)

    def test_ask_data_blocks_unsafe_code(self) -> None:
        client = fake_client('```python\nimport os\nresult = os.getcwd()\n```')
        result = ai_query.ask_data("读一下系统目录", df=DF, client=client)
        self.assertEqual(result.status, "error")
        self.assertIn("安全", result.message)

    def test_ask_data_unanswerable(self) -> None:
        client = fake_client("UNANSWERABLE: 当前数据没有员工姓名字段")
        result = ai_query.ask_data("谁效率最高？", df=DF, client=client)
        self.assertEqual(result.status, "unanswerable")


if __name__ == "__main__":
    unittest.main()
