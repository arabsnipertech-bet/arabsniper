import json
import argparse
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
QUOTE_HISTORY_FILE = BASE_DIR / "quote_history.json"


def load_json(path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def parse_float(v):
    try:
        if v is None or v == "":
            return None
        return float(str(v).replace(",", "."))
    except Exception:
        return None


def market_drop(first_val, current_val):
    if first_val is None or current_val is None:
        return 0.0
    return round(first_val - current_val, 4)


def update_details_with_drop_metrics(details_payload, history_db):
    details = details_payload.get("details", {})
    for fixture_id, item in details.items():
        fixture_id = str(fixture_id)
        rec = history_db.get(fixture_id)
        if not rec:
            continue

        hist = rec.get("history", [])
        if not hist:
            continue

        first = hist[0]
        last = hist[-1]

        first_m = first.get("markets", {})
        last_m = last.get("markets", {})

        drop_o25 = market_drop(first_m.get("o25"), last_m.get("o25"))
        drop_o05ht = market_drop(first_m.get("o05ht"), last_m.get("o05ht"))
        drop_o15ht = market_drop(first_m.get("o15ht"), last_m.get("o15ht"))
        drop_q1 = market_drop(first_m.get("q1"), last_m.get("q1"))
        drop_qx = market_drop(first_m.get("qx"), last_m.get("qx"))
        drop_q2 = market_drop(first_m.get("q2"), last_m.get("q2"))

        max_drop = max(
            drop_o25,
            drop_o05ht,
            drop_o15ht,
            drop_q1,
            drop_qx,
            drop_q2,
            0.0
        )

        flags = item.get("flags", {})
        if not isinstance(flags, dict):
            flags = {}

        flags["drop_diff"] = round(max_drop, 4)
        flags["drop_o25"] = round(drop_o25, 4)
        flags["drop_o05ht"] = round(drop_o05ht, 4)
        flags["drop_o15ht"] = round(drop_o15ht, 4)
        flags["drop_q1"] = round(drop_q1, 4)
        flags["drop_qx"] = round(drop_qx, 4)
        flags["drop_q2"] = round(drop_q2, 4)
        flags["history_points"] = len(hist)
        flags["first_seen_at"] = first.get("ts")
        flags["last_seen_at"] = last.get("ts")

        item["flags"] = flags
        details[fixture_id] = item

    details_payload["details"] = details
    return details_payload


def build_market_snapshot(detail_item):
    markets = detail_item.get("markets", {}) or {}
    return {
        "q1": parse_float(markets.get("q1")),
        "qx": parse_float(markets.get("qx")),
        "q2": parse_float(markets.get("q2")),
        "o25": parse_float(markets.get("o25")),
        "o05ht": parse_float(markets.get("o05ht")),
        "o15ht": parse_float(markets.get("o15ht")),
    }


def append_history_from_day(day_num, label, history_db):
    path = BASE_DIR / f"details_day{day_num}.json"
    payload = load_json(path, {})

    if not isinstance(payload, dict) or "details" not in payload:
        print(f"⚠️ details_day{day_num}.json non valido o mancante.")
        return history_db

    ts = datetime.now().isoformat(timespec="seconds")
    updated = 0
    skipped = 0

    for fixture_id, item in payload.get("details", {}).items():
        fixture_id = str(fixture_id)
        markets = build_market_snapshot(item)

        match_name = item.get("match", "")
        country = item.get("country", "")
        league = item.get("league", "")
        day_date = item.get("date", payload.get("date", ""))

        rec = history_db.get(fixture_id, {
            "fixture_id": fixture_id,
            "match": match_name,
            "country": country,
            "league": league,
            "first_date": day_date,
            "history": []
        })

        rec["match"] = match_name or rec.get("match", "")
        rec["country"] = country or rec.get("country", "")
        rec["league"] = league or rec.get("league", "")
        rec["first_date"] = rec.get("first_date") or day_date

        point = {
            "ts": ts,
            "label": label,
            "day": day_num,
            "date": day_date,
            "markets": markets
        }

        hist = rec.get("history", [])
        if hist:
            last_markets = hist[-1].get("markets", {})
            if last_markets == markets:
                skipped += 1
                history_db[fixture_id] = rec
                continue

        hist.append(point)
        rec["history"] = hist[-30:]  # manteniamo gli ultimi 30 punti
        history_db[fixture_id] = rec
        updated += 1

    payload = update_details_with_drop_metrics(payload, history_db)
    save_json(path, payload)

    print(f"🧠 DAY{day_num}: history aggiornata per {updated} fixture, {skipped} invariati.")
    return history_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", required=True, help="Lista giorni separati da virgola, es. 1,2,3")
    parser.add_argument("--label", default="manual")
    args = parser.parse_args()

    days = []
    for part in args.days.split(","):
        part = part.strip()
        if part.isdigit():
            days.append(int(part))

    history_db = load_json(QUOTE_HISTORY_FILE, {})

    for day_num in days:
        history_db = append_history_from_day(day_num, args.label, history_db)

    save_json(QUOTE_HISTORY_FILE, history_db)
    print(f"✅ quote_history.json aggiornato. Fixture totali archiviate: {len(history_db)}")


if __name__ == "__main__":
    main()
