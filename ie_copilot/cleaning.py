# -*- coding: utf-8 -*-
"""生产数据清洗与 IE 指标计算。

对外主入口是 :func:`clean_dataframe`，Streamlit 页面与命令行脚本共用同一套逻辑。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

DATE_COLUMN = "日期"
CATEGORY_COLUMNS = ["产线", "工序"]
GROUP_KEYS = ["产线", "工序"]
COUNT_COLUMNS = ["产量", "不良数"]
NUMERIC_COLUMNS = ["标准工时", "实际工时", "产量", "不良数", "停机时长"]
REQUIRED_COLUMNS = [DATE_COLUMN, *CATEGORY_COLUMNS, *NUMERIC_COLUMNS]
RATE_COLUMNS = ["工时达成率", "UPPH", "不良率"]


class CleaningError(ValueError):
    """输入数据不满足最低要求时抛出。"""


@dataclass
class CleaningReport:
    """记录清洗过程中发生了什么，便于在页面与日志中展示。"""

    rows_in: int
    rows_out: int
    duplicates_removed: int = 0
    invalid_date_rows_removed: int = 0
    numeric_coerced: dict[str, int] = field(default_factory=dict)
    non_integer_counts: dict[str, int] = field(default_factory=dict)
    missing_before: dict[str, int] = field(default_factory=dict)
    imputed_group: dict[str, int] = field(default_factory=dict)
    imputed_fallback: dict[str, int] = field(default_factory=dict)
    kept_missing: dict[str, int] = field(default_factory=dict)
    invalid_rows: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        """转为 JSON 可序列化的字典。"""
        return asdict(self)

    def summary_lines(self) -> list[str]:
        """生成适合终端打印的中文摘要。"""
        lines = [
            f"输入 {self.rows_in} 行，输出 {self.rows_out} 行",
            f"删除完全重复行：{self.duplicates_removed}",
            f"删除日期缺失/非法行：{self.invalid_date_rows_removed}",
        ]
        if self.numeric_coerced:
            detail = "，".join(f"{k} {v} 个" for k, v in self.numeric_coerced.items() if v)
            if detail:
                lines.append(f"数值转换失败：{detail}")
        if self.imputed_group:
            detail = "，".join(f"{k} {v} 行" for k, v in self.imputed_group.items() if v)
            if detail:
                lines.append(f"按产线+工序分组填充：{detail}")
        if self.imputed_fallback:
            detail = "，".join(f"{k} {v} 行" for k, v in self.imputed_fallback.items() if v)
            if detail:
                lines.append(f"使用全表统计兜底：{detail}")
        if self.kept_missing:
            detail = "，".join(f"{k} {v} 行" for k, v in self.kept_missing.items())
            lines.append(f"保留为空值：{detail}")
        for name, count in self.invalid_rows.items():
            lines.append(f"数据校验 - {name}：{count} 行")
        lines.extend(f"提示：{item}" for item in self.warnings)
        return lines


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """去除表头空格与 BOM，并校验必需字段。"""
    renamed = df.rename(columns=lambda col: str(col).strip().lstrip("\ufeff"))
    missing = [col for col in REQUIRED_COLUMNS if col not in renamed.columns]
    if missing:
        raise CleaningError(
            "缺少必需字段：" + "、".join(missing) + "。表头需包含：" + "、".join(REQUIRED_COLUMNS)
        )
    extras = [
        col
        for col in renamed.columns
        if col not in REQUIRED_COLUMNS and not str(col).startswith("Unnamed:")
    ]
    return renamed[REQUIRED_COLUMNS + extras].copy()


def _mode_or_nan(values: pd.Series):
    valid = values.dropna()
    if valid.empty:
        return np.nan
    return valid.mode().iloc[0]


def _fill_by_group_mode(df: pd.DataFrame, column: str, group_key: str) -> int:
    """用同一分组内的众数填充分类字段，返回填充行数。"""
    mapping = df.dropna(subset=[column]).groupby(group_key)[column].agg(_mode_or_nan)
    mapped = df[group_key].map(mapping)
    mask = df[column].isna() & mapped.notna()
    df.loc[mask, column] = mapped[mask]
    return int(mask.sum())


def _fill_numeric_by_group(df: pd.DataFrame, column: str) -> tuple[int, int]:
    """用同产线+工序的中位数填充，返回（分组填充行数，全表兜底行数）。"""
    group_median = df.groupby(GROUP_KEYS, dropna=False)[column].transform("median")
    mask = df[column].isna() & group_median.notna()
    df.loc[mask, column] = group_median[mask]
    filled_group = int(mask.sum())

    remaining = df[column].isna()
    overall = df[column].median()
    filled_fallback = 0
    if remaining.any() and pd.notna(overall):
        df.loc[remaining, column] = overall
        filled_fallback = int(remaining.sum())
    return filled_group, filled_fallback


def _validate_business_rules(df: pd.DataFrame) -> dict[str, int]:
    """业务规则校验，只统计不擅自改数。"""
    checks = {
        "实际工时小于等于 0": int((df["实际工时"].astype("float") <= 0).sum()),
        "不良数大于产量": int((df["不良数"].astype("float") > df["产量"].astype("float")).sum()),
        "数值字段为负": int((df[NUMERIC_COLUMNS].astype("float") < 0).any(axis=1).sum()),
        "日期+产线+工序重复": int(df.duplicated(subset=[DATE_COLUMN, *GROUP_KEYS]).sum()),
    }
    return {name: count for name, count in checks.items() if count}


def clean_dataframe(raw: pd.DataFrame) -> tuple[pd.DataFrame, CleaningReport]:
    """清洗原始生产数据并计算工时达成率、UPPH、不良率。

    与旧实现的区别：
    - 产量/不良数缺失不再填 0，避免产生 UPPH=0 的假暴跌；
    - 实际工时 <= 0 时比率记为空值，而不是 0；
    - 所有填充与校验都写入 :class:`CleaningReport`，便于追溯。
    """
    df = _normalize_columns(raw)
    report = CleaningReport(rows_in=len(df), rows_out=len(df))

    before = len(df)
    df = df.drop_duplicates(keep="first").reset_index(drop=True)
    report.duplicates_removed = before - len(df)

    parsed_dates = pd.to_datetime(df[DATE_COLUMN], errors="coerce")
    report.invalid_date_rows_removed = int(parsed_dates.isna().sum())
    df[DATE_COLUMN] = parsed_dates
    df = df.dropna(subset=[DATE_COLUMN]).reset_index(drop=True)

    for column in NUMERIC_COLUMNS:
        original = df[column]
        converted = pd.to_numeric(original, errors="coerce")
        coerced = int((original.notna() & converted.isna()).sum())
        if coerced:
            report.numeric_coerced[column] = coerced
        df[column] = converted

    report.missing_before = {
        column: int(df[column].isna().sum())
        for column in REQUIRED_COLUMNS
        if column != DATE_COLUMN
    }

    report.imputed_group["产线"] = _fill_by_group_mode(df, "产线", "工序")
    report.imputed_group["工序"] = _fill_by_group_mode(df, "工序", "产线")
    for column in CATEGORY_COLUMNS:
        missing = int(df[column].isna().sum())
        if missing:
            candidates = df[column].mode()
            if not candidates.empty:
                df[column] = df[column].fillna(candidates.iloc[0])
                report.imputed_fallback[column] = missing

    for column in ("标准工时", "实际工时"):
        grouped, fallback = _fill_numeric_by_group(df, column)
        report.imputed_group[column] = grouped
        report.imputed_fallback[column] = fallback

    downtime_missing = int(df["停机时长"].isna().sum())
    if downtime_missing:
        df["停机时长"] = df["停机时长"].fillna(0.0)
        report.imputed_fallback["停机时长"] = downtime_missing
        report.warnings.append("停机时长缺失按 0 处理（视为未记录停机）。")

    for column in COUNT_COLUMNS:
        rounded = df[column].round()
        fractional = int(((df[column] - rounded).abs() > 1e-9).sum())
        if fractional:
            report.non_integer_counts[column] = fractional
        missing = int(df[column].isna().sum())
        if missing:
            report.kept_missing[column] = missing
        df[column] = rounded.astype("Int64")

    report.invalid_rows = _validate_business_rules(df)

    standard_hours = df["标准工时"].astype("float")
    actual_hours = df["实际工时"].astype("float")
    output_qty = df["产量"].astype("float")
    defect_qty = df["不良数"].astype("float")
    valid_actual = actual_hours.where(actual_hours > 0)
    valid_output = output_qty.where(output_qty > 0)

    df["工时达成率"] = (standard_hours / valid_actual).replace([np.inf, -np.inf], np.nan).round(6)
    df["UPPH"] = (output_qty / valid_actual).replace([np.inf, -np.inf], np.nan).round(6)
    df["不良率"] = (defect_qty / valid_output).replace([np.inf, -np.inf], np.nan).round(6)

    for column in CATEGORY_COLUMNS:
        df[column] = df[column].astype("string")

    if report.kept_missing:
        report.warnings.append(
            "产量/不良数缺失保留为空值，对应 UPPH 与不良率不参与均值计算，避免出现虚假的 0。"
        )
    if report.imputed_fallback.get("标准工时") or report.imputed_fallback.get("实际工时"):
        report.warnings.append("部分工时缺失由全表统计兜底，建议核查原始数据完整度。")
    if report.numeric_coerced:
        report.warnings.append("部分数值字段存在无法解析的内容，已转为空值后参与插补。")
    if report.non_integer_counts:
        report.warnings.append("产量/不良数存在小数，已在计算指标前四舍五入。")
    if "实际工时小于等于 0" in report.invalid_rows:
        report.warnings.append("存在实际工时小于等于 0 的记录，相关行的比率指标为空。")
    if "不良数大于产量" in report.invalid_rows:
        report.warnings.append("存在不良数大于产量的记录，请核对原始数据。")
    if "日期+产线+工序重复" in report.invalid_rows:
        report.warnings.append("存在同日同产线同工序的重复记录，可能是不同班次，未自动合并。")

    df = df.sort_values([DATE_COLUMN, *GROUP_KEYS], na_position="last").reset_index(drop=True)
    report.rows_out = len(df)
    return df, report
