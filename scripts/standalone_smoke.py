from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def build_synthetic_data(data_root: Path) -> list[str]:
    price_root = data_root / "market" / "stock" / "daily" / "qfq"
    constituent_root = data_root / "reference" / "index_constituents"
    price_root.mkdir(parents=True, exist_ok=True)
    constituent_root.mkdir(parents=True, exist_ok=True)

    dates = pd.bdate_range("2024-01-02", "2025-12-31")
    codes = [f"{index:06d}" for index in range(1, 13)]
    rng = np.random.default_rng(20260714)

    constituent_rows = []
    for offset, code in enumerate(codes):
        returns = rng.normal(0.0002 + offset * 0.00003, 0.008, len(dates))
        close = (10 + offset) * np.cumprod(1 + returns)
        frame = pd.DataFrame(
            {
                "date": dates,
                "open": close * (1 + rng.normal(0, 0.001, len(dates))),
                "high": close * 1.01,
                "low": close * 0.99,
                "close": close,
                "volume": rng.integers(100_000, 1_000_000, len(dates)),
            }
        )
        frame["amount"] = frame["close"] * frame["volume"]
        frame.to_parquet(price_root / f"{code}.parquet", index=False)
        constituent_rows.append(
            {
                "IndexCode": "000300",
                "IndexName": "synthetic",
                "SecCode": code,
                "SecName": f"synthetic-{code}",
                "InDate": "2020-01-01",
                "OutDate": "",
            }
        )

    pd.DataFrame(constituent_rows).to_csv(
        constituent_root / "000300_comp.csv",
        index=False,
        encoding="utf-8-sig",
    )
    return codes


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="ai-factor-lab-smoke-") as temp_dir:
        data_root = Path(temp_dir)
        codes = build_synthetic_data(data_root)
        os.environ["QUANT_DATA_ROOT"] = str(data_root)

        from core.data.DataManager import DataProvider, UniverseManager
        from server.backtest.backtester import Backtester
        from server.main import healthcheck

        module_paths = {
            "data_manager": str(Path(sys.modules["core.data.DataManager"].__file__).resolve()),
            "backtester": str(Path(sys.modules["server.backtest.backtester"].__file__).resolve()),
        }
        if any(not path.startswith(str(REPO_ROOT)) for path in module_paths.values()):
            raise AssertionError(f"Imported module outside standalone repository: {module_paths}")

        members = UniverseManager().get_members("000300", "2025-01-02")
        if members != codes:
            raise AssertionError(f"Unexpected synthetic universe: {members}")

        local = DataProvider().load_stock_ohlcv_from_daily_parquet(
            fq="qfq",
            start_date="2024-01-02",
            end_date="2025-12-31",
            codes=codes,
        )
        if local.empty or local["code"].nunique() != len(codes):
            raise AssertionError("Standalone parquet loading failed")

        result = Backtester().run(
            factor_expression="rank(close)",
            start_date="2025-01-02",
            end_date="2025-12-31",
            pool="hs300",
            freq="D",
            layers=5,
        )
        if not result["dates"] or len(result["series"]) != 6:
            raise AssertionError("Standalone backtest returned an incomplete result")
        if healthcheck() != {"status": "ok"}:
            raise AssertionError("Health check failed")

        print(
            json.dumps(
                {
                    "status": "ok",
                    "external_quant_checkout_required": False,
                    "synthetic_codes": len(codes),
                    "backtest_dates": len(result["dates"]),
                    "series": len(result["series"]),
                    "module_paths": module_paths,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
