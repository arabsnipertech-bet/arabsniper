import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import requests

# =========================
# CONFIG
# =========================
BASE_DIR = Path(__file__).resolve().parent
SNAPSHOT_GLOB = "free_signals_*.json"
OUT_FILE = BASE_DIR / "casse_recenti.json"

SPORTSDB_SEARCH_URL = "https://www.thesportsdb.com/api/v1/json/123/searchevents.php"
REQUEST_TIMEOUT = 12
MAX_OUTPUT = 12

session = requests.Session()
session.headers.update({"User-Agent": "ArabSniperBet/2.0"})


# =========================
# HELPERS TESTO / MATCH
# =========================
def strip_accents(value: str) -> str:
    value = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in value if unicodedata.category(ch) != "Mn")


def clean_text(value: str) -> str:
    value = strip_accents(str(value or "").lower())
    value = re.sub(r"\bu\d{2}\b", " ", value)
    value = re.sub(r"\breserves?\b", " ", value)
    value = re.sub(r"\bii\b|\biii\b|\biv\b", " ", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def split_match(match_name: str):
    raw = str(match_name or "").strip()
    if " - " in raw:
        parts = [p.strip() for p in raw.split(" - ") if p.strip()]
    elif "-" in raw:
        parts = [p.strip() for p in raw.split("-") if p.strip()]
    else:
        parts = []

    if len(parts) >= 2:
        return parts[0], parts[1]
    return None, None


def build_queries(match_name: str):
    home, away = split_match(match_name)
    if not home or not away:
        return []

    queries = [
        f"{home} vs {away}",
        f"{away} vs {home}",
        f"{home} v {away}",
        f"{home} {away}",
    ]

    out = []
    seen = set()
    for q in queries:
        key = clean_text(q)
        if key and key not in seen:
            seen.add(key)
            out.append(q)
    return out


def get_tokens(text: str):
    return [t for t in clean_text(text).split() if len(t) >= 3]


def overlap_score(match_name: str, event_name: str) -> int:
    a = set(get_tokens(match_name))
    b = set(get_tokens(event_name))
    return len(a & b)


# =========================
# HELPERS QUOTE / SIGNAL
# =========================
def parse_float(value) -> float | None:
    try:
        v = str(value or "").strip().replace(",", ".")
        if not v:
            return None
        return float(v)
    except Exception:
        return None


def normalize_signal(signal: str) -> str:
    s = str(signal or "").upper().strip()

    if "OVER" in s:
        return "OVER 2.5"
    if "PT" in s:
        return "PT TARGET"
    if "BOOST" in s:
        return "BOOST TARGET"
    if "GOLD" in s:
        return "GOLD TARGET"

    return s or "UNKNOWN"


def quote_band_status(signal: str, quote_value: str) -> str:
    """
    Non blocca l'esito: aggiunge solo un contesto sintetico.
    """
    q = parse_float(quote_value)
    sig = normalize_signal(signal)

    if q is None:
        return "quota n/d"

    if sig == "GOLD TARGET":
        return "quota ok" if 1.40 <= q <= 2.80 else "quota fuori range"
    if sig == "BOOST TARGET":
        return "quota ok" if 1.40 <= q <= 2.80 else "quota fuori range"
    if sig == "OVER 2.5":
        return "quota ok" if 1.40 <= q <= 2.80 else "quota fuori range"
    if sig == "PT TARGET":
        return "quota ok" if 1.20 <= q <= 2.20 else "quota fuori range"

    return "quota non classificata"


# =========================
# SNAPSHOTS
# =========================
def parse_snapshot_date_from_filename(path: Path):
    m = re.search(r"free_signals_(\d{4}-\d{2}-\d{2})\.json$", path.name)
    if not m:
        return None
    return m.group(1)


def load_snapshots():
    files = sorted(BASE_DIR.glob(SNAPSHOT_GLOB))
    rows = []

    for fp in files:
        snapshot_date = parse_snapshot_date_from_filename(fp)
        if not snapshot_date:
            continue

        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[WARN] Impossibile leggere {fp.name}: {e}")
            continue

        if not isinstance(data, list):
            print(f"[WARN] {fp.name} non contiene una lista JSON valida.")
            continue

        for item in data:
            match_name = str(item.get("match", "")).strip()
            signal = str(item.get("signal", "")).strip()
            quote = str(item.get("quote", "")).strip()
            league = str(item.get("league", "")).strip()
            time_str = str(item.get("time", "")).strip()
            fixture_id = str(item.get("fixture_id", "")).strip()
            info = str(item.get("info", "")).strip()

            if not match_name or not signal:
                continue

            rows.append(
                {
                    "data": snapshot_date,
                    "snapshot_date": snapshot_date,
                    "match": match_name,
                    "signal": normalize_signal(signal),
                    "quote": quote,
                    "league": league,
                    "time": time_str,
                    "fixture_id": fixture_id,
                    "info": info,
                }
            )

    return rows


# =========================
# SEARCH RISULTATI
# =========================
def parse_event_date(ev: dict):
    date_str = ev.get("dateEvent")
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        return None


def extract_score(ev: dict):
    hs = ev.get("intHomeScore")
    aw = ev.get("intAwayScore")
    if hs in (None, "") or aw in (None, ""):
        return None
    try:
        hs_i = int(hs)
        aw_i = int(aw)
        return hs_i, aw_i
    except Exception:
        return None


def choose_best_event(match_name: str, snapshot_date: str, events: list):
    try:
        target_date = datetime.strptime(snapshot_date, "%Y-%m-%d").date()
    except Exception:
        return None

    ranked = []

    for ev in events:
        ev_name = ev.get("strEvent") or ""
        score = extract_score(ev)
        if not score:
            continue

        ev_date = parse_event_date(ev)
        if ev_date != target_date:
            continue

        name_score = overlap_score(match_name, ev_name)
        if name_score < 2:
            continue

        ranked.append((name_score, ev))

    if not ranked:
        return None

    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


def search_finished_result(match_name: str, snapshot_date: str):
    queries = build_queries(match_name)

    for q in queries:
        try:
            r = session.get(
                SPORTSDB_SEARCH_URL,
                params={"e": q},
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            payload = r.json()
        except Exception as e:
            print(f"[WARN] Errore ricerca '{q}': {e}")
            continue

        events = payload.get("event") or []
        if not events:
            continue

        best = choose_best_event(match_name, snapshot_date, events)
        if not best:
            continue

        score = extract_score(best)
        if not score:
            continue

        hs_i, aw_i = score
        total_goals = hs_i + aw_i

        return {
            "ft_score": f"{hs_i}-{aw_i}",
            "home_goals": hs_i,
            "away_goals": aw_i,
            "total_goals": total_goals,
        }

    return None


# =========================
# VALUTAZIONE PIU' FEDELE
# =========================
def evaluate_signal_result(signal: str, total_goals: int, quote_value: str) -> str | None:
    sig = normalize_signal(signal)
    qtag = quote_band_status(sig, quote_value)

    # OVER 2.5 = verifica netta FT
    if sig == "OVER 2.5":
        if total_goals >= 3:
            return f"✅ O2.5 VERIFICATA | FT>=3 | {qtag}"
        return f"❌ O2.5 NON VERIFICATA | FT<3 | {qtag}"

    # GOLD = segnale composito, ma sul sito lo leggiamo in chiave gol finale
    if sig == "GOLD TARGET":
        if total_goals >= 3:
            return f"✅ GOLD FORTE | FT>=3 | {qtag}"
        if total_goals == 2:
            return f"🟡 GOLD SOFT | FT=2 | {qtag}"
        return f"❌ GOLD NON VERIFICATA | FT<2 | {qtag}"

    # BOOST = segnale forte ma non identico a un over puro
    if sig == "BOOST TARGET":
        if total_goals >= 3:
            return f"✅ BOOST FORTE | FT>=3 | {qtag}"
        if total_goals == 2:
            return f"🟡 BOOST SOFT | FT=2 | {qtag}"
        return f"❌ BOOST NON VERIFICATA | FT<2 | {qtag}"

    # PT TARGET = con i dati attuali non possiamo certificare l'HT reale
    # quindi usiamo un esito prudente e onesto, basato sul FT
    if sig == "PT TARGET":
        if total_goals >= 3:
            return f"✅ PT-LIKE FORTE | HT n/d | FT>=3 | {qtag}"
        if total_goals == 2:
            return f"🟡 PT-LIKE SOFT | HT n/d | FT=2 | {qtag}"
        return f"❌ PT-LIKE NON VERIFICATA | HT n/d | FT<2 | {qtag}"

    # fallback
    if total_goals >= 3:
        return f"✅ VERIFICATA | FT>=3 | {qtag}"
    if total_goals == 2:
        return f"🟡 SOFT | FT=2 | {qtag}"
    return f"❌ NON VERIFICATA | FT<2 | {qtag}"


def should_publish_row(signal: str, verdict: str) -> bool:
    """
    Per la homepage tengo solo risultati almeno 'soft' o forti.
    Gli esiti completamente negativi non li mostro nella sezione casse.
    """
    if not verdict:
        return False
    return verdict.startswith("✅") or verdict.startswith("🟡")


# =========================
# MAIN
# =========================
def main():
    rows = load_snapshots()

    if not rows:
        OUT_FILE.write_text("[]", encoding="utf-8")
        print("Nessuno snapshot trovato. Creato casse_recenti.json vuoto.")
        return

    output = []
    seen = set()

    for row in rows:
        unique_key = row["fixture_id"] or f'{row["snapshot_date"]}|{row["match"]}'
        if unique_key in seen:
            continue
        seen.add(unique_key)

        result = search_finished_result(row["match"], row["snapshot_date"])
        if not result:
            print(f"[INFO] Nessun risultato trovato per {row['match']} ({row['snapshot_date']})")
            continue

        verdict = evaluate_signal_result(
            signal=row["signal"],
            total_goals=result["total_goals"],
            quote_value=row["quote"],
        )

        if not should_publish_row(row["signal"], verdict):
            continue

        output.append(
            {
                "data": row["snapshot_date"],
                "match": row["match"],
                "signal": row["signal"],
                "quote": row["quote"],
                "result": f'{result["ft_score"]} {verdict}',
                "league": row["league"],
                "time": row["time"],
                "fixture_id": row["fixture_id"],
            }
        )

    output.sort(key=lambda x: (x.get("data", ""), x.get("time", "")), reverse=True)

    final_output = [
        {
            "data": x["data"],
            "match": x["match"],
            "signal": x["signal"],
            "quote": x["quote"],
            "result": x["result"],
        }
        for x in output[:MAX_OUTPUT]
    ]

    OUT_FILE.write_text(
        json.dumps(final_output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"Creato {OUT_FILE.name} con {len(final_output)} record.")
    for row in final_output:
        print(f"- {row['data']} | {row['match']} | {row['signal']} | {row['result']}")


if __name__ == "__main__":
    main()
