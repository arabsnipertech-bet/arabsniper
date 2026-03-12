import json
from datetime import datetime
from pathlib import Path

DATA_FILE = Path("data.json")

def main():

    if not DATA_FILE.exists():
        print("data.json non trovato")
        return

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    # prendiamo solo i free
    free_matches = [
        x for x in data
        if x.get("is_gold") or x.get("is_boost")
    ]

    # massimo 4
    free_matches = free_matches[:4]

    today = datetime.now().strftime("%Y-%m-%d")

    snapshot = []

    for m in free_matches:
        snapshot.append({
            "match": m.get("match"),
            "signal": m.get("signal"),
            "quote": m.get("quote"),
            "league": m.get("league"),
            "time": m.get("time")
        })

    out_file = Path(f"free_signals_{today}.json")

    out_file.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Creato snapshot {out_file}")


if __name__ == "__main__":
    main()
