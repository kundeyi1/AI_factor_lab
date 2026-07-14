import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from server.backtest.metrics import calculate_metrics
from server.data.fetcher import DataFetcher
from server.factors.engine import FactorEngine

logger = logging.getLogger(__name__)


class Backtester:
    def __init__(self) -> None:
        self.fetcher = DataFetcher()

    def run(
        self,
        factor_expression: str,
        start_date: str,
        end_date: str,
        pool: str,
        freq: str,
        layers: int,
        progress=None,
    ) -> dict:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        hist_start = (start_dt - timedelta(days=365)).strftime("%Y-%m-%d")

        self._update(progress, 3, "读取指数成分股...")
        stocks = self.fetcher.get_index_components(pool, start_date)
        if not stocks:
            raise ValueError(f"无法获取股票池成分：{pool}")

        self._update(progress, 5, "批量读取主机本地行情...")
        local_panel = self.fetcher.get_local_pool_data(stocks, hist_start, end_date)
        frames = [local_panel] if not local_panel.empty else []
        loaded_codes = set(local_panel["stock_code"].unique()) if not local_panel.empty else set()
        missing_stocks = [stock for stock in stocks if stock not in loaded_codes]

        if loaded_codes:
            self._update(progress, 45, f"已从本地数据读取 {len(loaded_codes)}/{len(stocks)} 支股票")

        total_missing = len(missing_stocks)
        for index, stock in enumerate(missing_stocks, start=1):
            percent = 45 + int(index / max(total_missing, 1) * 5)
            self._update(progress, percent, f"补充缺失行情：{stock} ({index}/{total_missing})")
            try:
                df = self.fetcher.get_stock_k_data(stock, hist_start, end_date)
                if not df.empty:
                    df["stock_code"] = stock
                    frames.append(df)
            except Exception as exc:
                logger.warning("skip %s: %s", stock, exc)

        if not frames:
            raise ValueError("没有可用行情数据，无法回测。")

        self._update(progress, 55, "计算因子值...")
        panel = pd.concat(frames, ignore_index=True)
        panel["date"] = pd.to_datetime(panel["date"])
        panel = panel.sort_values(["stock_code", "date"])
        panel["factor_value"] = FactorEngine.calculate_factor(panel, factor_expression)
        panel = panel[panel["date"] >= pd.Timestamp(start_date)].copy()
        panel = panel.dropna(subset=["factor_value"])
        if panel.empty:
            raise ValueError("因子值全部为空，请检查表达式或日期范围。")

        self._update(progress, 68, "截面去极值和标准化...")
        panel["next_return"] = panel.groupby("stock_code")["pctChg"].shift(-1) / 100.0
        panel = panel.dropna(subset=["next_return"])
        panel["factor_norm"] = panel.groupby("date")["factor_value"].transform(self._winsorized_zscore)
        panel = panel.dropna(subset=["factor_norm"])

        self._update(progress, 76, "分层并计算组合收益...")
        panel["layer"] = panel.groupby("date")["factor_norm"].transform(lambda x: self._assign_layer(x, layers))
        panel = panel.dropna(subset=["layer"])
        if panel.empty:
            raise ValueError("分层后无有效样本，可能是样本数量不足或因子值过于集中。")

        layer_returns = panel.groupby(["date", "layer"])["next_return"].mean().unstack().sort_index()
        layer_returns = layer_returns.rename(columns={i: f"层 {int(i)}" for i in layer_returns.columns})
        lowest = "层 1"
        highest = f"层 {layers}"
        if lowest in layer_returns.columns and highest in layer_returns.columns:
            layer_returns["多空对冲组合"] = layer_returns[highest] - layer_returns[lowest]

        layer_returns = self._resample_returns(layer_returns, freq)
        nav = (1 + layer_returns.fillna(0)).cumprod()
        nav.index = pd.to_datetime(nav.index)
        periods_per_year = {"D": 252, "W": 52, "M": 12}.get(freq, 252)

        self._update(progress, 90, "计算绩效指标...")
        metric_payload = calculate_metrics(layer_returns, panel, periods_per_year)
        self._update(progress, 100, "回测完成")

        return {
            "dates": nav.index.strftime("%Y-%m-%d").tolist(),
            "series": {column: nav[column].round(6).fillna(1).tolist() for column in nav.columns},
            "metrics": metric_payload["summary"],
            "table": metric_payload["table"],
        }

    def _resample_returns(self, returns: pd.DataFrame, freq: str) -> pd.DataFrame:
        if freq == "D":
            return returns
        rule = "W-FRI" if freq == "W" else "M"
        return (1 + returns.fillna(0)).resample(rule).prod() - 1

    def _winsorized_zscore(self, x: pd.Series) -> pd.Series:
        lower = x.quantile(0.01)
        upper = x.quantile(0.99)
        clipped = x.clip(lower, upper)
        std = clipped.std()
        if not std or np.isnan(std):
            return pd.Series(index=x.index, data=np.nan)
        return (clipped - clipped.mean()) / std

    def _assign_layer(self, x: pd.Series, layers: int) -> pd.Series:
        try:
            ranked = x.rank(method="first")
            return pd.qcut(ranked, layers, labels=False, duplicates="drop") + 1
        except Exception:
            return pd.Series(index=x.index, data=np.nan)

    def _update(self, progress, percent: int, message: str) -> None:
        if progress:
            progress(percent, message)
