import logging
import os
from datetime import datetime

import pandas as pd

from server.data.cache import DataCache

logger = logging.getLogger(__name__)


POOL_CONFIG = {
    "hs300": {"label": "沪深300（core: 000300）", "core_universes": ["000300"]},
    "zz500": {"label": "中证500（core: 000905）", "core_universe": "000905"},
    "zz1000": {"label": "中证1000（core: 000852）", "core_universe": "000852"},
    "csi1800": {"label": "1800（沪深300+中证500+中证1000）", "core_universes": ["000300", "000905", "000852"]},
}


def get_available_pools() -> list[dict[str, str]]:
    return [{"value": value, "label": config["label"]} for value, config in POOL_CONFIG.items()]


class DataFetcher:
    def __init__(self) -> None:
        self._bs_logged_in = False
        self._offline_data_only = os.getenv("AI_FACTOR_LAB_OFFLINE_DATA_ONLY", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _login_baostock(self):
        import baostock as bs

        if self._bs_logged_in:
            return bs
        lg = bs.login()
        if lg.error_code != "0":
            raise ConnectionError(f"Baostock 登录失败：{lg.error_msg}")
        self._bs_logged_in = True
        return bs

    def get_index_components(self, index_code: str = "hs300", date: str | None = None) -> list[str]:
        date = date or datetime.now().strftime("%Y-%m-%d")
        pool = POOL_CONFIG.get(index_code)
        if not pool:
            logger.error("Unsupported stock pool: %s", index_code)
            return []

        try:
            from core.data.DataManager import UniverseManager

            manager = UniverseManager()
            universes = pool.get("core_universes") or [pool["core_universe"]]
            members = sorted(
                {
                    member
                    for universe in universes
                    for member in manager.get_members(universe, date)
                }
            )
            return [self._to_prefixed_code(code) for code in members]
        except Exception as exc:
            logger.error("Core universe lookup failed for %s: %s", index_code, exc)
            return []

    def get_local_pool_data(self, stock_codes: list[str], start_date: str, end_date: str) -> pd.DataFrame:
        """Load a whole pool from Quant's shared local parquet store in one pass."""
        if not stock_codes:
            return pd.DataFrame()

        try:
            from core.data.DataManager import DataProvider

            codes = [code.split(".")[-1] for code in stock_codes]
            local = DataProvider().load_stock_ohlcv_from_daily_parquet(
                fq="qfq",
                start_date=start_date,
                end_date=end_date,
                codes=codes,
            )
        except (FileNotFoundError, ImportError) as exc:
            logger.info("Local Quant parquet store is unavailable: %s", exc)
            return pd.DataFrame()
        except Exception as exc:
            logger.warning("Local Quant parquet load failed: %s", exc)
            return pd.DataFrame()

        if local.empty:
            return pd.DataFrame()

        clean = local.copy()
        clean["stock_code"] = clean["code"].map(self._to_prefixed_code)
        clean["date"] = pd.to_datetime(clean["date"]).dt.strftime("%Y-%m-%d")
        clean = clean.sort_values(["stock_code", "date"]).reset_index(drop=True)

        for column in ["open", "high", "low", "close", "volume", "amount"]:
            if column not in clean.columns:
                clean[column] = pd.NA
            clean[column] = pd.to_numeric(clean[column], errors="coerce")

        clean["pctChg"] = clean.groupby("stock_code")["close"].pct_change(fill_method=None) * 100.0
        clean["turn"] = pd.NA
        clean["vwap"] = pd.NA
        return clean[
            [
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "turn",
                "pctChg",
                "vwap",
                "stock_code",
            ]
        ]

    def get_stock_k_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        cached = DataCache.load_stock_data(stock_code)
        if not cached.empty and start_date >= cached["date"].min() and end_date <= cached["date"].max():
            return cached[(cached["date"] >= start_date) & (cached["date"] <= end_date)].copy()
        if self._offline_data_only:
            if cached.empty:
                return pd.DataFrame()
            return cached[(cached["date"] >= start_date) & (cached["date"] <= end_date)].copy()

        fetched = self._fetch_from_sources(stock_code, start_date, end_date)
        if fetched.empty:
            if cached.empty:
                return pd.DataFrame()
            return cached[(cached["date"] >= start_date) & (cached["date"] <= end_date)].copy()

        combined = pd.concat([cached, fetched], ignore_index=True) if not cached.empty else fetched
        DataCache.save_stock_data(stock_code, combined)
        combined = DataCache.load_stock_data(stock_code)
        return combined[(combined["date"] >= start_date) & (combined["date"] <= end_date)].copy()

    def _fetch_from_sources(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        for fetcher in (self._fetch_baostock, self._fetch_akshare):
            df = fetcher(stock_code, start_date, end_date)
            if not df.empty:
                return df
        return pd.DataFrame()

    def _fetch_baostock(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        try:
            bs = self._login_baostock()
            fields = "date,open,high,low,close,volume,amount,turn,pctChg"
            rs = bs.query_history_k_data_plus(
                stock_code,
                fields,
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="3",
            )
            rows = []
            if rs and rs.error_code == "0":
                while rs.next():
                    rows.append(rs.get_row_data())
            if not rows:
                return pd.DataFrame()
            df = pd.DataFrame(rows, columns=rs.fields)
            return self._normalize_k_data(df)
        except Exception as exc:
            logger.warning("Baostock k-data failed for %s: %s", stock_code, exc)
            return pd.DataFrame()

    def _fetch_akshare(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        try:
            import akshare as ak

            symbol = stock_code.split(".")[-1]
            df = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.replace("-", ""),
                end_date=end_date.replace("-", ""),
                adjust="hfq",
            )
            if df.empty:
                return pd.DataFrame()
            df = df.rename(
                columns={
                    "日期": "date",
                    "开盘": "open",
                    "收盘": "close",
                    "最高": "high",
                    "最低": "low",
                    "成交量": "volume",
                    "成交额": "amount",
                    "换手率": "turn",
                    "涨跌幅": "pctChg",
                }
            )
            return self._normalize_k_data(df)
        except Exception as exc:
            logger.warning("AkShare k-data failed for %s: %s", stock_code, exc)
            return pd.DataFrame()

    def _normalize_k_data(self, df: pd.DataFrame) -> pd.DataFrame:
        required = ["date", "open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]
        if any(col not in df.columns for col in required):
            return pd.DataFrame()
        clean = df[required].copy()
        clean["date"] = pd.to_datetime(clean["date"]).dt.strftime("%Y-%m-%d")
        for col in required[1:]:
            clean[col] = pd.to_numeric(clean[col], errors="coerce")
        clean["vwap"] = clean["amount"] / clean["volume"].replace(0, pd.NA)
        clean["vwap"] = clean["vwap"].fillna(clean["close"])
        return clean.dropna(subset=["close", "pctChg"])

    def _find_column(self, df: pd.DataFrame, candidates: list[str]) -> str:
        for candidate in candidates:
            if candidate in df.columns:
                return candidate
        raise KeyError(f"未找到成分股代码列，可用列：{list(df.columns)}")

    def _to_prefixed_code(self, code: str) -> str:
        raw = code.strip().split(".")[0].zfill(6)
        prefix = "sh" if raw.startswith(("5", "6", "9")) else "sz"
        return f"{prefix}.{raw}"
