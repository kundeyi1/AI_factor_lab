from pathlib import Path

import pandas as pd

from server.config import DATA_CACHE_DIR


class DataCache:
    @staticmethod
    def _path(stock_code: str) -> Path:
        safe = stock_code.replace(".", "_")
        return DATA_CACHE_DIR / f"{safe}.parquet"

    @classmethod
    def load_stock_data(cls, stock_code: str) -> pd.DataFrame:
        path = cls._path(stock_code)
        if not path.exists():
            return pd.DataFrame()
        try:
            return pd.read_parquet(path)
        except Exception:
            return pd.DataFrame()

    @classmethod
    def save_stock_data(cls, stock_code: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        path = cls._path(stock_code)
        clean = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        clean.to_parquet(path, index=False)
