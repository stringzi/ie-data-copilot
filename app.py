# -*- coding: utf-8 -*-
"""IE Data Copilot 的 Streamlit 前端入口。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from ie_copilot import ai_query, charts, config, data
from ie_copilot.cleaning import CleaningError, clean_dataframe

st.set_page_config(
    page_title="IE Data Copilot",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

PREVIEW_ROWS = 10


@st.cache_data(show_spinner="正在清洗上传的数据…")
def load_uploaded(file_bytes: bytes) -> tuple[pd.DataFrame, dict]:
    """读取并清洗用户上传的 CSV，结果按文件内容缓存。"""
    raw = data.read_csv_bytes(file_bytes)
    cleaned, report = clean_dataframe(raw)
    return cleaned, report.as_dict()


@st.cache_data(show_spinner="正在准备示例数据…")
def load_demo() -> tuple[pd.DataFrame, dict | None]:
    """重新清洗内置示例数据，同时刷新 data/processed 下的演示文件。"""
    cleaned, report = data.build_demo_data()
    return cleaned, report.as_dict() if report else None


def resolve_api_key(manual_key: str) -> tuple[str | None, str]:
    """按 手动输入 → 环境变量/.env → st.secrets 的顺序取 Key。"""
    if manual_key:
        return manual_key, "手动填写"
    env_key = config.get_api_key()
    if env_key:
        return env_key, "环境变量 / .env"
    secret_files = [
        config.PROJECT_ROOT / ".streamlit" / "secrets.toml",
        Path.home() / ".streamlit" / "secrets.toml",
    ]
    secret = None
    if any(path.exists() for path in secret_files):
        try:
            secret = st.secrets.get("DEEPSEEK_API_KEY")
        except Exception:
            secret = None
    if secret:
        return str(secret), "Streamlit secrets"
    return None, "未配置"


def format_value(value, pattern: str, fallback: str = "—") -> str:
    try:
        if value is None or pd.isna(value):
            return fallback
        return pattern.format(value)
    except (TypeError, ValueError):
        return fallback


def render_kpis(df: pd.DataFrame) -> None:
    dates = pd.to_datetime(df["日期"], errors="coerce").dropna()
    day_count = dates.dt.normalize().nunique() if not dates.empty else 0
    date_text = f"{dates.min():%Y-%m-%d} ~ {dates.max():%Y-%m-%d}" if not dates.empty else "—"
    columns = st.columns(5)
    columns[0].metric("数据行数", f"{len(df)}")
    columns[1].metric("覆盖天数", f"{day_count} 天")
    columns[2].metric("平均工时达成率", format_value(df["工时达成率"].mean(), "{:.1%}"))
    columns[3].metric("平均 UPPH", format_value(df["UPPH"].mean(), "{:.1f}"))
    columns[4].metric("平均不良率", format_value(df["不良率"].mean(), "{:.2%}"))
    st.caption(f"日期范围：{date_text} ｜ 平均值为有效记录的算术平均，无法计算的指标不计入分母。")


PREVIEW_STYLE = """
<style>
.ie-preview table { border-collapse: collapse; width: 100%; font-size: 0.8rem; }
.ie-preview th, .ie-preview td { padding: 5px 10px; border-bottom: 1px solid #e6e9ef; text-align: right; white-space: nowrap; }
.ie-preview th { background: #fafafa; font-weight: 600; color: #31333f; }
.ie-preview td:nth-child(-n+3), .ie-preview th:nth-child(-n+3) { text-align: left; }
</style>
"""


def render_preview(df: pd.DataFrame) -> None:
    """展示前 10 行：数字右对齐、缺失值显示为长横线。"""
    styler = (
        df.head(PREVIEW_ROWS)
        .style.format(
            {
                "日期": lambda value: value.strftime("%Y-%m-%d"),
                "标准工时": "{:.2f}",
                "实际工时": "{:.2f}",
                "停机时长": "{:.2f}",
                "产量": "{:.0f}",
                "不良数": "{:.0f}",
                "工时达成率": "{:.3f}",
                "UPPH": "{:.2f}",
                "不良率": "{:.4f}",
            },
            na_rep="—",
        )
        .hide(axis="index")
    )
    st.markdown(
        PREVIEW_STYLE + '<div class="ie-preview">' + styler.to_html() + "</div>",
        unsafe_allow_html=True,
    )


def render_cleaning_report(report: dict | None) -> None:
    if not report:
        return
    title = f"清洗报告：{report['rows_in']} 行 → {report['rows_out']} 行"
    with st.expander(title, expanded=False):
        filled = sum(report["imputed_group"].values()) + sum(report["imputed_fallback"].values())
        kept = sum(report["kept_missing"].values())
        columns = st.columns(4)
        columns[0].metric("删除重复行", report["duplicates_removed"])
        columns[1].metric("删除无效日期", report["invalid_date_rows_removed"])
        columns[2].metric("缺失值填充", filled)
        columns[3].metric("保留空值", kept)

        rows = []
        for column, count in report["imputed_group"].items():
            if count:
                rows.append({"字段": column, "处理方式": "同产线+工序统计值填充", "行数": count})
        for column, count in report["imputed_fallback"].items():
            if count:
                rows.append({"字段": column, "处理方式": "全表统计值/零值兜底", "行数": count})
        for column, count in report["kept_missing"].items():
            rows.append({"字段": column, "处理方式": "保留空值，不参与指标均值", "行数": count})
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

        for name, count in report["invalid_rows"].items():
            st.warning(f"数据校验 - {name}：{count} 行")
        for item in report["warnings"]:
            st.info(item)


def render_figure(fig, caption: str) -> None:
    if fig is None:
        st.info(f"{caption}：当前数据不足，已跳过。")
        return
    st.pyplot(fig)
    charts.close_figure(fig)


def render_result(result: ai_query.QueryResult) -> None:
    if result.status == "error":
        st.error(result.message)
        return
    if result.status == "unanswerable":
        st.info(result.message)
        return

    answer = result.answer
    if isinstance(answer, pd.DataFrame):
        st.dataframe(answer, hide_index=True, use_container_width=True)
    elif isinstance(answer, pd.Series):
        st.dataframe(answer.to_frame(), use_container_width=True)
    else:
        st.write(answer)

    for item in result.warnings:
        st.warning(item)
    if result.code:
        with st.expander("查看生成的代码"):
            st.code(result.code, language="python")
    st.caption("代码由模型生成并在受限沙箱中执行，重要结论请结合业务复核。")


def render_qa_section(df: pd.DataFrame, data_key: str, api_key: str | None, key_source: str) -> None:
    st.divider()
    st.subheader("向数据提问")
    st.caption("模型会把问题转换成 pandas 代码，在当前数据集上执行，并返回表格、数值或文字结论。")

    with st.form("qa_form"):
        question = st.text_input(
            "用自然语言提问",
            placeholder="例如：A 线的平均工时达成率是多少？哪道工序不良率最高？",
        )
        submitted = st.form_submit_button("提交问题", type="primary")

    if submitted:
        if not question.strip():
            st.warning("请先输入问题。")
        elif api_key is None:
            st.info(
                "未配置 DeepSeek API Key，问答功能不可用。"
                "请设置环境变量 DEEPSEEK_API_KEY、在 .env 中配置，或使用侧边栏“高级设置”。"
            )
        else:
            with st.spinner("正在生成分析代码并执行……"):
                result = ai_query.ask_data(question.strip(), df=df, api_key=api_key)
            st.session_state["qa_result"] = result
            st.session_state["qa_question"] = question.strip()
            st.session_state["qa_data_key"] = data_key

    result = st.session_state.get("qa_result")
    if result is None or st.session_state.get("qa_data_key") != data_key:
        return

    st.markdown("#### 回答")
    st.caption(f"问题：{st.session_state.get('qa_question', '')} ｜ 密钥来源：{key_source}")
    render_result(result)


def main() -> None:
    with st.sidebar:
        st.header("数据")
        uploaded = st.file_uploader("上传生产数据 CSV", type=["csv"])
        st.caption("未上传时使用内置示例数据。上传后会自动完成去重、缺失值处理与指标计算。")
        with st.expander("高级设置"):
            st.text_input(
                "临时 DeepSeek API Key",
                type="password",
                help="仅保存在当前会话中。正式使用请配置环境变量或 .env。",
                key="manual_api_key_input",
            )

    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        try:
            df, report = load_uploaded(file_bytes)
        except CleaningError as exc:
            st.error(f"数据格式不符合要求：{exc}")
            st.stop()
        except Exception as exc:
            st.error(f"读取或清洗失败：{exc}")
            st.stop()
        source_label = uploaded.name
        data_key = hashlib.sha1(file_bytes).hexdigest()[:12]
    else:
        df, report = load_demo()
        source_label = "内置示例数据"
        data_key = "demo"

    with st.sidebar:
        st.success(f"当前数据：{source_label}")
        st.download_button(
            "下载清洗后 CSV",
            data=df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"cleaned_{data_key}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    api_key, key_source = resolve_api_key(st.session_state.get("manual_api_key_input", ""))
    with st.sidebar:
        if api_key:
            st.caption(f"问答状态：可用（{key_source}）")
        else:
            st.caption("问答状态：未配置 API Key")

    st.title("IE Data Copilot")
    st.caption("工业工程数据分析助手：上传 CSV → 自动清洗 → 指标看板 → 自然语言问答")

    render_kpis(df)

    st.subheader("数据预览")
    st.caption(f"共 {len(df)} 行，展示前 {min(len(df), PREVIEW_ROWS)} 行")
    render_preview(df)

    render_cleaning_report(report)

    st.subheader("可视化分析")
    left, right = st.columns(2)
    with left:
        render_figure(charts.make_avg_achievement_rate_fig(df), "各产线平均工时达成率")
    with right:
        render_figure(charts.make_daily_upph_fig(df), "每日 UPPH 变化趋势")
    render_figure(charts.make_defect_rate_fig(df), "各工序平均不良率对比")

    render_qa_section(df, data_key, api_key, key_source)

    st.divider()
    st.caption(
        f"数据来源：{source_label} ｜ 清洗规则见 docs/PRD.md ｜ "
        "AI 生成的分析代码可能存在误差，请人工复核后再用于汇报。"
    )


if __name__ == "__main__":
    main()
