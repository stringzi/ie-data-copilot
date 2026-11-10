# -*- coding: utf-8 -*-
"""可视化模块：直接返回 matplotlib Figure，不写共享磁盘文件。

这样多个用户同时使用在线 Demo 时，不会互相覆盖同一张 PNG。
"""

from __future__ import annotations

import re
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from matplotlib import font_manager

LINE_ORDER_HINT = ["A线", "B线", "C线"]
PROCESS_ORDER_HINT = ["冲压", "焊接", "组装", "检测", "包装"]
CJK_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "SimHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
    "Arial Unicode MS",
]

_font_name: str | None = None
_font_configured = False


def setup_chinese_font() -> str | None:
    """按平台可用字体配置中文显示，返回选中的字体名。"""
    global _font_name, _font_configured
    if _font_configured:
        return _font_name

    sns.set_theme(style="whitegrid")
    available = {font.name for font in font_manager.fontManager.ttflist}
    _font_name = next((name for name in CJK_FONT_CANDIDATES if name in available), None)

    if _font_name:
        plt.rcParams["font.sans-serif"] = [_font_name, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["figure.dpi"] = 120
    plt.rcParams["savefig.dpi"] = 200
    plt.rcParams["savefig.bbox"] = "tight"
    _font_configured = True

    if _font_name is None:
        warnings.warn(
            "未检测到中文字体，图表中的中文可能显示为方框。Linux 环境可安装 fonts-noto-cjk。",
            RuntimeWarning,
            stacklevel=2,
        )
    return _font_name


def close_figure(fig: plt.Figure) -> None:
    """关闭图形，释放内存。"""
    plt.close(fig)


def _natural_key(value: object) -> list:
    return [int(part) if part.isdigit() else part for part in re.split(r"(\d+)", str(value))]


def _ordered_categories(series: pd.Series, preferred: list[str]) -> list[str]:
    """优先使用业务顺序，其余取值按自然顺序追加，避免上传数据的产线被丢弃。"""
    values = [str(value) for value in pd.Series(series).dropna().unique()]
    ordered = [value for value in preferred if value in values]
    return ordered + sorted([value for value in values if value not in ordered], key=_natural_key)


def make_avg_achievement_rate_fig(df: pd.DataFrame) -> plt.Figure | None:
    """各产线平均工时达成率柱状图（含基准线 1.0）。"""
    if not {"产线", "工时达成率"}.issubset(df.columns):
        return None
    data = df.dropna(subset=["产线", "工时达成率"])
    if data.empty:
        return None

    setup_chinese_font()
    summary = (
        data.groupby("产线", as_index=False)["工时达成率"]
        .mean()
        .rename(columns={"工时达成率": "平均工时达成率"})
    )
    order = _ordered_categories(summary["产线"], LINE_ORDER_HINT)
    summary["产线"] = pd.Categorical(summary["产线"].astype(str), categories=order, ordered=True)
    summary = summary.sort_values("产线")

    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    sns.barplot(
        data=summary,
        x="产线",
        y="平均工时达成率",
        hue="产线",
        palette="Blues_d",
        legend=False,
        ax=ax,
    )
    ax.axhline(1.0, color="#d62728", linestyle="--", linewidth=1.6, label="基准线 1.0")
    ax.set_title("各产线平均工时达成率", fontsize=14, pad=12)
    ax.set_xlabel("产线")
    ax.set_ylabel("平均工时达成率")
    top = float(summary["平均工时达成率"].max())
    ax.set_ylim(0, max(1.15, top * 1.12))
    ax.legend(loc="upper right")
    for container in ax.containers:
        ax.bar_label(container, fmt="%.3f", padding=3)
    fig.tight_layout()
    return fig


def make_daily_upph_fig(df: pd.DataFrame) -> plt.Figure | None:
    """每日 UPPH 变化趋势（按产线）。同一天多工序先取均值。"""
    if not {"日期", "产线", "UPPH"}.issubset(df.columns):
        return None
    data = df.dropna(subset=["日期", "产线", "UPPH"])
    if data.empty:
        return None

    setup_chinese_font()
    daily = data.groupby(["日期", "产线"], as_index=False)["UPPH"].mean()
    order = _ordered_categories(daily["产线"], LINE_ORDER_HINT)
    daily["产线"] = pd.Categorical(daily["产线"].astype(str), categories=order, ordered=True)
    daily = daily.sort_values(["产线", "日期"])

    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    sns.lineplot(
        data=daily,
        x="日期",
        y="UPPH",
        hue="产线",
        hue_order=order,
        marker="o",
        linewidth=2,
        ax=ax,
    )
    ax.set_title("每日 UPPH 变化趋势（按产线）", fontsize=14, pad=12)
    ax.set_xlabel("日期")
    ax.set_ylabel("日均 UPPH")
    ax.legend(title="产线")
    fig.autofmt_xdate()
    fig.tight_layout()
    return fig


def make_defect_rate_fig(df: pd.DataFrame) -> plt.Figure | None:
    """各工序平均不良率对比柱状图。"""
    if not {"工序", "不良率"}.issubset(df.columns):
        return None
    data = df.dropna(subset=["工序", "不良率"])
    if data.empty:
        return None

    setup_chinese_font()
    summary = (
        data.groupby("工序", as_index=False)["不良率"]
        .mean()
        .rename(columns={"不良率": "平均不良率"})
    )
    order = _ordered_categories(summary["工序"], PROCESS_ORDER_HINT)
    summary["工序"] = pd.Categorical(summary["工序"].astype(str), categories=order, ordered=True)
    summary = summary.sort_values("工序")

    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    sns.barplot(
        data=summary,
        x="工序",
        y="平均不良率",
        hue="工序",
        palette="Oranges_d",
        legend=False,
        ax=ax,
    )
    ax.set_title("各工序平均不良率对比", fontsize=14, pad=12)
    ax.set_xlabel("工序")
    ax.set_ylabel("平均不良率")
    top = float(summary["平均不良率"].max())
    ax.set_ylim(0, max(top * 1.15, 0.01))
    for container in ax.containers:
        ax.bar_label(container, fmt=lambda value: f"{value:.2%}", padding=3)
    fig.tight_layout()
    return fig


CHART_EXPORTS = [
    (make_avg_achievement_rate_fig, "avg_achievement_rate_by_line.png"),
    (make_daily_upph_fig, "daily_upph_trend.png"),
    (make_defect_rate_fig, "defect_rate_by_process.png"),
]


def export_all(df: pd.DataFrame, output_dir: Path | str) -> list[Path]:
    """导出三张图到指定目录（用于生成 README 素材）。"""
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for maker, filename in CHART_EXPORTS:
        fig = maker(df)
        if fig is None:
            continue
        path = target / filename
        fig.savefig(path, dpi=200, bbox_inches="tight")
        close_figure(fig)
        written.append(path)
    return written
