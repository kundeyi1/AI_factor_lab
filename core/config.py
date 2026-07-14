"""Project-wide path configuration.

Set ``QUANT_DATA_ROOT`` to override the default data directory. Without an
override, the project keeps the old Windows default when available, then uses
``~/DATA`` on macOS/Linux, then falls back to the project-local ``data`` folder.
"""

from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT_ENV_VAR = "QUANT_DATA_ROOT"


def _default_data_root() -> Path:
    configured = os.getenv(DATA_ROOT_ENV_VAR)
    if configured:
        return Path(configured).expanduser()

    candidates = []
    if os.name == "nt":
        candidates.append(Path("D:/DATA"))
    candidates.extend([
        Path.home() / "DATA",
        PROJECT_ROOT / "data",
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return PROJECT_ROOT / "data"


DATA_ROOT = _default_data_root()


def data_path(*parts: str | os.PathLike[str]) -> Path:
    """Return a path under the configured data root."""
    return DATA_ROOT.joinpath(*map(Path, parts))


STOCK_DATA_ROOT = data_path("market", "stock")
DAILY_QFQ_ROOT = data_path("market", "stock", "daily", "qfq")
STOCK_CODES_CACHE = data_path("reference", "stock_universe", "a_stock_codes.txt")
STOCK_NAME_MAP_PATH = data_path("reference", "stock_universe", "stock_name_map.csv")
ALL_STOCK_DATA_FILE = data_path("market", "stock", "all_stock_data_ts_20140102_20251231.csv")
TIMING_DIR = data_path("timing")
SPARSE_SIGNAL_DIR = data_path("signals", "gx_pit_mom")
FACTORS_DIR = data_path("factors", "technical")
CSI_985_INDEX_FILE = data_path("market", "index", "broad", "000985.CSI.xlsx")
QLIB_CN_FULL_DIR = data_path("qlib", "cn_full")
INDEX_CONSTITUENTS_DIR = data_path("reference", "index_constituents")
MARKET_VALUE_DIR = data_path("fundamental", "market_value")
ALPHA158_DIR = data_path("factors", "alpha158")
BARRA_FACTORS_DIR = data_path("factors", "barra")
