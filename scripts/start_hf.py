from __future__ import annotations

import os
import sys
import tarfile
from pathlib import Path

import uvicorn


REQUIRED_CONSTITUENTS = (
    "000300_comp.csv",
    "000905_comp.csv",
    "000852_comp.csv",
)
REPO_ROOT = Path(__file__).resolve().parents[1]


def data_is_ready(data_root: Path) -> bool:
    price_root = data_root / "market" / "stock" / "daily" / "qfq"
    constituent_root = data_root / "reference" / "index_constituents"
    return (
        price_root.is_dir()
        and any(price_root.glob("*.parquet"))
        and all((constituent_root / name).is_file() for name in REQUIRED_CONSTITUENTS)
    )


def safe_extract(archive_path: Path, destination: Path) -> None:
    destination = destination.resolve()
    with tarfile.open(archive_path, "r") as archive:
        for member in archive.getmembers():
            if member.issym() or member.islnk():
                raise ValueError(f"Archive links are not allowed: {member.name}")
            target = (destination / member.name).resolve()
            if destination not in target.parents and target != destination:
                raise ValueError(f"Unsafe path in data archive: {member.name}")
        archive.extractall(destination)


def ensure_data() -> Path:
    data_root = Path(os.environ.get("QUANT_DATA_ROOT", "/home/user/data")).expanduser()
    if data_is_ready(data_root):
        return data_root

    repo_id = os.environ.get("HF_DATASET_REPO", "").strip()
    if not repo_id:
        raise RuntimeError("HF_DATASET_REPO is required when QUANT_DATA_ROOT is not pre-populated")

    filename = os.environ.get("HF_DATA_ARCHIVE", "quant_data.tar").strip()
    token = os.environ.get("HF_DATA_TOKEN") or os.environ.get("HF_TOKEN") or None
    from huggingface_hub import hf_hub_download

    archive_path = Path(
        hf_hub_download(
            repo_id=repo_id,
            repo_type="dataset",
            filename=filename,
            token=token,
        )
    )
    data_root.mkdir(parents=True, exist_ok=True)
    safe_extract(archive_path, data_root)
    if not data_is_ready(data_root):
        raise RuntimeError(f"Extracted dataset is incomplete under {data_root}")
    return data_root


def main() -> None:
    data_root = ensure_data()
    os.environ["QUANT_DATA_ROOT"] = str(data_root)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "7860")),
        log_level=os.environ.get("LOG_LEVEL", "info").lower(),
    )


if __name__ == "__main__":
    main()
