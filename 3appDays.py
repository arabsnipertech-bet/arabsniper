import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import time
import sys
from pathlib import Path
from github import Github

# ==========================================
# CONFIGURAZIONE ARAB SNIPER V24.1 MULTI-DAY WEB
# Base derivata dalla V24 test
# Stretta selettiva su:
# - BOOST
# - GOLD
# + rolling snapshot 5 giorni
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = str(BASE_DIR / "arab_sniper_database.json")
SNAP_FILE = str(BASE_DIR / "arab_snapshot_database.json")
CONFIG_FILE = str(BASE_DIR / "nazioni_config.json")
DETAILS_FILE = str(BASE_DIR / "match_details.json")

DEFAULT_EXCLUDED = ["Thailand", "Indonesia", "India", "Kenya", "Morocco", "Rwanda", "Nigeria", "Oman", "Algeria", "UAE"]
LEAGUE_BLACKLIST = ["u19", "u20", "youth", "women", "friendly", "carioca", "paulista", "mineiro"]
ROLLING_SNAPSHOT_HORIZONS = [1, 2, 3, 4, 5]

REMOTE_MAIN_FILE = "data.json"
REMOTE_SNAPSHOT_FILE = "snapshot_odds.json"
REMOTE_DAY_FILES = {
    1: "data_day1.json",
    2: "data_day2.json",
    3: "data_day3.json",
    4: "data_day4.json",
    5: "data_day5.json",
}
REMOTE_DETAILS_FILES = {
    1: "details_day1.json",
    2: "details_day2.json",
    3: "details_day3.json",
    4: "details_day4.json",
    5: "details_day5.json",
}

try:
    from zoneinfo import ZoneInfo
    ROME_TZ = ZoneInfo("Europe/Rome")
except Exception:
    ROME_TZ = None


def now_rome():
    return datetime.now(ROME_TZ) if ROME_TZ else datetime.now()


st.set_page_config(page_title="ARAB SNIPER V24.1 MULTI-DAY WEB", layout="wide")

# ==========================================
# GITHUB UPDATE CORE
# ==========================================
def github_write_json(filename, payload, commit_message):
    try:
        token = os.getenv("GITHUB_TOKEN") or st.secrets.get("GITHUB_TOKEN")
        if not token:
            return "MISSING_TOKEN"

        g = Github(token)
        repo = g.get_repo("arabsnipertech-bet/arabsniper")
        content_str = json.dumps(payload, indent=4, ensure_ascii=False)

        try:
            contents = repo.get_contents(filename)
            repo.update_file(contents.path, commit_message, content_str, contents.sha)
            return "SUCCESS"
        except Exception:
            repo.create_file(filename, commit_message, content_str)
            return "SUCCESS"

    except Exception as e:
        return str(e)


def upload_to_github_main(results):
    return github_write_json(
        REMOTE_MAIN_FILE,
        results,
        "Update Arab Sniper Data"
    )


def upload_day_to_github(day_num, results):
    return github_write_json(
        REMOTE_DAY_FILES[day_num],
        results,
        f"Update Arab Sniper Day {day_num} Data"
    )


def upload_details_to_github(day_num, payload):
    return github_write_json(
        REMOTE_DETAILS_FILES[day_num],
        payload,
        f"Update Arab Sniper Day {day_num} Details"
    )


def upload_snapshot_to_github(payload):
    return github_write_json(
        REMOTE_SNAPSHOT_FILE,
        payload,
        "Update rolling snapshot odds"
    )


def download_remote_snapshot():
    try:
        url = f"https://raw.githubusercontent.com/arabsnipertech-bet/arabsniper/main/{REMOTE_SNAPSHOT_FILE}?v={int(time.time())}"
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            return None
        payload = r.json()
        if not isinstance(payload, dict):
            return None
        return payload
    except Exception:
        return None

# ==========================================
# SESSION STATE
# ==========================================
if "config" not in st.session_state:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                st.session_state.config = json.load(f)
        except Exception:
            st.session_state.config = {"excluded": DEFAULT_EXCLUDED}
    else:
        st.session_state.config = {"excluded": DEFAULT_EXCLUDED}

if "team_stats_cache" not in st.session_state:
    st.session_state.team_stats_cache = {}

if "team_last_matches_cache" not in st.session_state:
    st.session_state.team_last_matches_cache = {}

if "available_countries" not in st.session_state:
    st.session_state.available_countries = []

if "scan_results" not in st.session_state:
    st.session_state.scan_results = []

if "odds_memory" not in st.session_state:
    st.session_state.odds_memory = {}

if "match_details" not in st.session_state:
    st.session_state.match_details = {}

if "selected_fixture_for_modal" not in st.session_state:
    st.session_state.selected_fixture_for_modal = None


def save_config():
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(st.session_state.config, f, indent=4, ensure_ascii=False)


def load_db():
    today = now_rome().strftime("%Y-%m-%d")
    ts = None

    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f).get("results", [])
                st.session_state.scan_results = [r for r in data if r.get("Data", "") >= today]
        except Exception:
            pass

    if os.path.exists(SNAP_FILE):
        try:
            with open(SNAP_FILE, "r", encoding="utf-8") as f:
                snap_data = json.load(f)
                st.session_state.odds_memory = snap_data.get("odds", {})
                ts = snap_data.get("timestamp", "N/D")
        except Exception:
            pass

    if os.path.exists(DETAILS_FILE):
        try:
            with open(DETAILS_FILE, "r", encoding="utf-8") as f:
                details_data = json.load(f)
                st.session_state.match_details = details_data.get("details", {})
        except Exception:
            pass

    return ts


last_snap_ts = load_db()

# ==========================================
# API CORE & ROBUSTNESS
# ==========================================
API_KEY = os.getenv("API_SPORTS_KEY")

if not API_KEY:
    try:
        API_KEY = st.secrets.get("API_SPORTS_KEY", None)
    except Exception:
        pass

HEADERS = {"x-apisports-key": API_KEY} if API_KEY else {}


def api_get(session, path, params):
    if not API_KEY:
        return None

    for attempt in range(2):
        try:
            r = session.get(
                f"https://v3.football.api-sports.io/{path}",
                headers=HEADERS,
                params=params,
                timeout=20
            )
            if r.status_code == 200:
                return r.json()
            time.sleep(1)
        except Exception:
            if attempt == 1:
                return None
            time.sleep(1)
    return None


def _contains_ht(text):
    t = str(text or "").lower()
    return any(k in t for k in ["1st half", "first half", "1h", "ht", "half time", "halftime", "1° tempo"])


def safe_float(x, default=0.0):
    try:
        if x is None:
            return default
        if isinstance(x, (int, float)):
            return float(x)
        s = str(x).strip().replace(",", ".")
        if s in ("", "-", "None", "null"):
            return default
        return float(s)
    except Exception:
        return default


def is_blacklisted_league(league_name):
    name = str(league_name or "").lower()
    return any(k in name for k in LEAGUE_BLACKLIST)


def extract_elite_markets(session, fid):
    res = api_get(session, "odds", {"fixture": fid})
    if not res or not res.get("response"):
        return None

    mk = {"q1": 0.0, "qx": 0.0, "q2": 0.0, "o25": 0.0, "o05ht": 0.0, "o15ht": 0.0}

    for bm in res["response"][0].get("bookmakers", []):
        for b in bm.get("bets", []):
            name = (b.get("name") or "").lower()
            bid = b.get("id")

            if bid == 1 and mk["q1"] == 0:
                for v in b.get("values", []):
                    vl = str(v.get("value", "")).lower()
                    odd = safe_float(v.get("odd"), 0.0)
                    if "home" in vl:
                        mk["q1"] = odd
                    elif "draw" in vl:
                        mk["qx"] = odd
                    elif "away" in vl:
                        mk["q2"] = odd

            if bid == 5 and mk["o25"] == 0:
                if any(j in name for j in ["corner", "card", "booking"]):
                    continue
                for v in b.get("values", []):
                    if "over 2.5" in str(v.get("value", "")).lower():
                        mk["o25"] = safe_float(v.get("odd"), 0.0)

            if _contains_ht(name) and any(k in name for k in ["total", "over/under", "ou", "goals"]):
                if "team" in name:
                    continue
                for v in b.get("values", []):
                    val_txt = str(v.get("value", "")).lower().replace(",", ".")
                    if "over 0.5" in val_txt and mk["o05ht"] == 0:
                        mk["o05ht"] = safe_float(v.get("odd"), 0.0)
                    if "over 1.5" in val_txt and mk["o15ht"] == 0:
                        mk["o15ht"] = safe_float(v.get("odd"), 0.0)

        if mk["q1"] > 0 and mk["o25"] > 0 and mk["o05ht"] > 0:
            break

    if (1.01 <= mk["q1"] <= 1.10) or (1.01 <= mk["q2"] <= 1.10) or (1.01 <= mk["o25"] <= 1.30):
        return "SKIP"

    return mk


def save_snapshot_file(payload):
    with open(SNAP_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)

    upload_snapshot_to_github(payload)


def load_existing_snapshot_payload():
    if os.path.exists(SNAP_FILE):
        try:
            with open(SNAP_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
                if isinstance(payload, dict):
                    payload.setdefault("odds", {})
                    return payload
        except Exception:
            pass

    remote_payload = download_remote_snapshot()
    if isinstance(remote_payload, dict):
        remote_payload.setdefault("odds", {})
        return remote_payload

    return {
        "odds": {},
        "timestamp": None,
        "updated_at": None,
        "coverage": "rolling_day1_day5"
    }


def build_rolling_multiday_snapshot(session):
    """
    Salva la baseline quote di tutti i fixture Day1+Day2+Day3+Day4+Day5.
    Se un fixture_id esiste già, NON lo sovrascrive:
    così il drop resta ancorato alla prima quota vista.
    """
    target_dates = get_target_dates()
    existing_payload = load_existing_snapshot_payload()
    existing_odds = existing_payload.get("odds", {}) or {}

    new_odds = dict(existing_odds)
    active_fixture_ids = set()

    for horizon in ROLLING_SNAPSHOT_HORIZONS:
        target_date = target_dates[horizon - 1]

        res = api_get(session, "fixtures", {"date": target_date, "timezone": "Europe/Rome"})
        if not res:
            continue

        fx_list = [
            f for f in res.get("response", [])
            if f["fixture"]["status"]["short"] == "NS"
            and not is_blacklisted_league(f.get("league", {}).get("name", ""))
        ]

        for f in fx_list:
            fid = str(f["fixture"]["id"])
            active_fixture_ids.add(fid)

            mk = extract_elite_markets(session, f["fixture"]["id"])
            if not mk or mk == "SKIP":
                continue

            if fid not in new_odds:
                new_odds[fid] = {
                    "q1": mk["q1"],
                    "q2": mk["q2"],
                    "first_seen_date": target_date,
                    "first_seen_horizon": horizon,
                    "first_seen_ts": now_rome().strftime("%Y-%m-%d %H:%M:%S")
                }
            else:
                if isinstance(new_odds[fid], dict):
                    new_odds[fid]["last_seen_date"] = target_date
                    new_odds[fid]["last_seen_horizon"] = horizon
                    new_odds[fid]["last_seen_ts"] = now_rome().strftime("%Y-%m-%d %H:%M:%S")

        time.sleep(0.15)

    cleaned_odds = {}
    for fid, data in new_odds.items():
        if fid in active_fixture_ids:
            cleaned_odds[fid] = data

    payload = {
        "odds": cleaned_odds,
        "timestamp": now_rome().strftime("%H:%M"),
        "updated_at": now_rome().strftime("%Y-%m-%d %H:%M:%S"),
        "coverage": "rolling_day1_day5"
    }

    st.session_state.odds_memory = cleaned_odds
    save_snapshot_file(payload)
    return payload


def get_team_last_matches(session, tid):
    cache_key = str(tid)
    if cache_key in st.session_state.team_last_matches_cache:
        return st.session_state.team_last_matches_cache[cache_key]

    res = api_get(session, "fixtures", {"team": tid, "last": 8, "status": "FT"})
    fx = res.get("response", []) if res else []

    last_matches = []
    for f in fx:
        home_name = f.get("teams", {}).get("home", {}).get("name", "N/D")
        away_name = f.get("teams", {}).get("away", {}).get("name", "N/D")
        gh = f.get("goals", {}).get("home", 0)
        ga = f.get("goals", {}).get("away", 0)
        hth = f.get("score", {}).get("halftime", {}).get("home", 0)
        hta = f.get("score", {}).get("halftime", {}).get("away", 0)

        last_matches.append({
            "date": str(f.get("fixture", {}).get("date", ""))[:10],
            "league": f.get("league", {}).get("name", "N/D"),
            "match": f"{home_name} - {away_name}",
            "ht": f"{hth}-{hta}",
            "ft": f"{gh}-{ga}",
            "total_ht_goals": (hth or 0) + (hta or 0),
            "total_ft_goals": (gh or 0) + (ga or 0)
        })

    st.session_state.team_last_matches_cache[cache_key] = last_matches
    return last_matches


def get_team_performance(session, tid):
    if str(tid) in st.session_state.team_stats_cache:
        return st.session_state.team_stats_cache[str(tid)]

    res = api_get(session, "fixtures", {"team": tid, "last": 8, "status": "FT"})
    fx = res.get("response", []) if res else []
    if not fx:
        return None

    act = len(fx)
    tht, gf, gs = 0, 0, 0

    for f in fx:
        ht_data = f.get("score", {}).get("halftime", {})
        tht += (ht_data.get("home") or 0) + (ht_data.get("away") or 0)

        is_home = f["teams"]["home"]["id"] == tid
        gf += (f["goals"]["home"] or 0) if is_home else (f["goals"]["away"] or 0)
        gs += (f["goals"]["away"] or 0) if is_home else (f["goals"]["home"] or 0)

    last_f = fx[0]
    ft_sum = (last_f.get("goals", {}).get("home") or 0) + (last_f.get("goals", {}).get("away") or 0)
    ht_sum = (last_f.get("score", {}).get("halftime", {}).get("home") or 0) + (last_f.get("score", {}).get("halftime", {}).get("away") or 0)
    last_2h_zero = ((ft_sum - ht_sum) == 0)

    stats = {
        "avg_ht": tht / act,
        "avg_total": (gf + gs) / act,
        "last_2h_zero": last_2h_zero
    }

    st.session_state.team_stats_cache[str(tid)] = stats
    return stats

# ==========================================
# SCORING HELPERS V24.1
# ==========================================
def round3(x):
    return round(float(x), 3)


def symmetry_bonus(a, b, tight=0.22, medium=0.45):
    diff = abs(float(a) - float(b))
    if diff <= tight:
        return 0.8
    if diff <= medium:
        return 0.4
    return 0.0


def band_score(value, core_low, core_high, soft_low=None, soft_high=None, core_pts=1.0, soft_pts=0.45):
    v = safe_float(value, 0.0)
    if core_low <= v <= core_high:
        return core_pts
    if soft_low is not None and soft_high is not None and soft_low <= v <= soft_high:
        return soft_pts
    return 0.0


def compute_drop_diff(fid, mk):
    if fid not in st.session_state.odds_memory:
        return 0.0

    old_data = st.session_state.odds_memory.get(fid, {})
    if not isinstance(old_data, dict):
        return 0.0

    fav_is_home = mk["q1"] <= mk["q2"]
    old_q = safe_float(old_data.get("q1") if fav_is_home else old_data.get("q2"), 0.0)
    fav_now = min(mk["q1"], mk["q2"])

    if old_q > 0 and fav_now > 0 and old_q > fav_now:
        return round(old_q - fav_now, 3)
    return 0.0


def score_drop(drop_diff):
    if drop_diff >= 0.15:
        return 1.2
    if drop_diff >= 0.10:
        return 0.9
    if drop_diff >= 0.05:
        return 0.5
    return 0.0


def score_pt_signal(mk, s_h, s_a, combined_ht_avg):
    score = 0.0

    score += band_score(combined_ht_avg, 1.12, 1.70, 1.05, 1.90, core_pts=1.5, soft_pts=0.8)

    if s_h["avg_ht"] >= 1.10 and s_a["avg_ht"] >= 1.10:
        score += 1.6
    elif (s_h["avg_ht"] >= 1.25 and s_a["avg_ht"] >= 0.95) or (s_a["avg_ht"] >= 1.25 and s_h["avg_ht"] >= 0.95):
        score += 1.0

    score += symmetry_bonus(s_h["avg_ht"], s_a["avg_ht"], tight=0.20, medium=0.40)

    score += band_score(mk["o05ht"], 1.20, 1.40, 1.15, 1.48, core_pts=1.6, soft_pts=0.7)
    score += band_score(mk["o15ht"], 2.00, 3.60, 1.80, 4.20, core_pts=0.8, soft_pts=0.3)

    if s_h["last_2h_zero"] or s_a["last_2h_zero"]:
        score += 0.8

    if s_h["avg_total"] >= 1.20 and s_a["avg_total"] >= 1.20:
        score += 0.5

    return round3(score)


def score_over_signal(mk, s_h, s_a, combined_ht_avg, fav, drop_diff):
    score = 0.0

    if s_h["avg_total"] >= 1.55 and s_a["avg_total"] >= 1.55:
        score += 2.2
    elif s_h["avg_total"] >= 1.45 and s_a["avg_total"] >= 1.45:
        score += 1.4
    elif (s_h["avg_total"] >= 1.80 and s_a["avg_total"] >= 1.20) or (s_a["avg_total"] >= 1.80 and s_h["avg_total"] >= 1.20):
        score += 1.0

    score += symmetry_bonus(s_h["avg_total"], s_a["avg_total"], tight=0.28, medium=0.50)

    score += band_score(mk["o25"], 1.51, 2.37, 1.40, 2.55, core_pts=1.8, soft_pts=0.8)

    if combined_ht_avg >= 1.10:
        score += 0.7
    if combined_ht_avg >= 1.20:
        score += 0.3

    if 1.35 <= fav <= 2.20:
        score += 0.4

    score += score_drop(drop_diff) * 0.7

    return round3(score)


def score_boost_signal(mk, s_h, s_a, pt_score, over_score, drop_diff, combined_ht_avg):
    score = 0.0
    score += pt_score * 0.38
    score += over_score * 0.48

    if (s_h["avg_ht"] >= 1.30 and s_a["avg_ht"] >= 1.00) or (s_a["avg_ht"] >= 1.30 and s_h["avg_ht"] >= 1.00):
        score += 0.55
    elif s_h["avg_ht"] >= 1.15 and s_a["avg_ht"] >= 1.15:
        score += 0.35

    if s_h["avg_total"] >= 1.65 and s_a["avg_total"] >= 1.65:
        score += 0.55
    elif (s_h["avg_total"] >= 1.95 and s_a["avg_total"] >= 1.35) or (s_a["avg_total"] >= 1.95 and s_h["avg_total"] >= 1.35):
        score += 0.25

    if 1.60 <= mk["o25"] <= 2.12 and 1.22 <= mk["o05ht"] <= 1.36:
        score += 0.55
    elif 1.55 <= mk["o25"] <= 2.20 and 1.20 <= mk["o05ht"] <= 1.38:
        score += 0.20

    if combined_ht_avg >= 1.16:
        score += 0.35

    score += score_drop(drop_diff) * 0.45
    return round3(score)


def score_gold_signal(mk, s_h, s_a, pt_score, over_score, boost_score, fav, drop_diff, is_gold_zone, combined_ht_avg):
    score = 0.0
    score += pt_score * 0.22
    score += over_score * 0.30
    score += boost_score * 0.34

    if is_gold_zone:
        score += 0.85

    if combined_ht_avg >= 1.18 and s_h["avg_total"] >= 1.55 and s_a["avg_total"] >= 1.50:
        score += 0.45

    if 1.42 <= fav <= 1.82:
        score += 0.35

    if drop_diff >= 0.10:
        score += 0.55
    elif drop_diff >= 0.05:
        score += 0.25

    return round3(score)


def build_signal_package(fid, mk, s_h, s_a, combined_ht_avg):
    fav = min(mk["q1"], mk["q2"])
    is_gold_zone = (1.40 <= fav <= 1.90)
    drop_diff = compute_drop_diff(fid, mk)

    pt_score = score_pt_signal(mk, s_h, s_a, combined_ht_avg)
    over_score = score_over_signal(mk, s_h, s_a, combined_ht_avg, fav, drop_diff)
    boost_score = score_boost_signal(mk, s_h, s_a, pt_score, over_score, drop_diff, combined_ht_avg)
    gold_score = score_gold_signal(mk, s_h, s_a, pt_score, over_score, boost_score, fav, drop_diff, is_gold_zone, combined_ht_avg)

    tags = []
    probe_tags = []

    if (fav < 1.75)
