import numpy as np
import pandas as pd


def _max_drawdown(returns: pd.Series) -> float:
    nav = (1 + returns.fillna(0)).cumprod()
    peak = nav.cummax()
    return ((nav - peak) / peak).min()


def _format_pct(value: float) -> str:
    if pd.isna(value) or np.isinf(value):
        return "--"
    return f"{value * 100:.2f}%"


def _format_num(value: float, digits: int = 2) -> str:
    if pd.isna(value) or np.isinf(value):
        return "--"
    return f"{value:.{digits}f}"


def calculate_metrics(layer_returns: pd.DataFrame, panel_df: pd.DataFrame, periods_per_year: int) -> dict:
    metrics = {}
    table = []

    for col in layer_returns.columns:
        returns = layer_returns[col].fillna(0)
        years = max(len(returns) / periods_per_year, 1 / periods_per_year)
        cumulative = (1 + returns).prod()
        ann_return = cumulative ** (1 / years) - 1
        ann_vol = returns.std() * np.sqrt(periods_per_year)
        sharpe = ann_return / ann_vol if ann_vol and not pd.isna(ann_vol) else 0.0
        max_dd = _max_drawdown(returns)
        win_rate = (returns > 0).mean()

        item = {
            "name": str(col),
            "annual_return": _format_pct(ann_return),
            "annual_volatility": _format_pct(ann_vol),
            "sharpe": _format_num(sharpe),
            "max_drawdown": _format_pct(max_dd),
            "win_rate": _format_pct(win_rate),
        }
        table.append(item)
        metrics[str(col)] = item

    if {"factor_norm", "next_return"}.issubset(panel_df.columns):
        ic_frame = panel_df[["date", "factor_norm", "next_return"]]
        daily_ic = ic_frame.groupby("date")[["factor_norm", "next_return"]].apply(
            lambda x: x["factor_norm"].corr(x["next_return"])
        )
        daily_rank_ic = ic_frame.groupby("date")[["factor_norm", "next_return"]].apply(
            lambda x: x["factor_norm"].corr(x["next_return"], method="spearman")
        )
        ic_mean = daily_ic.mean()
        ic_ir = ic_mean / daily_ic.std() if daily_ic.std() and not pd.isna(daily_ic.std()) else 0.0
        rank_ic_mean = daily_rank_ic.mean()
        rank_ic_ir = rank_ic_mean / daily_rank_ic.std() if daily_rank_ic.std() and not pd.isna(daily_rank_ic.std()) else 0.0
    else:
        ic_mean = ic_ir = rank_ic_mean = rank_ic_ir = 0.0

    return {
        "summary": {
            "long_short_annual_return": metrics.get("多空对冲组合", {}).get("annual_return", "--"),
            "long_short_sharpe": metrics.get("多空对冲组合", {}).get("sharpe", "--"),
            "max_drawdown": metrics.get("多空对冲组合", {}).get("max_drawdown", "--"),
            "ic_mean": _format_num(ic_mean, 4),
            "ic_ir": _format_num(ic_ir, 4),
            "rank_ic_mean": _format_num(rank_ic_mean, 4),
            "rank_ic_ir": _format_num(rank_ic_ir, 4),
        },
        "by_series": metrics,
        "table": table,
    }
