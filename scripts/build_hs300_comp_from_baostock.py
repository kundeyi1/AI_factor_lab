from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import baostock as bs
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.config import INDEX_CONSTITUENTS_DIR


INDEX_ID = "000300"
INDEX_NAME = "沪深300"


def build_query_dates(start_year: int, end_date: pd.Timestamp, extra_dates: list[str]) -> list[str]:
    dates: list[str] = []
    for year in range(start_year, end_date.year + 1):
        for month_day in ("01-05", "07-05"):
            candidate = pd.Timestamp(f"{year}-{month_day}")
            if candidate <= end_date:
                dates.append(candidate.strftime("%Y-%m-%d"))
    for value in extra_dates:
        candidate = pd.Timestamp(value)
        if candidate <= end_date:
            dates.append(candidate.strftime("%Y-%m-%d"))
    return sorted(set(dates))


def fetch_snapshots(query_dates: list[str]) -> list[dict]:
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"Baostock login failed: {login.error_msg}")

    snapshots: list[dict] = []
    try:
        for index, query_date in enumerate(query_dates, 1):
            result = bs.query_hs300_stocks(query_date)
            if result.error_code != "0":
                raise RuntimeError(f"query_hs300_stocks({query_date}) failed: {result.error_msg}")

            rows = []
            while result.next():
                update_date, code, name = result.get_row_data()
                if not code:
                    continue
                rows.append(
                    {
                        "code": code.split(".")[-1].zfill(6),
                        "name": name,
                        "update_date": update_date,
                    }
                )
            if not rows:
                print(f"skip {query_date}: empty")
                continue

            frame = pd.DataFrame(rows)
            effective_date = pd.to_datetime(frame["update_date"], errors="coerce").dropna().max()
            snapshots.append({"query_date": query_date, "effective_date": effective_date, "members": frame})
            print(f"{index:02d}/{len(query_dates)} {query_date}: {len(frame)} rows effective={effective_date.date()}")
    finally:
        bs.logout()

    by_effective: dict[pd.Timestamp, dict] = {}
    for snapshot in snapshots:
        by_effective[pd.Timestamp(snapshot["effective_date"])] = snapshot
    return [by_effective[date] for date in sorted(by_effective)]


def snapshots_to_intervals(snapshots: list[dict]) -> pd.DataFrame:
    intervals: list[dict[str, str]] = []
    active: dict[str, dict[str, str]] = {}

    for snapshot in snapshots:
        effective_date = pd.Timestamp(snapshot["effective_date"]).strftime("%Y-%m-%d")
        current = {
            str(row.code): str(row.name)
            for row in snapshot["members"].itertuples(index=False)
        }
        current_codes = set(current)
        active_codes = set(active)

        for code in sorted(active_codes - current_codes):
            row = active.pop(code)
            row["OutDate"] = effective_date
            intervals.append(row)
        for code in sorted(current_codes - active_codes):
            active[code] = {
                "IndexCode": INDEX_ID,
                "IndexName": INDEX_NAME,
                "SecCode": code,
                "SecName": current[code],
                "InDate": effective_date,
                "OutDate": "",
            }
        for code in sorted(current_codes & active_codes):
            active[code]["SecName"] = current[code]

    intervals.extend(active.values())
    output = pd.DataFrame(intervals)
    output["InDate_dt"] = pd.to_datetime(output["InDate"])
    output["OutDate_dt"] = pd.to_datetime(output["OutDate"].replace("", pd.NA), errors="coerce")
    return output.sort_values(["SecCode", "InDate_dt", "OutDate_dt"]).drop(columns=["InDate_dt", "OutDate_dt"])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the shared 000300_comp.csv constituent history from Baostock snapshots."
    )
    parser.add_argument("--output-root", default=str(INDEX_CONSTITUENTS_DIR))
    parser.add_argument("--start-year", type=int, default=2006)
    parser.add_argument("--end-date", default=pd.Timestamp.today().normalize().strftime("%Y-%m-%d"))
    parser.add_argument("--extra-date", action="append", default=["2025-06-20", "2026-06-01"])
    args = parser.parse_args()

    end_date = pd.Timestamp(args.end_date)
    query_dates = build_query_dates(args.start_year, end_date, args.extra_date)
    snapshots = fetch_snapshots(query_dates)
    if not snapshots:
        raise RuntimeError("No HS300 snapshots fetched.")

    output_dir = Path(args.output_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{INDEX_ID}_comp.csv"
    metadata_path = output_dir / f"{INDEX_ID}_comp.metadata.json"

    intervals = snapshots_to_intervals(snapshots)
    intervals.to_csv(output_path, index=False, encoding="utf-8-sig")

    metadata = {
        "universe_id": INDEX_ID,
        "index_name": INDEX_NAME,
        "source": "baostock.query_hs300_stocks",
        "rows": int(len(intervals)),
        "snapshot_count": int(len(snapshots)),
        "first_effective_date": pd.Timestamp(snapshots[0]["effective_date"]).strftime("%Y-%m-%d"),
        "last_effective_date": pd.Timestamp(snapshots[-1]["effective_date"]).strftime("%Y-%m-%d"),
        "history_complete": False,
        "method": (
            "Reconstructed intervals from Jan/Jul Baostock snapshots plus configured extra dates; "
            "regular semiannual adjustments are covered, off-cycle changes between sampled snapshots may be approximate."
        ),
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"written {output_path} rows={len(intervals)}")


if __name__ == "__main__":
    main()
