import json
import os
from datetime import datetime

DATA_FILES = [
    "data_day1.json",
    "data_day2.json",
    "data_day3.json",
    "data_day4.json",
    "data_day5.json",
]

OUTPUT_FILE = "casse_recenti.json"


def load_json(file):
    if not os.path.exists(file):
        return []
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def extract_casse():
    all_matches = []

    for file in DATA_FILES:
        data = load_json(file)

        if not isinstance(data, list):
            continue

        for row in data:
            info = str(row.get("Info", "")).upper()

            if "GOLD" not in info and "BOOST" not in info:
                continue

            fixture_id = str(row.get("Fixture_ID", "")).strip()

            if not fixture_id:
                continue

            match_data = {
                "fixture_id": fixture_id,
                "match": row.get("Match"),
                "league": row.get("Lega"),
                "time": row.get("Ora"),
                "info": row.get("Info"),
                "o25": row.get("O2.5"),
                "o05h": row.get("O0.5H"),
                "o15h": row.get("O1.5H"),
                "source_day": file,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            all_matches.append(match_data)

    return all_matches


def deduplicate(matches):
    seen = {}
    for m in matches:
        fid = m["fixture_id"]

        # tieni l'ultimo aggiornamento
        seen[fid] = m

    return list(seen.values())


def save_output(matches):
    matches = sorted(matches, key=lambda x: x["time"] or "")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(matches, f, indent=4, ensure_ascii=False)


if __name__ == "__main__":
    print("📦 Costruzione casse recenti...")

    matches = extract_casse()

    if not matches:
        print("⚠️ Nessuna cassa trovata")
        save_output([])
        exit(0)

    matches = deduplicate(matches)

    save_output(matches)

    print(f"✅ Casse salvate: {len(matches)}")
