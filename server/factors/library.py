import json

from server.config import DATA_CACHE_DIR

LIBRARY_FILE = DATA_CACHE_DIR / "saved_factors.json"


class FactorLibrary:
    @staticmethod
    def get_all_factors() -> list[dict[str, str]]:
        if not LIBRARY_FILE.exists():
            return []
        try:
            with open(LIBRARY_FILE, "r", encoding="utf-8") as file:
                saved = json.load(file)
            return saved if isinstance(saved, list) else []
        except Exception:
            return []

    @staticmethod
    def save_factor(name: str, expression: str, description: str = "") -> None:
        factors = FactorLibrary.get_all_factors()
        factors = [item for item in factors if item.get("name") != name]
        factors.insert(0, {"name": name, "expression": expression, "description": description})
        FactorLibrary._write(factors)

    @staticmethod
    def delete_factor(name: str) -> bool:
        factors = FactorLibrary.get_all_factors()
        remaining = [item for item in factors if item.get("name") != name]
        FactorLibrary._write(remaining)
        return len(remaining) != len(factors)

    @staticmethod
    def clear() -> None:
        FactorLibrary._write([])

    @staticmethod
    def _write(factors: list[dict[str, str]]) -> None:
        DATA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(LIBRARY_FILE, "w", encoding="utf-8") as file:
            json.dump(factors, file, ensure_ascii=False, indent=2)
