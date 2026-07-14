from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

DEFAULT_EXPRESSION = "ts_rank(power(abs(pctChg), 2), 5) * ts_rank(power(abs(ts_delta(close, 1)), 2), 5)"
DEFAULT_DESCRIPTION = "该因子强调短期价格波动与收盘价变化，用于观察情绪反弹和价格反转。"


def _secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except FileNotFoundError:
        value = default
    return str(value) if value is not None else default


@st.cache_resource(show_spinner=False)
def prepare_runtime() -> tuple[object, object, list[dict[str, str]]]:
    data_root = Path(
        os.environ.get("QUANT_DATA_ROOT")
        or _secret("QUANT_DATA_ROOT")
        or "/tmp/ai-factor-lab-data"
    ).expanduser()
    os.environ["QUANT_DATA_ROOT"] = str(data_root)
    os.environ.setdefault("AI_FACTOR_LAB_CACHE_DIR", str(data_root / "data_cache"))
    os.environ.setdefault("AI_FACTOR_LAB_OFFLINE_DATA_ONLY", "true")
    os.environ.setdefault("HF_DATASET_REPO", _secret("HF_DATASET_REPO", "kundeyi/ai-factor-lab-data"))
    os.environ.setdefault("HF_DATA_ARCHIVE", _secret("HF_DATA_ARCHIVE", "quant_data.tar"))
    token = _secret("HF_DATA_TOKEN")
    if token:
        os.environ["HF_DATA_TOKEN"] = token

    from scripts.start_hf import ensure_data

    ready_root = ensure_data()
    os.environ["QUANT_DATA_ROOT"] = str(ready_root)

    from server.ai.generator import factor_generator
    from server.backtest.backtester import Backtester
    from server.data.fetcher import get_available_pools

    return Backtester(), factor_generator, get_available_pools()


def initialize_session() -> None:
    defaults = {
        "factor_name": "短期情绪反弹因子",
        "factor_expression": DEFAULT_EXPRESSION,
        "factor_description": DEFAULT_DESCRIPTION,
        "factor_library": [],
        "last_result": None,
        "last_expression": "",
        "chat_history": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def render_result(result: dict) -> None:
    metrics = result.get("metrics", {})
    columns = st.columns(5)
    labels = [
        ("多空年化收益", "long_short_annual_return"),
        ("多空夏普", "long_short_sharpe"),
        ("最大回撤", "max_drawdown"),
        ("IC 均值", "ic_mean"),
        ("IC IR", "ic_ir"),
    ]
    for column, (label, key) in zip(columns, labels):
        column.metric(label, metrics.get(key, "--"))

    dates = pd.to_datetime(result.get("dates", []))
    series = result.get("series", {})
    if len(dates) and series:
        chart = pd.DataFrame(series, index=dates)
        chart.index.name = "日期"
        st.subheader("分层净值曲线")
        st.line_chart(chart, width="stretch")

    table = result.get("table", [])
    if table:
        st.subheader("分层绩效指标")
        st.dataframe(pd.DataFrame(table), width="stretch", hide_index=True)


st.set_page_config(page_title="AI Factor Lab", page_icon="📈", layout="wide")
initialize_session()

st.title("AI Factor Lab")
st.caption("描述或编辑因子表达式，使用内置离线行情完成分层回测。")

try:
    with st.spinner("首次启动正在准备离线行情数据，可能需要几分钟……"):
        backtester, factor_generator, pools = prepare_runtime()
except Exception as exc:
    st.error(f"数据环境初始化失败：{exc}")
    st.info("部署者需要在 Streamlit Secrets 中配置私有数据集的只读 HF_DATA_TOKEN。")
    st.stop()

with st.sidebar:
    st.header("AI 生成表达式（可选）")
    provider = st.selectbox("供应商", ["deepseek", "openai"], format_func=lambda x: x.title())
    api_key = st.text_input("模型 API Key", type="password", help="仅用于本次会话调用，不保存到项目。")
    factor_idea = st.text_area("因子想法", placeholder="例如：寻找短期超跌后反弹的股票")
    if st.button("生成因子", width="stretch"):
        if not factor_idea.strip():
            st.warning("请先输入因子想法。")
        elif not api_key.strip():
            st.warning("请提供所选供应商的 API Key，或者直接编辑表达式回测。")
        else:
            try:
                generated = factor_generator.generate_factor(
                    factor_idea.strip(),
                    history=st.session_state.chat_history,
                    api_key=api_key.strip(),
                    provider=provider,
                )
                st.session_state.factor_name = generated["name"]
                st.session_state.factor_expression = generated["expression"]
                st.session_state.factor_description = generated["description"]
                st.session_state.chat_history.extend(
                    [
                        {"role": "user", "content": factor_idea.strip()},
                        {"role": "model", "content": str(generated)},
                    ]
                )
                st.success("表达式已生成，请在主页面确认后回测。")
                st.rerun()
            except Exception as exc:
                st.error(f"生成失败：{exc}")

    st.divider()
    st.header("本次会话的因子库")
    library = st.session_state.factor_library
    if not library:
        st.caption("完成回测后可以保存当前因子；刷新或休眠后不保证保留。")
    for index, item in enumerate(library):
        if st.button(item["name"], key=f"load-factor-{index}", width="stretch"):
            st.session_state.factor_name = item["name"]
            st.session_state.factor_expression = item["expression"]
            st.session_state.factor_description = item["description"]
            st.rerun()

name_col, save_col = st.columns([5, 1])
with name_col:
    st.text_input("因子名称", key="factor_name")
with save_col:
    st.write("")
    st.write("")
    can_save = bool(
        st.session_state.last_result
        and st.session_state.last_expression == st.session_state.factor_expression.strip()
    )
    if st.button("保存到会话", disabled=not can_save, width="stretch"):
        item = {
            "name": st.session_state.factor_name.strip() or "未命名因子",
            "expression": st.session_state.factor_expression.strip(),
            "description": st.session_state.factor_description.strip(),
        }
        st.session_state.factor_library = [
            item,
            *[saved for saved in st.session_state.factor_library if saved["name"] != item["name"]],
        ]
        st.success("已保存到当前浏览器会话。")

st.text_area("因子表达式", key="factor_expression", height=120)
st.text_area("因子说明", key="factor_description", height=90)

controls = st.columns([1.2, 1.2, 1.3, 0.8, 0.8])
start_date = controls[0].date_input("开始日期", value=pd.Timestamp("2025-06-20"))
end_date = controls[1].date_input("结束日期", value=pd.Timestamp("2026-06-01"))
pool_options = {item["value"]: item["label"] for item in pools}
pool = controls[2].selectbox("股票池", list(pool_options), format_func=pool_options.get)
layers = controls[3].selectbox("分层", [3, 5, 10], index=1)
freq = controls[4].selectbox("调仓", ["D", "W", "M"], format_func={"D": "日频", "W": "周频", "M": "月频"}.get)

if st.button("开始回测", type="primary", width="stretch"):
    expression = st.session_state.factor_expression.strip()
    if not expression:
        st.error("因子表达式不能为空。")
    elif start_date >= end_date:
        st.error("开始日期必须早于结束日期。")
    else:
        progress_bar = st.progress(0, text="任务已创建")

        def update_progress(percent: int, message: str) -> None:
            progress_bar.progress(min(max(percent, 0), 100), text=message)

        try:
            result = backtester.run(
                expression,
                start_date.isoformat(),
                end_date.isoformat(),
                pool,
                freq,
                layers,
                progress=update_progress,
            )
            st.session_state.last_result = result
            st.session_state.last_expression = expression
            progress_bar.progress(100, text="回测完成")
            st.success("回测完成。")
        except Exception as exc:
            st.session_state.last_result = None
            st.error(f"回测失败：{exc}")

if st.session_state.last_result:
    render_result(st.session_state.last_result)
else:
    st.info("尚未运行回测。默认表达式和日期可直接用于 smoke。")
