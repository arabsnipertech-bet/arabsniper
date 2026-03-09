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
# CONFIGURAZIONE ARAB SNIPER TEST VERSION
# ISOLATA DALLA PRODUZIONE
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
BASE_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = str(BASE_DIR / "arab_sniper_database_test.json")
SNAP_FILE = str(BASE_DIR / "arab_snapshot_database_test.json")
CONFIG_FILE = str(BASE_DIR / "nazioni_config_test.json")
DETAILS_FILE = str(BASE_DIR / "match_details_test.json")

# File remoti SOLO TEST (mai più data.json principale)
REMOTE_TEST_DATA_FILE = ".test/data_test.json"
REMOTE_TEST_DETAILS_FILE = ".test/match_details_test.json"

DEFAULT_EXCLUDED = [
    "Thailand", "Indonesia", "India", "Kenya", "Morocco",
    "Rwanda", "Nigeria", "Oman", "Algeria", "UAE"
]
LEAGUE_BLACKLIST = ["u19", "u20", "youth", "women", "friendly", "carioca", "paulista", "mineiro"]

try:
    from zoneinfo import ZoneInfo
    ROME_TZ = ZoneInfo("Europe/Rome")
except Exception:
    ROME_TZ = None

def now_rome():
    return datetime.now(ROME_TZ) if ROME_TZ else datetime.now()

st.set_page_config(page_title="ARAB SNIPER TEST WEB", layout="wide")

# ==========================================
# GITHUB TEST UPLOAD (ISOLATO)
# Scrive SOLO in .test/, mai in data.json root
# ==========================================
def github_write_json(remote_filename, payload, commit_message):
    try:
        token = os.getenv("GITHUB_TOKEN") or st.secrets.get("GITHUB_TOKEN")
        if not token:
            return "MISSING_TOKEN"

        g = Github(token)
        repo = g.get_repo("Arabsnipertech-bet/arabsniper")
        content_str = json.dumps(payload, indent=4, ensure_ascii=False)

        try:
            contents = repo.get_contents(remote_filename)
            repo.update_file(contents.path, commit_message, content_str, contents.sha)
            return "SUCCESS"
        except Exception:
            repo.create_file(remote_filename, commit_message, content_str)
            return "SUCCESS"

    except Exception as e:
        return str(e)

def upload_test_results_to_github(results):
    return github_write_json(
        REMOTE_TEST_DATA_FILE,
        results,
        "Update TEST Arab Sniper Data"
    )

def upload_test_details_to_github(details_payload):
    return github_write_json(
        REMOTE_TEST_DETAILS_FILE,
        details_payload,
        "Update TEST Arab Sniper Match Details"
    )

# ==========================================
# INIZIALIZZAZIONE SESSION STATE
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
API_KEY = os.getenv("API_SPORTS_KEY") or st.secrets.get("API_SPORTS_KEY", None)
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

def save_match_details_file():
    payload = {
        "updated_at": now_rome().strftime("%Y-%m-%d %H:%M:%S"),
        "details": st.session_state.match_details
    }
    with open(DETAILS_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=4, ensure_ascii=False)
    return payload

# ==========================================
# SCAN CORE CON STORAGE SOLO TEST
# ==========================================
def run_full_scan(snap=False):
    target_dates = [(now_rome().date() + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]

    with st.spinner(f"🚀 Analisi mercati {target_dates[HORIZON - 1]}..."):
        with requests.Session() as s:
            target_date = target_dates[HORIZON - 1]
            res = api_get(s, "fixtures", {"date": target_date, "timezone": "Europe/Rome"})
            if not res:
                st.error("❌ Nessuna risposta valida dall'API.")
                return

            day_fx = [
                f for f in res.get("response", [])
                if f["fixture"]["status"]["short"] == "NS"
                and not is_blacklisted_league(f.get("league", {}).get("name", ""))
            ]

            st.session_state.available_countries = sorted(
                list(set(st.session_state.available_countries) | {fx["league"]["country"] for fx in day_fx})
            )

            if snap:
                csnap = {}
                snap_bar = st.progress(0, text="📌 SNAPSHOT IN CORSO...")

                for i, f in enumerate(day_fx):
                    snap_bar.progress((i + 1) / len(day_fx) if day_fx else 1.0)
                    m = extract_elite_markets(s, f["fixture"]["id"])
                    if m and m != "SKIP":
                        csnap[str(f["fixture"]["id"])] = {"q1": m["q1"], "q2": m["q2"]}
                    time.sleep(0.2)

                st.session_state.odds_memory = csnap
                with open(SNAP_FILE, "w", encoding="utf-8") as f:
                    json.dump(
                        {"odds": csnap, "timestamp": now_rome().strftime("%H:%M")},
                        f,
                        indent=4,
                        ensure_ascii=False
                    )
                snap_bar.empty()

            final_list = []
            details_map = dict(st.session_state.match_details)

            pb = st.progress(0, text="🚀 ANALISI SEGNALI E MEDIE...")
            for i, f in enumerate(day_fx):
                pb.progress((i + 1) / len(day_fx) if day_fx else 1.0)

                cnt = f["league"]["country"]
                if cnt in st.session_state.config["excluded"]:
                    continue

                fid = str(f["fixture"]["id"])
                mk = extract_elite_markets(s, fid)
                if not mk or mk == "SKIP" or mk["q1"] == 0:
                    continue

                home_team = f["teams"]["home"]
                away_team = f["teams"]["away"]

                s_h = get_team_performance(s, home_team["id"])
                s_a = get_team_performance(s, away_team["id"])
                if not s_h or not s_a:
                    continue

                combined_ht_avg = (s_h["avg_ht"] + s_a["avg_ht"]) / 2
                if combined_ht_avg < 1.05:
                    continue

                fav = min(mk["q1"], mk["q2"])
                is_gold_zone = (1.40 <= fav <= 1.90)
                tags = ["M-Ok"]

                if fid in st.session_state.odds_memory:
                    old_data = st.session_state.odds_memory[fid]
                    old_q = old_data["q1"] if mk["q1"] < mk["q2"] else old_data["q2"]
                    if old_q > fav:
                        diff = old_q - fav
                        if diff >= 0.05:
                            tags.append(f"📉-{diff:.2f}")

                h_p, h_o, h_g = False, False, False

                if (fav < 1.75) and (s_h["avg_total"] >= 1.0 and s_a["avg_total"] >= 1.0):
                    tags.append("🐟O")
                    h_p = True

                if (2.0 <= mk["q1"] <= 3.5) and (2.0 <= mk["q2"] <= 3.5) and (s_h["avg_total"] >= 1.0 and s_a["avg_total"] >= 1.0):
                    tags.append("🐟G")
                    h_p = True

                cond_ft_155 = (s_h["avg_total"] >= 1.55 and s_a["avg_total"] >= 1.55)
                cond_q_o25 = (1.51 <= mk["o25"] <= 2.37)
                cond_q_o05h = (1.21 <= mk["o05ht"] <= 1.40)

                if cond_ft_155 and cond_q_o25 and cond_q_o05h:
                    cond_boost_ht = (s_h["avg_ht"] >= 1.27 or s_a["avg_ht"] >= 1.27)
                    cond_boost_ft = (s_h["avg_total"] > 1.85 or s_a["avg_total"] > 1.85)
                    if cond_boost_ht and cond_boost_ft:
                        tags.append("🚀 BOOST")
                        h_o = True
                    else:
                        tags.append("⚽ OVER")
                        h_o = True

                cond_pt_ht = (s_h["avg_ht"] >= 1.1 and s_a["avg_ht"] >= 1.1)
                cond_pt_ft = (s_h["avg_total"] >= 1.1 and s_a["avg_total"] >= 1.1)
                cond_pt_odd = (1.20 <= mk["o05ht"] <= 1.40)
                cond_pt_last = (s_h["last_2h_zero"] or s_a["last_2h_zero"])

                if cond_pt_ht and cond_pt_ft and cond_pt_odd and cond_pt_last:
                    tags.append("🎯PT")
                    h_g = True

                if h_p and h_o and h_g:
                    tags.insert(0, "⚽⭐ GOLD")

                row = {
                    "Ora": f["fixture"]["date"][11:16],
                    "Lega": f"{f['league']['name']} ({cnt})",
                    "Match": f"{home_team['name']} - {away_team['name']}",
                    "FAV": "✅" if is_gold_zone else "❌",
                    "1X2": f"{mk['q1']:.1f}|{mk['qx']:.1f}|{mk['q2']:.1f}",
                    "O2.5": f"{mk['o25']:.2f}",
                    "O0.5H": f"{mk['o05ht']:.2f}",
                    "O1.5H": f"{mk['o15ht']:.2f}",
                    "AVG FT": f"{s_h['avg_total']:.1f}|{s_a['avg_total']:.1f}",
                    "AVG HT": f"{s_h['avg_ht']:.1f}|{s_a['avg_ht']:.1f}",
                    "Info": " ".join(tags),
                    "Data": f["fixture"]["date"][:10],
                    "Fixture_ID": f["fixture"]["id"]
                }
                final_list.append(row)

                details_map[fid] = {
                    "fixture_id": f["fixture"]["id"],
                    "date": f["fixture"]["date"][:10],
                    "time": f["fixture"]["date"][11:16],
                    "league": f["league"]["name"],
                    "country": cnt,
                    "match": f"{home_team['name']} - {away_team['name']}",
                    "home_team": home_team["name"],
                    "away_team": away_team["name"],
                    "markets": {
                        "q1": mk["q1"],
                        "qx": mk["qx"],
                        "q2": mk["q2"],
                        "o25": mk["o25"],
                        "o05ht": mk["o05ht"],
                        "o15ht": mk["o15ht"]
                    },
                    "averages": {
                        "home_avg_ft": round(s_h["avg_total"], 3),
                        "away_avg_ft": round(s_a["avg_total"], 3),
                        "home_avg_ht": round(s_h["avg_ht"], 3),
                        "away_avg_ht": round(s_a["avg_ht"], 3),
                        "combined_ht_avg": round(combined_ht_avg, 3)
                    },
                    "flags": {
                        "fav_quote": round(fav, 3),
                        "is_gold_zone": is_gold_zone,
                        "home_last_2h_zero": s_h["last_2h_zero"],
                        "away_last_2h_zero": s_a["last_2h_zero"]
                    },
                    "tags": tags,
                    "home_last_8": get_team_last_matches(s, home_team["id"]),
                    "away_last_8": get_team_last_matches(s, away_team["id"])
                }

                time.sleep(0.2)

            current_db = {str(r["Fixture_ID"]): r for r in st.session_state.scan_results}
            for r in final_list:
                current_db[str(r["Fixture_ID"])] = r

            st.session_state.scan_results = list(current_db.values())
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump({"results": st.session_state.scan_results}, f, indent=4, ensure_ascii=False)

            st.session_state.match_details = details_map
            details_payload = save_match_details_file()

            # Upload SOLO TEST remoti
            status_data = upload_test_results_to_github(st.session_state.scan_results)
            status_details = upload_test_details_to_github(details_payload)

            if status_data == "SUCCESS":
                st.success("✅ TEST DATA aggiornato in .test/data_test.json")
            else:
                st.warning(f"⚠️ TEST DATA non aggiornato su GitHub: {status_data}")

            if status_details == "SUCCESS":
                st.success("✅ TEST DETAILS aggiornato in .test/match_details_test.json")
            else:
                st.warning(f"⚠️ TEST DETAILS non aggiornato su GitHub: {status_details}")

            pb.empty()

            if "--auto" not in sys.argv and "--fast" not in sys.argv:
                time.sleep(2)
                st.rerun()

# ==========================================
# UI SIDEBAR
# ==========================================
st.sidebar.header("👑 Arab Sniper TEST WEB")
HORIZON = st.sidebar.selectbox("Orizzonte Temporale:", options=[1, 2, 3], index=0)
target_dates = [(now_rome().date() + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]

all_discovered = sorted(list(set(st.session_state.get("available_countries", []))))
if st.session_state.scan_results:
    historical_cnt = {r["Lega"].split("(")[-1].replace(")", "") for r in st.session_state.scan_results}
    all_discovered = sorted(list(set(all_discovered) | historical_cnt))

if all_discovered:
    new_ex = st.sidebar.multiselect(
        "Escludi Nazioni:",
        options=all_discovered,
        default=[c for c in st.session_state.config.get("excluded", []) if c in all_discovered]
    )
    if st.sidebar.button("💾 SALVA CONFIG"):
        st.session_state.config["excluded"] = new_ex
        save_config()
        st.rerun()

if last_snap_ts:
    st.sidebar.success(f"✅ SNAPSHOT TEST: {last_snap_ts}")
else:
    st.sidebar.warning("⚠️ SNAPSHOT TEST ASSENTE")

st.sidebar.markdown("---")
st.sidebar.caption(f"DB TEST: {Path(DB_FILE).name}")
st.sidebar.caption(f"SNAP TEST: {Path(SNAP_FILE).name}")
st.sidebar.caption(f"DETAILS TEST: {Path(DETAILS_FILE).name}")

# ==========================================
# UI MAIN
# ==========================================
c1, c2 = st.columns(2)
if c1.button("📌 SNAP + SCAN"):
    run_full_scan(snap=True)
if c2.button("🚀 SCAN VELOCE"):
    run_full_scan(snap=False)

if st.session_state.scan_results:
    df = pd.DataFrame(st.session_state.scan_results)
    full_view = df[df["Data"] == target_dates[HORIZON - 1]]

    if not full_view.empty:
        view = full_view.drop(columns=["Data", "Fixture_ID"])

        st.markdown("""
            <style>
                .main-container { width: 100%; max-height: 800px; overflow: auto; border: 1px solid #444; border-radius: 8px; background-color: #0e1117; }
                .mobile-table { width: 100%; min-width: 1000px; border-collapse: separate; border-spacing: 0; font-family: sans-serif; font-size: 11px; }
                .mobile-table th { position: sticky; top: 0; background: #1a1c23; color: #00e5ff; z-index: 10; padding: 12px 5px; border-bottom: 2px solid #333; border-right: 1px solid #333; }
                .mobile-table td { padding: 8px 5px; border-bottom: 1px solid #333; border-right: 1px solid #333; text-align: center; white-space: nowrap; }
                .row-gold { background-color: #FFD700 !important; color: black !important; font-weight: bold; }
                .row-boost { background-color: #006400 !important; color: white !important; font-weight: bold; }
                .row-over { background-color: #90EE90 !important; color: black !important; font-weight: bold; }
                .row-std { background-color: #FFFFFF !important; color: #000000 !important; }
            </style>
        """, unsafe_allow_html=True)

        def get_row_class(info):
            if "GOLD" in info:
                return "row-gold"
            if "BOOST" in info:
                return "row-boost"
            if "OVER" in info:
                return "row-over"
            return "row-std"

        html = '<div class="main-container"><table class="mobile-table"><thead><tr>'
        html += ''.join(f'<th>{c}</th>' for c in view.columns)
        html += '</tr></thead><tbody>'

        for _, row in view.iterrows():
            cls = get_row_class(row["Info"])
            html += f'<tr class="{cls}">' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>'

        html += '</tbody></table></div>'
        st.markdown(html, unsafe_allow_html=True)

        st.markdown("---")
        d1, d2, d3 = st.columns(3)
        d1.download_button(
            "💾 CSV",
            full_view.to_csv(index=False).encode("utf-8"),
            f"arab_test_{target_dates[HORIZON - 1]}.csv"
        )
        d2.download_button(
            "🌐 HTML",
            html.encode("utf-8"),
            f"arab_test_{target_dates[HORIZON - 1]}.html"
        )
        d3.download_button(
            "🧠 DETAILS JSON",
            json.dumps(
                {
                    k: v for k, v in st.session_state.match_details.items()
                    if v.get("date") == target_dates[HORIZON - 1]
                },
                indent=4,
                ensure_ascii=False
            ).encode("utf-8"),
            f"match_details_test_{target_dates[HORIZON - 1]}.json"
        )

        st.markdown("---")
        st.subheader("🔎 Dettagli partite analizzate")

        fixture_options = []
        for _, row in full_view.iterrows():
            fid = str(row["Fixture_ID"])
            fixture_options.append((fid, f"{row['Ora']} | {row['Match']} | {row['Lega']}"))

        if fixture_options:
            labels = {label: fid for fid, label in fixture_options}
            selected_label = st.selectbox("Seleziona una partita:", list(labels.keys()))
            selected_fid = labels[selected_label]
            detail = st.session_state.match_details.get(selected_fid)

            if detail:
                a1, a2, a3 = st.columns(3)
                a1.metric("Quota O2.5", f"{detail['markets']['o25']:.2f}")
                a2.metric("Quota O0.5 HT", f"{detail['markets']['o05ht']:.2f}")
                a3.metric("Quota O1.5 HT", f"{detail['markets']['o15ht']:.2f}")

                st.write(f"**Match:** {detail['match']}")
                st.write(f"**Tag:** {' '.join(detail['tags'])}")
                st.write(
                    f"**Medie HT:** {detail['averages']['home_avg_ht']:.2f} | {detail['averages']['away_avg_ht']:.2f}"
                )
                st.write(
                    f"**Medie FT:** {detail['averages']['home_avg_ft']:.2f} | {detail['averages']['away_avg_ft']:.2f}"
                )

                c_home, c_away = st.columns(2)

                with c_home:
                    st.markdown(f"### 🏠 Ultime 8 {detail['home_team']}")
                    df_home = pd.DataFrame(detail["home_last_8"])
                    if not df_home.empty:
                        st.dataframe(df_home, use_container_width=True, hide_index=True)

                with c_away:
                    st.markdown(f"### ✈️ Ultime 8 {detail['away_team']}")
                    df_away = pd.DataFrame(detail["away_last_8"])
                    if not df_away.empty:
                        st.dataframe(df_away, use_container_width=True, hide_index=True)
else:
    st.info("Esegui uno scan.")

# ==========================================
# LOGICA PER ESECUZIONE AUTOMATICA
# ==========================================
if __name__ == "__main__":
    if "--auto" in sys.argv:
        HORIZON = 1
        print("🚀 Avvio Scan Automatico TEST (SNAP + SCAN)...")
        run_full_scan(snap=True)
        print("✅ Scan TEST completo terminato.")
    elif "--fast" in sys.argv:
        HORIZON = 1
        print("⚡ Avvio Scan Veloce Automatico TEST...")
        run_full_scan(snap=False)
        print("✅ Scan veloce TEST terminato.")
