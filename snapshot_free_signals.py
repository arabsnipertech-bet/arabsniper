import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_FILE = Path("data.json")
MAX_FREE_MATCHES = 4


def safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def load_data() -> list[dict]:
    if not DATA_FILE.exists():
        print("data.json non trovato")
        return []

    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Errore lettura data.json: {exc}")
        return []

    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]

    if isinstance(raw, dict):
        for key in ("data", "results", "matches", "rows"):
            if isinstance(raw.get(key), list):
                return [x for x in raw[key] if isinstance(x, dict)]

    print("Formato data.json non riconosciuto")
    return []


def get_info_text(row: dict) -> str:
    return safe_str(row.get("Info"))


def get_match_text(row: dict) -> str:
    return safe_str(row.get("Match") or row.get("match"))


def get_time_text(row: dict) -> str:
    return safe_str(row.get("Ora") or row.get("time"))


def get_league_text(row: dict) -> str:
    return safe_str(row.get("Lega") or row.get("league"))


def get_fixture_id(row: dict) -> str:
    return safe_str(row.get("Fixture_ID") or row.get("fixture_id"))


def get_signal_label(row: dict) -> str:
    info = get_info_text(row).upper()

    if "GOLD" in info:
        return "GOLD TARGET"
    if "BOOST" in info:
        return "BOOST TARGET"
    if "OVER" in info:
        return "OVER 2.5"
    if "PT" in info:
        return "PT TARGET"

    # fallback morbido
    if safe_str(row.get("signal")):
        return safe_str(row.get("signal"))

    return ""


def get_quote_value(row: dict) -> str:
    info = get_info_text(row).upper()

    if "GOLD" in info:
        odds = safe_str(row.get("1X2"))
        if "|" in odds:
            parts = [p.strip() for p in odds.split("|") if p.strip()]
            return parts[0] if parts else odds
        return odds

    if "BOOST" in info or "OVER" in info:
        return safe_str(row.get("O2.5"))

    # fallback
    return (
        safe_str(row.get("O2.5"))
        or safe_str(row.get("1X2"))
        or safe_str(row.get("quota"))
    )


def signal_priority(row: dict) -> int:
    info = get_info_text(row).upper()

    if "GOLD" in info:
        return 1
    if "BOOST" in info:
        return 2
    if "OVER" in info:
        return 3
    if "PT" in info:
        return 4
    return 99


def has_usable_signal(row: dict) -> bool:
    info = get_info_text(row).upper()
    return any(tag in info for tag in ("GOLD", "BOOST", "OVER", "PT"))


def normalize_match_key(row: dict) -> str:
    match = get_match_text(row).lower()
    time_ = get_time_text(row)
    league = get_league_text(row).lower()
    return f"{time_}|{league}|{match}"


def row_is_valid(row: dict) -> bool:
    match = get_match_text(row)
    time_ = get_time_text(row)

    if not match or len(match) < 3:
        return False

    if not time_:
        return False

    if not has_usable_signal(row):
        return False

    return True


def select_free_matches(rows: list[dict]) -> list[dict]:
    cleaned = [r for r in rows if row_is_valid(r)]

    cleaned.sort(
        key=lambda r: (
            signal_priority(r),
            get_time_text(r),
            get_match_text(r).lower(),
        )
    )

    seen = set()
    selected = []

    for row in cleaned:
        key = normalize_match_key(row)
        if key in seen:
            continue
        seen.add(key)
        selected.append(row)
        if len(selected) >= MAX_FREE_MATCHES:
            break

    return selected


def build_snapshot_row(row: dict, snapshot_date: str) -> dict:
    return {
        "data": snapshot_date,
        "time": get_time_text(row),
        "match": get_match_text(row),
        "league": get_league_text(row),
        "fixture_id": get_fixture_id(row),
        "signal": get_signal_label(row),
        "quote": get_quote_value(row),
        "info": get_info_text(row),
    }


def write_snapshot(rows: list[dict]) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    out_file = Path(f"free_signals_{today}.json")

    snapshot = [build_snapshot_row(r, today) for r in rows]

    out_file.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Creato snapshot: {out_file}")
    print(f"Match salvati: {len(snapshot)}")

    for idx, item in enumerate(snapshot, start=1):
        print(
            f"{idx}. {item['time']} | {item['match']} | "
            f"{item['signal']} | quota {item['quote']}"
        )


def main() -> None:
    rows = load_data()
    if not rows:
        print("Nessun dato disponibile in data.json")
        return

    selected = select_free_matches(rows)
    write_snapshot(selected)


if __name__ == "__main__":
    main()
