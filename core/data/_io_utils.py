"""
Data I/O 共享工具函数 — 供 DataManager 内部使用，消除重复代码。

提取的共享模式：
  - resolve_data_path:      路径解析（绝对 vs 相对 base_path）
  - read_csv_auto_encoding:  CSV 编码自动检测（utf-8-sig → utf-8 → gbk）
  - canonical_stock_code:    股票代码标准化（合并两个旧版 normalize_stock_code）
"""
import pandas as pd
from pathlib import Path
from typing import Optional

from core.config import DATA_ROOT


LEGACY_DATA_PATH_PREFIXES = {
    "STOCK/daily": DATA_ROOT / "market" / "stock" / "daily",
    "STOCK/qlib_cn_full": DATA_ROOT / "qlib" / "cn_full",
    "STOCK/a_stock_codes.txt": DATA_ROOT / "reference" / "stock_universe" / "a_stock_codes.txt",
    "STOCK/codes_from_20140102_20251231.txt": DATA_ROOT / "reference" / "stock_universe" / "codes_from_20140102_20251231.txt",
    "STOCK/stock_name_map.csv": DATA_ROOT / "reference" / "stock_universe" / "stock_name_map.csv",
    "STOCK/all_stock_data_ts_20140102_20251231.csv": DATA_ROOT / "market" / "stock" / "all_stock_data_ts_20140102_20251231.csv",
    "INDEX_COMP": DATA_ROOT / "reference" / "index_constituents",
    "MARKET_VALUE": DATA_ROOT / "fundamental" / "market_value",
    "FACTORS/Alpha158": DATA_ROOT / "factors" / "alpha158",
    "FACTORS": DATA_ROOT / "factors" / "technical",
    "Barra": DATA_ROOT / "factors" / "barra",
    "SPARSE_SIGNAL": DATA_ROOT / "signals" / "gx_pit_mom",
    "TIMING": DATA_ROOT / "timing",
    "BOND": DATA_ROOT / "market" / "bond",
    "COMM": DATA_ROOT / "market" / "commodity",
    "US": DATA_ROOT / "market" / "us",
    "ANALYST": DATA_ROOT / "fundamental" / "analyst",
    "FUNDAMENTAL": DATA_ROOT / "fundamental" / "statements",
    "0AMV": DATA_ROOT / "market" / "derived" / "amv",
    "INDEX/STOCK": DATA_ROOT / "market" / "index" / "broad",
    "INDEX/ZX/ZX_YJHY.xlsx": DATA_ROOT / "market" / "index" / "zxyj" / "ZX_YJHY.xlsx",
    "INDEX/ZX/ZX_YJHY_ALL.csv": DATA_ROOT / "market" / "index" / "zxyj" / "ZX_YJHY_ALL.csv",
    "INDEX/ZX/yjhy_prices.csv": DATA_ROOT / "market" / "index" / "zxyj" / "yjhy_prices.csv",
    "INDEX/ZX/中信行业指数_石油石化.csv": DATA_ROOT / "market" / "index" / "zxyj" / "中信行业指数_石油石化.csv",
    "INDEX/ZX/ZX_EJHY.xlsx": DATA_ROOT / "market" / "index" / "zxej" / "ZX_EJHY.xlsx",
    "INDEX/ZX/ejhy_prices.csv": DATA_ROOT / "market" / "index" / "zxej" / "ejhy_prices.csv",
    "INDEX/ZX/中信行业指数_石油开采Ⅱ.csv": DATA_ROOT / "market" / "index" / "zxej" / "中信行业指数_石油开采Ⅱ.csv",
    "INDEX/GYSY": DATA_ROOT / "market" / "index" / "zxyj",
    "INDEX/AG": DATA_ROOT / "market" / "index" / "silver",
    "INDEX/AL": DATA_ROOT / "market" / "index" / "aluminum",
    "INDEX/CU": DATA_ROOT / "market" / "index" / "copper",
    "INDEX/OIL": DATA_ROOT / "market" / "index" / "oil",
    "INDEX/STEEL": DATA_ROOT / "market" / "index" / "steel",
    "INDEX/HLDB/512890.SH.xlsx": DATA_ROOT / "market" / "etf" / "hldb" / "512890.SH.xlsx",
    "INDEX/HLDB": DATA_ROOT / "market" / "index" / "hldb",
    "INDEX/GOLD/517400.SH.xlsx": DATA_ROOT / "market" / "etf" / "gold" / "517400.SH.xlsx",
    "INDEX/GOLD": DATA_ROOT / "market" / "index" / "gold",
    "INDEX": DATA_ROOT / "market" / "index",
    "curated/market/stock/daily": DATA_ROOT / "market" / "stock" / "daily",
    "curated/market/stock/ohlcv_long": DATA_ROOT / "market" / "stock",
    "curated/reference/security_master": DATA_ROOT / "reference" / "stock_universe",
    "reference/stocks": DATA_ROOT / "reference" / "stock_universe",
    "curated/reference/index_constituents": DATA_ROOT / "reference" / "index_constituents",
    "curated/fundamental/market_value/daily": DATA_ROOT / "fundamental" / "market_value",
    "features/technical": DATA_ROOT / "factors" / "technical",
    "features/alpha158": DATA_ROOT / "factors" / "alpha158",
    "features/barra": DATA_ROOT / "factors" / "barra",
    "marts/qlib/cn_full": DATA_ROOT / "qlib" / "cn_full",
    "signals/timing": DATA_ROOT / "timing",
    "signals/sparse": DATA_ROOT / "signals" / "gx_pit_mom",
    "signals/chart_patterns": DATA_ROOT / "patterns" / "chart",
    "raw/market/index/STOCK": DATA_ROOT / "market" / "index" / "broad",
    "raw/market/index/ZX/ZX_YJHY.xlsx": DATA_ROOT / "market" / "index" / "zxyj" / "ZX_YJHY.xlsx",
    "raw/market/index/ZX/ZX_YJHY_ALL.csv": DATA_ROOT / "market" / "index" / "zxyj" / "ZX_YJHY_ALL.csv",
    "raw/market/index/ZX/yjhy_prices.csv": DATA_ROOT / "market" / "index" / "zxyj" / "yjhy_prices.csv",
    "raw/market/index/ZX/中信行业指数_石油石化.csv": DATA_ROOT / "market" / "index" / "zxyj" / "中信行业指数_石油石化.csv",
    "raw/market/index/ZX/ZX_EJHY.xlsx": DATA_ROOT / "market" / "index" / "zxej" / "ZX_EJHY.xlsx",
    "raw/market/index/ZX/ejhy_prices.csv": DATA_ROOT / "market" / "index" / "zxej" / "ejhy_prices.csv",
    "raw/market/index/ZX/中信行业指数_石油开采Ⅱ.csv": DATA_ROOT / "market" / "index" / "zxej" / "中信行业指数_石油开采Ⅱ.csv",
    "raw/market/index/GYSY": DATA_ROOT / "market" / "index" / "zxyj",
    "raw/market/index/AG": DATA_ROOT / "market" / "index" / "silver",
    "raw/market/index/AL": DATA_ROOT / "market" / "index" / "aluminum",
    "raw/market/index/CU": DATA_ROOT / "market" / "index" / "copper",
    "raw/market/index/OIL": DATA_ROOT / "market" / "index" / "oil",
    "raw/market/index/STEEL": DATA_ROOT / "market" / "index" / "steel",
    "raw/market/index/HLDB/512890.SH.xlsx": DATA_ROOT / "market" / "etf" / "hldb" / "512890.SH.xlsx",
    "raw/market/index/HLDB": DATA_ROOT / "market" / "index" / "hldb",
    "raw/market/index/GOLD/517400.SH.xlsx": DATA_ROOT / "market" / "etf" / "gold" / "517400.SH.xlsx",
    "raw/market/index/GOLD": DATA_ROOT / "market" / "index" / "gold",
    "raw/market/index": DATA_ROOT / "market" / "index",
    "raw/market/bond": DATA_ROOT / "market" / "bond",
    "raw/market/commodity": DATA_ROOT / "market" / "commodity",
    "raw/market/us": DATA_ROOT / "market" / "us",
    "raw/fundamental": DATA_ROOT / "fundamental" / "statements",
    "raw/analyst": DATA_ROOT / "fundamental" / "analyst",
    "raw/vendor/amv": DATA_ROOT / "market" / "derived" / "amv",
    "market/index/stock": DATA_ROOT / "market" / "index" / "broad",
    "market/index/commodity_theme/AG": DATA_ROOT / "market" / "index" / "silver",
    "market/index/commodity_theme/AL": DATA_ROOT / "market" / "index" / "aluminum",
    "market/index/commodity_theme/CU": DATA_ROOT / "market" / "index" / "copper",
    "market/index/commodity_theme/OIL": DATA_ROOT / "market" / "index" / "oil",
    "market/index/commodity_theme/STEEL": DATA_ROOT / "market" / "index" / "steel",
    "market/index/commodity_theme/GOLD/517400.SH.xlsx": DATA_ROOT / "market" / "etf" / "gold" / "517400.SH.xlsx",
    "market/index/commodity_theme/GOLD": DATA_ROOT / "market" / "index" / "gold",
    "market/index/industry/GYSY": DATA_ROOT / "market" / "index" / "zxyj",
    "market/index/industry/HLDB/512890.SH.xlsx": DATA_ROOT / "market" / "etf" / "hldb" / "512890.SH.xlsx",
    "market/index/industry/HLDB": DATA_ROOT / "market" / "index" / "hldb",
    "market/index/industry/ZX_YJHY.xlsx": DATA_ROOT / "market" / "index" / "zxyj" / "ZX_YJHY.xlsx",
    "market/index/industry/ZX_YJHY_ALL.csv": DATA_ROOT / "market" / "index" / "zxyj" / "ZX_YJHY_ALL.csv",
    "market/index/industry/yjhy_prices.csv": DATA_ROOT / "market" / "index" / "zxyj" / "yjhy_prices.csv",
    "market/index/industry/中信行业指数_石油石化.csv": DATA_ROOT / "market" / "index" / "zxyj" / "中信行业指数_石油石化.csv",
    "market/index/industry/ZX_EJHY.xlsx": DATA_ROOT / "market" / "index" / "zxej" / "ZX_EJHY.xlsx",
    "market/index/industry/ejhy_prices.csv": DATA_ROOT / "market" / "index" / "zxej" / "ejhy_prices.csv",
    "market/index/industry/中信行业指数_石油开采Ⅱ.csv": DATA_ROOT / "market" / "index" / "zxej" / "中信行业指数_石油开采Ⅱ.csv",
    "market/index/equity_broad": DATA_ROOT / "market" / "index" / "broad",
    "market/index/equity_theme/gold_stock": DATA_ROOT / "market" / "index" / "gold",
    "market/index/equity_strategy/dividend_low_volatility": DATA_ROOT / "market" / "index" / "hldb",
    "market/index/equity_strategy/growth": DATA_ROOT / "market" / "index" / "growth",
    "market/index/equity_industry/citic_level1": DATA_ROOT / "market" / "index" / "zxyj",
    "market/index/equity_industry/citic_level2": DATA_ROOT / "market" / "index" / "zxej",
    "market/index/equity_industry/citic_resource/precious_metals": DATA_ROOT / "market" / "index" / "gold",
    "market/index/equity_industry/citic_resource/steel": DATA_ROOT / "market" / "index" / "steel",
    "market/index/equity_industry/citic_resource/nonferrous_metals/CI005214.WI.xlsx": DATA_ROOT / "market" / "index" / "copper" / "CI005214.WI.xlsx",
    "market/index/equity_industry/citic_resource/nonferrous_metals/CI005218.WI.xlsx": DATA_ROOT / "market" / "index" / "aluminum" / "CI005218.WI.xlsx",
    "market/index/equity_industry/wind_resource/precious_metals": DATA_ROOT / "market" / "index" / "silver",
    "market/index/equity_industry/wind_resource/nonferrous_metals": DATA_ROOT / "market" / "index" / "aluminum",
    "market/index/equity_industry/wind_resource/petroleum": DATA_ROOT / "market" / "index" / "oil",
    "market/index/equity_industry/wind_resource/steel": DATA_ROOT / "market" / "index" / "steel",
    "market/index/equity_industry/changjiang_resource/precious_metals/003048.CJ.xlsx": DATA_ROOT / "market" / "index" / "silver" / "003048.CJ.xlsx",
    "market/index/equity_industry/changjiang_resource/precious_metals/003049.CJ.xlsx": DATA_ROOT / "market" / "index" / "gold" / "003049.CJ.xlsx",
    "market/index/derived/hedged_nav": DATA_ROOT / "market" / "index" / "gold",
    "market/etf/thematic/gold_stock": DATA_ROOT / "market" / "etf" / "gold",
    "market/etf/strategy/dividend_low_volatility": DATA_ROOT / "market" / "etf" / "hldb",
    "market/benchmark/benchmark_60s_40b.csv": DATA_ROOT / "market" / "benchmark" / "60bond_40csi300.csv",
}


def _resolve_legacy_data_path(file_path: str) -> Optional[Path]:
    normalized = str(file_path).replace("\\", "/").lstrip("/")
    if normalized in {"D:/DATA", "D:/DATA/"}:
        return DATA_ROOT
    if normalized.startswith("D:/DATA/"):
        normalized = normalized[len("D:/DATA/"):]

    for legacy_prefix, target_prefix in sorted(
        LEGACY_DATA_PATH_PREFIXES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if normalized == legacy_prefix:
            return target_prefix
        if normalized.startswith(f"{legacy_prefix}/"):
            suffix = normalized[len(legacy_prefix) + 1:]
            return target_prefix / suffix
    return None


def resolve_data_path(base_path: Path, file_path: str) -> Path:
    """解析数据文件路径，兼容迁移前的 D:/DATA 相对路径约定。"""
    p = Path(file_path)
    if p.is_absolute():
        return p

    candidate = base_path / p
    if candidate.exists():
        return candidate

    legacy_path = _resolve_legacy_data_path(file_path)
    return legacy_path if legacy_path is not None else candidate


def read_csv_auto_encoding(path: Path, **kwargs):
    """
    按 utf-8-sig → utf-8 → gbk 顺序尝试读取 CSV。
    所有编码都失败时用 pandas 默认编码兜底。
    """
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path, **kwargs)


def canonical_stock_code(code) -> str:
    """
    标准化股票代码为 6 位数字字符串。

    处理场景：
      - 带交易所前缀：sh600000 / SZ000001 / bj830799 → 去前缀
      - 带 .0 后缀：000001.0 → 去后缀
      - 带交易所后缀：000001.XSHE / 600000.SH → 取前半段
      - 短代码补零：1 → 000001
      - 非纯数字：保持原样返回
    """
    text = str(code).strip()
    # 去交易所前缀 sh/sz/bj（长度≥8，前缀2字母 + 后6位数字）
    if len(text) >= 8 and text[:2].lower() in {"sh", "sz", "bj"} and text[2:].isdigit():
        text = text[2:]
    # 去 .0 后缀
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    # 去 .XSHE / .SH 等后缀
    if "." in text and text.split(".")[0].isdigit():
        text = text.split(".")[0]
    # 纯数字 → 补零到6位
    if text.isdigit() and len(text) <= 6:
        return text.zfill(6)
    return text
