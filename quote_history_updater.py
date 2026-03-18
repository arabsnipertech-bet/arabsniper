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


def round_or_zero(v, nd=4):
    try:
        return round(float(v), nd)
    except Exception:
        return 0.0


def market_drop(old_val, new_val):
    if old_val is None or new_val is None:
        return 0.0
    return round_or_zero(old_val - new_val, 4)


def normalize_fixture_id(v):
    try:
        return str(int(v))
    except Exception:
        return str(v).strip()


def dedupe_preserve_order(items):
    seen = set()
    out = []
    for item in items:
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


LIGHT_DROP = 0.04
MEDIUM_DROP = 0.08
STRONG_DROP = 0.15


def strength_from_drop(value):
    if value >= STRONG_DROP:
        return "strong"
    if value >= MEDIUM_DROP:
        return "medium"
    if value >= LIGHT_DROP:
        return "light"
    return "none"


def market_label_map():
    return {
        "o25": "O25",
        "o05ht": "O05HT",
        "o15ht": "O15HT",
        "q1": "1",
        "qx": "X",
        "q2": "2",
    }


def build_drop_tags(drop_map):
    label_map = market_label_map()
    positive = {k: v for k, v in drop_map.items() if v >= LIGHT_DROP}
    if not positive:
        return []

    sorted_markets = sorted(positive.items(), key=lambda x: x[1], reverse=True)
    best_market, best_value = sorted_markets[0]
    strength = strength_from_drop(best_value)

    tags = ["📉 DROP", f"📉 {label_map.get(best_market, best_market)}"]

    if len(positive) >= 2:
        tags.append("📉 MULTI")

    if strength == "strong":
        tags.append("🔥 DROP STRONG")
    elif strength == "medium":
        tags.append("⚠️ DROP MEDIUM")
    elif strength == "light":
        tags.append("▫️ DROP LIGHT")

    return dedupe_preserve_order(tags)


def build_info_drop_suffix(drop_map):
    label_map = market_label_map()
    positive = {k: v for k, v in drop_map.items() if v >= LIGHT_DROP}
    if not positive:
        return ""

    best_market = max(positive.items(), key=lambda x: x[1])[0]
    strength = strength_from_drop(positive[best_market])

    bits = ["📉DROP", f"📉{label_map.get(best_market, best_market)}"]

    if len(positive) >= 2:
        bits.append("MULTI")

    if strength == "strong":
        bits.append("STRONG")
    elif strength == "medium":
        bits.append("MED")
    else:
        bits.append("LIGHT")

    return " ".join(bits)


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


def compute_drop_maps(history_points):
    empty_map = {"q1": 0.0, "qx": 0.0, "q2": 0.0, "o25": 0.0, "o05ht": 0.0, "o15ht": 0.0}

    if not history_points:
        return empty_map.copy(), empty_map.copy()

    first = history_points[0].get("markets", {})
    last = history_points[-1].get("markets", {})

    open_map = {}
    for key in empty_map.keys():
        open_map[key] = market_drop(first.get(key), last.get(key))

    if len(history_points) < 2:
        return open_map, empty_map.copy()

    prev = history_points[-2].get("markets", {})
    last_map = {}
    for key in empty_map.keys():
        last_map[key] = market_drop(prev.get(key), last.get(key))

    return open_map, last_map


def best_positive_drop(drop_map):
    best_key = None
    best_val = 0.0
    for key, val in drop_map.items():
        if val > best_val:
            best_key = key
            best_val = val
    return best_key, round_or_zero(best_val, 4)


def append_history_from_day(day_num, label, history_db):
    path = BASE_DIR / f"details_day{day_num}.json"
    payload = load_json(path, {})

    if not isinstance(payload, dict) or "details" not in payload:
        print(f"⚠️ details_day{day_num}.json non valido o mancante.")
        return history_db

    ts = datetime.now().isoformat(timespec="seconds")
    updated = 0
    skipped = 0

    details = payload.get("details", {})
    for fixture_id, item in details.items():
        fixture_id = normalize_fixture_id(item.get("fixture_id", fixture_id))

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
            last_point = hist[-1]
            last_markets = last_point.get("markets", {})
            if last_markets == markets:
                skipped += 1
                history_db[fixture_id] = rec
                continue

        hist.append(point)
        rec["history"] = hist[-40:]
        history_db[fixture_id] = rec
        updated += 1

    print(f"🧠 DAY{day_num}: history aggiornata per {updated} fixture, {skipped} invariati.")
    return history_db


def enrich_details_file(day_num, history_db):
    path = BASE_DIR / f"details_day{day_num}.json"
    payload = load_json(path, {})

    if not isinstance(payload, dict) or "details" not in payload:
        print(f"⚠️ details_day{day_num}.json non valido per enrich.")
        return

    details = payload.get("details", {})
    touched = 0

    for fixture_key, item in list(details.items()):
        fixture_id = normalize_fixture_id(item.get("fixture_id", fixture_key))
        rec = history_db.get(fixture_id)

        if not rec:
            continue

        hist = rec.get("history", [])
        if not hist:
            continue

        open_map, last_map = compute_drop_maps(hist)
        best_market_open, best_open = best_positive_drop(open_map)
        best_market_last, best_last = best_positive_drop(last_map)

        flags = item.get("flags", {})
        if not isinstance(flags, dict):
            flags = {}

        flags["drop_diff"] = round_or_zero(best_open, 4)
        flags["drop_open_diff"] = round_or_zero(best_open, 4)
        flags["drop_last_diff"] = round_or_zero(best_last, 4)
        flags["drop_market"] = best_market_open or ""
        flags["drop_last_market"] = best_market_last or ""
        flags["drop_strength"] = strength_from_drop(best_open)
        flags["history_points"] = len(hist)
        flags["first_seen_at"] = hist[0].get("ts")
        flags["last_seen_at"] = hist[-1].get("ts")

        flags["drop_o25"] = round_or_zero(open_map["o25"], 4)
        flags["drop_o05ht"] = round_or_zero(open_map["o05ht"], 4)
        flags["drop_o15ht"] = round_or_zero(open_map["o15ht"], 4)
        flags["drop_q1"] = round_or_zero(open_map["q1"], 4)
        flags["drop_qx"] = round_or_zero(open_map["qx"], 4)
        flags["drop_q2"] = round_or_zero(open_map["q2"], 4)

        flags["drop_last_o25"] = round_or_zero(last_map["o25"], 4)
        flags["drop_last_o05ht"] = round_or_zero(last_map["o05ht"], 4)
        flags["drop_last_o15ht"] = round_or_zero(last_map["o15ht"], 4)
        flags["drop_last_q1"] = round_or_zero(last_map["q1"], 4)
        flags["drop_last_qx"] = round_or_zero(last_map["qx"], 4)
        flags["drop_last_q2"] = round_or_zero(last_map["q2"], 4)

        item["flags"] = flags

        original_tags = item.get("tags", [])
        if not isinstance(original_tags, list):
            original_tags = []

        drop_tags = build_drop_tags(open_map)
        item["tags"] = dedupe_preserve_order(original_tags + drop_tags)

        details[str(fixture_id)] = item
        touched += 1

    payload["details"] = details
    save_json(path, payload)
    print(f"✅ details_day{day_num}.json arricchito per {touched} fixture.")


def enrich_data_file(day_num, history_db):
    path = BASE_DIR / f"data_day{day_num}.json"
    rows = load_json(path, [])

    if not isinstance(rows, list):
        print(f"⚠️ data_day{day_num}.json non valido per enrich.")
        return

    touched = 0

    for row in rows:
        fixture_id = normalize_fixture_id(row.get("Fixture_ID"))
        rec = history_db.get(fixture_id)
        if not rec:
            continue

        hist = rec.get("history", [])
        if not hist:
            continue

        open_map, _ = compute_drop_maps(hist)
        info_suffix = build_info_drop_suffix(open_map)

        current_info = str(row.get("Info", "")).strip()
        if info_suffix:
            if info_suffix not in current_info:
                row["Info"] = (current_info + " " + info_suffix).strip()
                touched += 1

    save_json(path, rows)
    print(f"✅ data_day{day_num}.json aggiornato con tag drop per {touched} righe.")

    if day_num == 1:
        live_path = BASE_DIR / "data.json"
        live_rows = load_json(live_path, [])
        if isinstance(live_rows, list):
            touched_live = 0
            for row in live_rows:
                fixture_id = normalize_fixture_id(row.get("Fixture_ID"))
                rec = history_db.get(fixture_id)
                if not rec:
                    continue

                hist = rec.get("history", [])
                if not hist:
                    continue

                open_map, _ = compute_drop_maps(hist)
                info_suffix = build_info_drop_suffix(open_map)

                current_info = str(row.get("Info", "")).strip()
                if info_suffix and info_suffix not in current_info:
                    row["Info"] = (current_info + " " + info_suffix).strip()
                    touched_live += 1

            save_json(live_path, live_rows)
            print(f"✅ data.json aggiornato con tag drop per {touched_live} righe.")


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

    if not days:
        print("❌ Nessun day valido passato a --days")
        return

    history_db = load_json(QUOTE_HISTORY_FILE, {})

    for day_num in days:
        history_db = append_history_from_day(day_num, args.label, history_db)

    save_json(QUOTE_HISTORY_FILE, history_db)
    print(f"✅ quote_history.json aggiornato. Fixture archiviate: {len(history_db)}")

    for day_num in days:
        enrich_details_file(day_num, history_db)
        enrich_data_file(day_num, history_db)


if __name__ == "__main__":
    main()
