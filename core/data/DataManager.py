import pandas as pd
import numpy as np
import os
import warnings
import zipfile
import io
import json
from pathlib import Path
from typing import Iterable
from core.config import DATA_ROOT
from core.utils.Logger import get_logger
from core.data._io_utils import resolve_data_path, read_csv_auto_encoding, canonical_stock_code

logger = get_logger(__name__)

class UniverseManager:
    """
    板块/股票池管理器
    """
    DEFAULT_UNIVERSE_NAMES = {
        "000300": "沪深300",
        "000905": "中证500",
        "000852": "中证1000",
    }

    def __init__(self, base_path=None, constituent_root: str = "INDEX_COMP"):
        self.base_path = Path(base_path) if base_path is not None else DATA_ROOT
        self.constituent_root = Path(constituent_root)
        self._cache = {}

    def _constituent_dir(self) -> Path:
        return resolve_data_path(self.base_path, str(self.constituent_root))

    def _resolve_constituent_path(self, universe_id) -> Path:
        candidate = Path(str(universe_id))
        if candidate.suffix.lower() == ".csv":
            if candidate.is_absolute():
                return candidate
            direct = self.base_path / candidate
            if direct.exists():
                return direct
            return self._constituent_dir() / candidate
        return self._constituent_dir() / f"{universe_id}_comp.csv"

    def _current_snapshot_path(self, universe_id) -> Path:
        return self._constituent_dir() / f"{universe_id}_current_comp.csv"

    @staticmethod
    def _read_csv_with_fallback(path: Path) -> pd.DataFrame:
        return read_csv_auto_encoding(path)

    @classmethod
    def normalize_constituents(cls, df: pd.DataFrame, universe_id=None) -> pd.DataFrame:
        columns = ["index_code", "index_name", "code", "sec_name", "indate", "outdate"]
        if df is None or df.empty:
            return pd.DataFrame(columns=columns)

        normalized = df.copy()
        raw_cols = {str(c).strip().lower(): c for c in normalized.columns}
        aliases = {
            "index_code": ["indexcode", "index_code", "指数代码"],
            "index_name": ["indexname", "index_name", "指数名称"],
            "code": ["seccode", "sec_code", "code", "symbol", "品种代码", "成分券代码"],
            "sec_name": ["secname", "sec_name", "name", "品种名称", "成分券名称"],
            "indate": ["indate", "in_date", "纳入日期", "日期"],
            "outdate": ["outdate", "out_date", "剔除日期"],
        }
        rename_dict = {}
        for target, names in aliases.items():
            for name in names:
                key = str(name).strip().lower()
                if key in raw_cols:
                    rename_dict[raw_cols[key]] = target
                    break
        normalized = normalized.rename(columns=rename_dict)

        if "code" not in normalized.columns:
            raise ValueError("成分股文件缺少股票代码列，例如 SecCode/成分券代码/code。")
        if "indate" not in normalized.columns:
            raise ValueError("成分股文件缺少入选日期列，例如 InDate/纳入日期/日期。")
        if "outdate" not in normalized.columns:
            normalized["outdate"] = pd.NaT

        normalized["code"] = normalized["code"].map(canonical_stock_code)
        normalized["indate"] = pd.to_datetime(normalized["indate"], errors="coerce")
        normalized["outdate"] = pd.to_datetime(normalized["outdate"], errors="coerce")
        if "index_code" not in normalized.columns:
            normalized["index_code"] = str(universe_id) if universe_id is not None else pd.NA
        if "index_name" not in normalized.columns:
            normalized["index_name"] = cls.DEFAULT_UNIVERSE_NAMES.get(str(universe_id), pd.NA)
        if "sec_name" not in normalized.columns:
            normalized["sec_name"] = pd.NA

        normalized = normalized.dropna(subset=["code", "indate"])
        return normalized[columns].sort_values(["code", "indate", "outdate"]).reset_index(drop=True)

    def get_constituents(self, universe_id):
        cache_key = str(self._resolve_constituent_path(universe_id))
        if cache_key in self._cache:
            return self._cache[cache_key]
        path = self._resolve_constituent_path(universe_id)
        if not path.exists():
            current_path = self._current_snapshot_path(universe_id)
            extra = ""
            if current_path.exists():
                extra = f"。发现当前快照 {current_path}，但它不包含完整历史 InDate/OutDate 区间，不能直接用于历史动态股票池回测。"
            raise FileNotFoundError(f"找不到历史成分股文件：{path}{extra}")
        try:
            df = self.normalize_constituents(self._read_csv_with_fallback(path), universe_id=universe_id)
        except Exception as e:
            logger.error(f"Error loading universe {universe_id}: {e}")
            raise
        self._cache[cache_key] = df
        return df

    def get_members(self, universe_id, target_date) -> list[str]:
        df = self.get_constituents(universe_id)
        if df.empty:
            return []
        target = pd.to_datetime(target_date)
        mask = (df["indate"] <= target) & ((df["outdate"] > target) | (df["outdate"].isna()))
        return sorted(df.loc[mask, "code"].dropna().astype(str).unique().tolist())

    def get_member_union(self, universe_id, start_date=None, end_date=None) -> list[str]:
        df = self.get_constituents(universe_id)
        if df.empty:
            return []
        start = pd.to_datetime(start_date) if start_date is not None else df["indate"].min()
        end = pd.to_datetime(end_date) if end_date is not None else pd.Timestamp.today().normalize()
        mask = (df["indate"] <= end) & ((df["outdate"] > start) | (df["outdate"].isna()))
        return sorted(df.loc[mask, "code"].dropna().astype(str).unique().tolist())

    def build_membership_mask(self, universe_id, dates: Iterable, codes: Iterable) -> pd.DataFrame:
        date_index = pd.to_datetime(pd.Index(dates)).sort_values()
        code_list = [canonical_stock_code(code) for code in codes]
        mask = pd.DataFrame(False, index=date_index, columns=code_list)
        df = self.get_constituents(universe_id)
        if df.empty or len(date_index) == 0 or len(code_list) == 0:
            return mask

        code_set = set(code_list)
        for row in df.itertuples(index=False):
            code = str(row.code)
            if code not in code_set:
                continue
            outdate = pd.Timestamp(row.outdate) if pd.notna(row.outdate) else pd.Timestamp.max
            active_dates = (mask.index >= pd.Timestamp(row.indate)) & (mask.index < outdate)
            if active_dates.any():
                mask.loc[active_dates, code] = True
        return mask

    @staticmethod
    def _fetch_current_constituents_from_akshare(universe_id: str) -> pd.DataFrame:
        import akshare as ak

        df = ak.index_stock_cons_csindex(symbol=str(universe_id))
        if df is None or df.empty:
            df = ak.index_stock_cons(symbol=str(universe_id))
        return df

    def bootstrap_current_constituents(
        self,
        universe_ids=("000300", "000905", "000852"),
        *,
        as_of_date=None,
        overwrite: bool = True,
    ) -> dict[str, Path]:
        """
        通过 AkShare 下载当前成分股快照并保存为 *_current_comp.csv。
        该文件只用于补齐当前样本和审计，不作为历史动态股票池文件。
        """
        output_dir = self._constituent_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        as_of = pd.to_datetime(as_of_date) if as_of_date is not None else pd.Timestamp.today().normalize()
        written = {}

        for universe_id in universe_ids:
            target_path = self._current_snapshot_path(universe_id)
            if target_path.exists() and not overwrite:
                written[str(universe_id)] = target_path
                continue
            raw = self._fetch_current_constituents_from_akshare(str(universe_id))
            current = self.normalize_constituents(raw, universe_id=universe_id)
            current["indate"] = as_of
            current["outdate"] = pd.NaT
            current.to_csv(target_path, index=False, encoding="utf-8-sig")
            meta_path = target_path.with_suffix(".metadata.json")
            metadata = {
                "universe_id": str(universe_id),
                "as_of_date": as_of.strftime("%Y-%m-%d"),
                "source": "akshare.index_stock_cons_csindex",
                "history_complete": False,
                "warning": "current-only snapshot; do not use as historical constituent intervals",
            }
            meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            written[str(universe_id)] = target_path
        return written

class DataProvider:
    """
    数据接入层：负责统一管理本地数据读取、缓存和基础清洗
    """
    def __init__(self, base_data_path: str = None):
        self.base_path = Path(base_data_path) if base_data_path is not None else DATA_ROOT
        self.universe_mgr = UniverseManager(self.base_path)

    def get_stock_data(self, filename: str, name: str = "stock"):
        path = resolve_data_path(self.base_path, filename)
        if not path.exists():
            return None
        return load_and_preprocess(str(path), name)

    def get_batch_data(self, filenames: list):
        data_dict = {}
        for f in filenames:
            name = Path(f).stem
            data_dict[name] = self.get_stock_data(f, name)
        return data_dict

    def get_wide_table(self, filename: str):
        path = resolve_data_path(self.base_path, filename)
        if not path.exists():
            return None
        df = read_csv_auto_encoding(path)
        metadata_keywords = ["指标名称", "频率", "单位", "指标id", "来源", "指标ID"]
        rows_to_drop = [i for i in range(min(15, len(df))) if any(k.lower() in str(df.iloc[i, 0]).lower() for k in metadata_keywords)]
        if rows_to_drop:
            df.drop(rows_to_drop, inplace=True); df.reset_index(drop=True, inplace=True)
        date_col = next((c for c in df.columns if any(k in c.lower() for k in ["date", "日期", "time", "时间"])), None)
        if date_col:
            df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
            df.dropna(subset=[date_col], inplace=True)
            df.set_index(date_col, inplace=True)
            df.index.name = "date"
        else:
            df.index = pd.to_datetime(df.iloc[:, 0], errors="coerce")
            df = df[df.index.notnull()].iloc[:, 1:]
            df.index.name = "date"
        return df.apply(pd.to_numeric, errors="coerce").sort_index()

    def get_fundamental_data(self, filename: str = "FUNDAMENTAL/ROE.csv", value_col: str = "ROE"):
        path = self.base_path / filename
        if not path.exists(): return None
        df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_excel(path)
        col_map = {"secucode": "code", "证券代码": "code", "代码": "code", "enddate": "date", "截止日期": "date", "报告期": "date", value_col.lower(): "value"}
        df.columns = [str(c).lower().strip() for c in df.columns]
        df.rename(columns=col_map, inplace=True)
        df = df.dropna(subset=["code", "date"])
        df["date"] = pd.to_datetime(df["date"])
        df["code"] = df["code"].map(canonical_stock_code)
        if "value" in df.columns: df["value"] = pd.to_numeric(df["value"], errors="coerce")
        return df[["code", "date", "value"]].sort_values(["code", "date"])

    def load_sector_matrix(self, file_path: str):
        """
        加载板块/行业指数矩阵 (Wind Excel 格式)
        """
        path = resolve_data_path(self.base_path, file_path)
        if not path.exists(): return pd.DataFrame()
        try:
            preview = pd.read_excel(path, nrows=10)
            header_row_idx = 0
            for i in range(len(preview)):
                if any(k in str(preview.iloc[i].values) for k in ["指标名称", "名称"]):
                    header_row_idx = i; break
            raw_cols = preview.iloc[header_row_idx].tolist()
            clean_cols = ["date"] + [str(c).split(":")[-1].split("：")[-1] for c in raw_cols[1:]]
            df = pd.read_excel(path, skiprows=header_row_idx + 6, names=clean_cols)
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            return df.dropna(subset=["date"]).set_index("date").sort_index().dropna(axis=1, how="all").apply(pd.to_numeric, errors="coerce")
        except Exception as e:
            logger.error(f"Error loading sector matrix: {e}")
            return pd.DataFrame()

    def load_wide_matrix(self, file_path: str, start_date=None, end_date=None):
        path = resolve_data_path(self.base_path, file_path)
        if not path.exists(): return pd.DataFrame()
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        if start_date: df = df[df.index >= pd.to_datetime(start_date)]
        if end_date: df = df[df.index <= pd.to_datetime(end_date)]
        return df

    @staticmethod
    def normalize_stock_code(code) -> str:
        return canonical_stock_code(code)

    def load_stock_ohlcv_long(self, file_path: str, start_date=None, end_date=None, codes=None):
        """
        加载股票长表行情，要求至少包含 date/code/open/high/low/close/volume。
        支持 CSV/Excel 长表。
        """
        path = resolve_data_path(self.base_path, file_path)
        if not path.exists():
            raise FileNotFoundError(f"找不到行情数据文件：{path}")

        if path.suffix.lower() in [".xlsx", ".xls"]:
            df = pd.read_excel(path)
        else:
            df = read_csv_auto_encoding(path)

        df.columns = [str(c).strip().lower() for c in df.columns]
        rename_map = {
            "trade_date": "date",
            "trade_dt": "date",
            "datetime": "date",
            "ticker": "code",
            "symbol": "code",
            "secucode": "code",
            "vol": "volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        required = ["date", "code", "open", "high", "low", "close", "volume"]
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"行情数据缺少必要字段：{missing}")

        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["code"] = df["code"].map(self.normalize_stock_code)
        df = df.dropna(subset=["date", "code"])
        if start_date:
            df = df[df["date"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["date"] <= pd.to_datetime(end_date)]
        if codes is not None:
            normalized_codes = {self.normalize_stock_code(code) for code in codes}
            df = df[df["code"].isin(normalized_codes)]

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        return df.sort_values(["code", "date"]).reset_index(drop=True)

    @staticmethod
    def _normalize_fq(fq: str) -> str:
        """统一 fq 取值到 parquet 子目录名。"""
        key = str(fq).strip().lower()
        mapping = {
            "bfq": "raw",
            "raw": "raw",
            "nfq": "raw",
            "hfq": "hfq",
            "qfq": "qfq",
            "不复权": "raw",
            "后复权": "hfq",
            "前复权": "qfq",
        }
        if key not in mapping:
            raise ValueError("fq 仅支持 qfq/hfq/bfq（或 raw）。")
        return mapping[key]

    def load_stock_ohlcv_from_daily_parquet(
        self,
        fq: str = "qfq",
        start_date=None,
        end_date=None,
        codes=None,
        daily_root: str = "STOCK/daily",
        universe: str = None,
    ):
        """
        从按 code 分片的日线 parquet 加载长表行情。

        - fq: qfq/hfq/bfq(raw)
        - start_date/end_date: 日期过滤，end_date 为空时自动取库内最新日期
        - codes: None 则加载目录全部代码文件；传入 universe 时加载区间成分股并集
        - daily_root: 相对 base_path 或绝对路径
        - universe: 指数代码，例如 000905，仅在 codes=None 时用于减少 parquet 读取
        """
        fq_dir = self._normalize_fq(fq)
        root = resolve_data_path(self.base_path, str(daily_root))
        store_dir = root / fq_dir
        if not store_dir.exists():
            raise FileNotFoundError(f"找不到分片 parquet 目录：{store_dir}")

        if codes is None:
            if universe is not None:
                code_list = self.universe_mgr.get_member_union(universe, start_date=start_date, end_date=end_date)
            else:
                code_list = sorted(p.stem for p in store_dir.glob("*.parquet"))
        else:
            code_list = [self.normalize_stock_code(c) for c in codes]

        frames = []
        for code in code_list:
            file_path = store_dir / f"{code}.parquet"
            if not file_path.exists():
                continue
            df_code = pd.read_parquet(file_path, engine="fastparquet")
            if df_code.empty:
                continue
            df_code = df_code.copy()
            df_code["date"] = pd.to_datetime(df_code["date"], errors="coerce")
            df_code["code"] = self.normalize_stock_code(code)
            frames.append(df_code)

        if not frames:
            return pd.DataFrame(columns=["date", "code", "open", "high", "low", "close", "volume"])

        df = pd.concat(frames, ignore_index=True)
        df = df.dropna(subset=["date", "code"])

        if start_date is not None:
            df = df[df["date"] >= pd.to_datetime(start_date)]

        if end_date is not None:
            end_dt = pd.to_datetime(end_date)
        else:
            end_dt = df["date"].max()
        df = df[df["date"] <= end_dt]

        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            else:
                df[col] = np.nan

        # 与既有长表读取接口对齐，保留常用字段并附带 amount/adjust_factor（若存在）
        ordered_cols = ["date", "code", "open", "high", "low", "close", "volume"]
        for extra in ["amount", "adjust_factor"]:
            if extra in df.columns:
                ordered_cols.append(extra)
        df = df[ordered_cols]
        return df.sort_values(["code", "date"]).reset_index(drop=True)

    @staticmethod
    def build_price_matrices(data: pd.DataFrame):
        """
        将股票长表行情转换为 open/high/low/close 宽表，供事件回测器使用。
        """
        required = ["date", "code", "open", "high", "low", "close"]
        missing = [col for col in required if col not in data.columns]
        if missing:
            raise ValueError(f"价格矩阵转换缺少必要字段：{missing}")

        df = data.copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["code"] = df["code"].map(DataProvider.normalize_stock_code)
        return {
            "open": df.pivot(index="date", columns="code", values="open").sort_index(),
            "high": df.pivot(index="date", columns="code", values="high").sort_index(),
            "low": df.pivot(index="date", columns="code", values="low").sort_index(),
            "close": df.pivot(index="date", columns="code", values="close").sort_index(),
        }

def load_and_preprocess(path, asset_name):
    warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
    if path.endswith(".csv"):
        df = read_csv_auto_encoding(Path(path))
    elif path.endswith(".xlsx") or path.endswith(".xls"):
        try: df = pd.read_excel(path)
        except:
            with zipfile.ZipFile(path, "r") as zin:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as zout:
                    for item in zin.infolist():
                        if item.filename != "xl/styles.xml": zout.writestr(item, zin.read(item.filename))
                        else: zout.writestr(item, '"<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"></styleSheet>"')
                buffer.seek(0); df = pd.read_excel(buffer, engine="openpyxl")
    else: return pd.DataFrame()
    if df.shape[0] > 0:
        header_row_idx = -1
        for i in range(min(5, len(df))):
            if any(any(kw in str(val) for kw in ["日期", "date", "指标名称", "时间", "time"]) for val in df.iloc[i].values):
                header_row_idx = i; break
        if header_row_idx != -1:
            new_cols = [str(c).strip() if pd.notna(c) else f"unnamed_{i}" for i, c in enumerate(df.iloc[header_row_idx].values)]
            df = df.iloc[header_row_idx+1:].copy(); df.columns = new_cols
    df.columns = [str(c).strip().lower() for c in df.columns]
    date_col = next((c for c in df.columns if c in ["date", "日期", "指标名称", "time", "时间", "trade_date", "trade_dt", "s_info_date", "s_info_tradedate"]), df.columns[0])
    df.rename(columns={date_col: "date"}, inplace=True)
    df["date"] = pd.to_datetime(df["date"], unit="D", origin="1899-12-30").dt.normalize() if pd.api.types.is_numeric_dtype(df["date"]) else pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date").set_index("date")
    ohlc_map = {"open": ["open", "开盘"], "high": ["high", "最高"], "low": ["low", "最低"], "close": ["close", "收盘", "最新价", asset_name.lower()], "volume": ["volume", "成交量"], "amount": ["amount", "成交额"]}
    res = pd.DataFrame(index=df.index)
    for std, kws in ohlc_map.items():
        col = next((c for c in df.columns if any(kw in c for kw in kws)), None)
        res[std] = pd.to_numeric(df[col], errors="coerce") if col else np.nan
    if res["close"].isna().all():
        for c in df.columns:
            tmp = pd.to_numeric(df[c], errors="coerce")
            if not tmp.isna().all(): res["close"] = tmp; break
    return res[~res.index.duplicated(keep="first")].sort_index().ffill()

def normalize_series(df_or_ser):
    if isinstance(df_or_ser, pd.Series):
        v = df_or_ser.dropna()
        return df_or_ser / v.iloc[0] if not v.empty and v.iloc[0] != 0 else df_or_ser
    elif isinstance(df_or_ser, pd.DataFrame):
        res = df_or_ser.copy()
        for c in res.columns:
            v = res[c].dropna()
            res[c] = res[c] / v.iloc[0] if not v.empty and v.iloc[0] != 0 else np.nan
        return res
    return df_or_ser
