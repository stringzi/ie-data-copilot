# -*- coding: utf-8 -*-
"""数据读写：内置示例数据、清洗结果与报告落盘。"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pandas as pd

from .cleaning import DATE_COLUMN, CleaningReport, clean_dataframe
from .config import PROCESSED_CSV, RAW_CSV, REPORT_JSON


def read_csv_flexible(path: Path | str) -> pd.DataFrame:
    """读取 CSV，自动兼容 UTF-8 BOM 与 GB18030（Excel 中文导出常见编码）。"""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return pd.read_csv(path, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"无法识别 CSV 编码：{last_error}")


def read_csv_bytes(file_bytes: bytes) -> pd.DataFrame:
    """从上传的字节流读取 CSV。"""
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return pd.read_csv(BytesIO(file_bytes), encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"无法识别 CSV 编码：{last_error}")


def save_processed(df: pd.DataFrame, report: CleaningReport | None = None) -> None:
    """保存清洗后的数据与清洗报告（UTF-8 BOM，Excel 可直接打开）。"""
    PROCESSED_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_CSV, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    if report is not None:
        REPORT_JSON.write_text(
            json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def build_demo_data(write: bool = True) -> tuple[pd.DataFrame, CleaningReport | None]:
    """从原始示例数据重新清洗；原始文件缺失时回退到已清洗数据。"""
    if RAW_CSV.exists():
        df, report = clean_dataframe(read_csv_flexible(RAW_CSV))
        if write:
            try:
                save_processed(df, report)
            except OSError:
                # 只读部署环境（如部分托管平台）无法写盘时，仍返回内存中的清洗结果
                pass
        return df, report
    if PROCESSED_CSV.exists():
        return pd.read_csv(PROCESSED_CSV, parse_dates=[DATE_COLUMN]), None
    raise FileNotFoundError(
        f"未找到示例数据：{RAW_CSV}。请从仓库重新获取 data/raw/simulated_production_hours.csv。"
    )


def load_default_dataframe() -> pd.DataFrame:
    """问答模块使用的默认数据集。"""
    df, _ = build_demo_data(write=False)
    return df
