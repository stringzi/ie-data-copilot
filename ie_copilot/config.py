# -*- coding: utf-8 -*-
"""项目路径与运行时配置。"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_CSV = DATA_DIR / "raw" / "simulated_production_hours.csv"
PROCESSED_CSV = DATA_DIR / "processed" / "cleaned_data.csv"
REPORT_JSON = DATA_DIR / "processed" / "cleaning_report.json"

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"


def _load_env_file() -> None:
    """若安装了 python-dotenv，则自动读取项目根目录的 .env（不覆盖已有环境变量）。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(PROJECT_ROOT / ".env", override=False)


_load_env_file()


def get_api_key() -> str | None:
    """读取 DeepSeek API Key，未配置时返回 None。"""
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    return key or None


def get_base_url() -> str:
    """读取 API Base URL，便于切换到其他 OpenAI 兼容服务。"""
    return os.getenv("DEEPSEEK_BASE_URL", DEFAULT_BASE_URL).strip() or DEFAULT_BASE_URL


def get_model() -> str:
    """读取模型名称。"""
    return os.getenv("DEEPSEEK_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
