import json
from pathlib import Path

from app.main import app

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"


def main() -> None:
    CONTRACT_PATH.write_text(
        json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
