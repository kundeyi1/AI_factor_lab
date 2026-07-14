from __future__ import annotations

import argparse
import hashlib
import io
import json
import tarfile
from datetime import datetime, timezone
from pathlib import Path


CONSTITUENT_FILES = (
    "000300_comp.csv",
    "000905_comp.csv",
    "000852_comp.csv",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_data(data_root: Path, output: Path, cache_root: Path | None = None) -> dict:
    price_root = data_root / "market" / "stock" / "daily" / "qfq"
    constituent_root = data_root / "reference" / "index_constituents"
    price_files = sorted(price_root.glob("*.parquet"))
    if not price_files:
        raise FileNotFoundError(f"No qfq parquet files found under {price_root}")

    constituent_paths = [constituent_root / name for name in CONSTITUENT_FILES]
    missing = [str(path) for path in constituent_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing historical constituent files: {missing}")
    cache_files = sorted(cache_root.glob("*.parquet")) if cache_root and cache_root.is_dir() else []

    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "format": "ai-factor-lab-data-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "qfq_files": len(price_files),
        "fallback_cache_files": len(cache_files),
        "constituent_files": list(CONSTITUENT_FILES),
    }

    with tarfile.open(output, "w") as archive:
        for path in price_files:
            archive.add(path, arcname=f"market/stock/daily/qfq/{path.name}", recursive=False)
        for path in constituent_paths:
            archive.add(path, arcname=f"reference/index_constituents/{path.name}", recursive=False)
        for path in cache_files:
            archive.add(path, arcname=f"data_cache/{path.name}", recursive=False)

        payload = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        info = tarfile.TarInfo("manifest.json")
        info.size = len(payload)
        info.mtime = int(datetime.now(timezone.utc).timestamp())
        archive.addfile(info, io.BytesIO(payload))

    manifest.update(
        {
            "archive": str(output),
            "archive_bytes": output.stat().st_size,
            "archive_sha256": sha256(output),
        }
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Package AI Factor Lab market data for a private HF Dataset repo.")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--cache-root", type=Path)
    args = parser.parse_args()
    cache_root = args.cache_root.expanduser() if args.cache_root else None
    print(
        json.dumps(
            package_data(args.data_root.expanduser(), args.output.expanduser(), cache_root=cache_root),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
