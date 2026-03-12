import json
from datetime import datetime
from pathlib import Path

DATA_FILE = Path("data.json")

def main():

    if not DATA_FILE.exists():
        print("data.json non trovato")
        return

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    free = [
        x for x in data
        if x.get("is_gold") or x.get("is_boost")
    ]

    free = free[:4]

    today = datetime.now().strftime("%Y-%m-%d")

    out = Path(f"free_signals_{today}.json")

    out.write_text(
        json.dumps(free, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("Snapshot creato:", out)


if __name__ == "__main__":
    main()
