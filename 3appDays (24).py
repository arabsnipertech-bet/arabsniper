import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import time
from pathlib import Path
from github import Github  # <--- Nuova libreria aggiunta

# ==========================================
# CONFIGURAZIONE ARAB SNIPER V22.04.24 - GITHUB AUTO-UPDATE
# ==========================================
BASE_DIR = Path(__file__).resolve().parent
DB_FILE = str(BASE_DIR / "arab_sniper_database.json")
SNAP_FILE = str(BASE_DIR / "arab_snapshot_database.json")
CONFIG_FILE = str(BASE_DIR / "nazioni_config.json")

DEFAULT_EXCLUDED = ["Thailand", "Indonesia", "India", "Kenya", "Morocco", "Rwanda", "Nigeria", "Oman", "Algeria", "UAE"]

try:
    from zoneinfo import ZoneInfo
    ROME_TZ = ZoneInfo("Europe/Rome")
except Exception:
    ROME_TZ = None

def now_rome():
    return datetime.now(ROME_TZ) if ROME_TZ else datetime.now()

# --- FUNZIONE CARICAMENTO AUTOMATICO SU GITHUB ---
def upload_to_github(results):
    """Estrae i segnali e aggiorna segnali.json sul repository GitHub"""
    try:
        # Recupera il token dalle Secrets di Streamlit (Configurato come GITHUB_TOKEN)
        token = st.secrets["GITHUB_TOKEN"]
        g = Github(token)
        repo = g.get_user().get_repo("arab-sniper-web")
        
        # Prepariamo i dati: 3 segnali OVER (Verde Chiaro) per la Home + Tutti per la Dashboard
        # Salviamo l'intero database dei risultati correnti per alimentare entrambe le pagine
        content = json.dumps(results, indent=4)
        file_path = "segnali.json"
        
        try:
            # Prova ad aggiornare il file esistente
            contents = repo.get_contents(file_path)
            repo.update_file(contents.path, "Update segnali via Arab Sniper Bot", content, contents.sha)
            st.sidebar.success("🚀 Sito arabsniperbet.com aggiornato!")
        except:
            # Se il file non esiste (primo avvio), lo crea
            repo.create_file(file_path, "Initial commit segnali", content)
            st.sidebar.info("📌 File segnali.json creato su GitHub")
            
    except Exception as e:
        st.sidebar.error(f"❌ Errore GitHub: {e}")

st.set_page_config(page_title="ARAB SNIPER V22.04.24", layout="wide")

# [ ... Resto del setup iniziale invariato ... ]
if "config" not in st.session_state:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f: st.session_state.config = json.load(f)
    else: st.session_state.config = {"excluded": DEFAULT_EXCLUDED}

if "team_stats_cache" not in st.session_state: st.session_state.team_stats_cache = {}
if "available_countries" not in st.session_state: st.session_state.available_countries = []
if "scan_results" not in st.session_state: st.session_state.scan_results = []
if "odds_memory" not in st.session_state: st.session_state.odds_memory = {}

def save_config():
    with open(CONFIG_FILE, "w") as f: json.dump(st.session_state.config, f)

def load_db():
    today = now_rome().strftime("%Y-%m-%d")
    ts = None
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r") as f:
                data = json.load(f).get("results", [])
                st.session_state.scan_results = [r for r in data if r.get("Data", "") >= today]
        except: pass
    return ts

load_db()

API_KEY = st.secrets.get("API_SPORTS_KEY")
HEADERS = {"x-apisports-key": API_KEY}

# [ ... Funzioni api_get, _contains_ht, extract_elite_markets, get_team_performance invariate ... ]
def api_get(session, path, params):
    for attempt in range(2): 
        try:
            r = session.get(f"https://v3.football.api-sports.io/{path}", headers=HEADERS, params=params, timeout=20)
            if r.status_code == 200: return r.json()
            time.sleep(1)
        except:
            if attempt == 1: return None
            time.sleep(1)
    return None

def _contains_ht(text):
    t = (text or "").lower()
    return any(k in t for k in ["1st half", "first half", "1h", "ht", "half time", "halftime", "1° tempo"])

def _contains_btts(text):
    t = (text or "").lower()
    return any(k in t for k in ["both teams", "btts", "gg", "to score", "gol/gol", "entrambe segnano"])

def _is_yes(text):
    t = (text or "").strip().lower()
    return t in ["yes", "si", "sì", "y", "1"]

def extract_elite_markets(session, fid):
    res = api_get(session, "odds", {"fixture": fid})
    if not res or not res.get("response"): return None
    mk = {"q1": 0.0, "qx": 0.0, "q2": 0.0, "o25": 0.0, "o05ht": 0.0, "gght": 0.0}
    for bm in res["response"][0].get("bookmakers", []):
        for b in bm.get("bets", []):
            name = (b.get("name") or "").lower()
            bid = b.get("id")
            if bid == 1 and mk["q1"] == 0:
                for v in b.get("values", []):
                    vl = v["value"].lower()
                    if "home" in vl: mk["q1"] = float(v["odd"])
                    elif "draw" in vl: mk["qx"] = float(v["odd"])
                    elif "away" in vl: mk["q2"] = float(v["odd"])
            if bid == 5 and mk["o25"] == 0:
                if any(j in name for j in ["corner", "card", "booking"]): continue
                for v in b.get("values", []):
                    if "over 2.5" in v["value"].lower(): mk["o25"] = float(v["odd"])
            if mk["o05ht"] == 0 and _contains_ht(name) and any(k in name for k in ["total", "over/under", "ou", "goals"]):
                if "team" in name: continue
                for v in b.get("values", []):
                    if "over 0.5" in v["value"].lower(): mk["o05ht"] = float(v["odd"])
            if mk["gght"] == 0 and _contains_btts(name):
                is_name_ht = _contains_ht(name)
                for v in b.get("values", []):
                    val_txt = v["value"].lower()
                    if _is_yes(val_txt) and (is_name_ht or _contains_ht(val_txt) or bid in [40, 71]):
                        mk["gght"] = float(v["odd"])
                        break
        if mk["q1"] > 0 and mk["o25"] > 0 and (mk["o05ht"] > 0 or mk["gght"] > 0): break
    if (1.01 <= mk["q1"] <= 1.10) or (1.01 <= mk["q2"] <= 1.10) or (1.01 <= mk["o25"] <= 1.30): return "SKIP"
    return mk

def get_team_performance(session, tid):
    if str(tid) in st.session_state.team_stats_cache: return st.session_state.team_stats_cache[str(tid)]
    res = api_get(session, "fixtures", {"team": tid, "last": 8, "status": "FT"})
    fx = res.get("response", []) if res else []
    if not fx: return None
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

    stats = {"avg_ht": tht/act, "avg_total": (gf+gs)/act, "last_2h_zero": last_2h_zero}
    st.session_state.team_stats_cache[str(tid)] = stats
    return stats

def run_full_scan(snap=False):
    target_dates = [(now_rome().date() + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]
    with st.spinner("🚀 Arab Sniper: Analisi mercati V22.04.24..."):
        with requests.Session() as s:
            target_date = target_dates[HORIZON - 1]
            res = api_get(s, "fixtures", {"date": target_date, "timezone": "Europe/Rome"})
            if not res: return
            day_fx = [f for f in res.get("response", []) if f["fixture"]["status"]["short"] == "NS"]
            
            final_list = []
            pb = st.progress(0, text="🚀 SCANSIONE PARTITE E ANALISI...")
            for i, f in enumerate(day_fx):
                pb.progress((i+1)/len(day_fx))
                cnt = f["league"]["country"]
                if cnt in st.session_state.config["excluded"]: continue
                fid = str(f["fixture"]["id"])
                mk = extract_elite_markets(s, fid)
                if not mk or mk == "SKIP" or mk["q1"] == 0: continue
                s_h, s_a = get_team_performance(s, f["teams"]["home"]["id"]), get_team_performance(s, f["teams"]["away"]["id"])
                if not s_h or not s_a: continue

                combined_ht_avg = (s_h["avg_ht"] + s_a["avg_ht"]) / 2
                if combined_ht_avg < 1.05: continue

                fav = min(mk["q1"], mk["q2"])
                is_gold_zone = (1.40 <= fav <= 1.90)
                tags = ["M-Ok"]
                
                h_p, h_o, h_g = False, False, False
                if (fav < 1.75) and (s_h["avg_total"] >= 1.0 and s_a["avg_total"] >= 1.0): tags.append("🐟O"); h_p = True
                
                cond_ft_155 = (s_h["avg_total"] >= 1.55 and s_a["avg_total"] >= 1.55)
                cond_q_o25 = (1.51 <= mk["o25"] <= 2.37)
                cond_q_o05h = (1.21 <= mk["o05ht"] <= 1.40)
                
                if cond_ft_155 and cond_q_o25 and cond_q_o05h:
                    if (s_h["avg_ht"] >= 1.27 or s_a["avg_ht"] >= 1.27) and (s_h["avg_total"] > 1.85 or s_a["avg_total"] > 1.85): 
                        tags.append("🚀 BOOST"); h_o = True
                    else: 
                        tags.append("⚽ OVER"); h_o = True
                
                if (s_h["avg_ht"] >= 1.1 and s_a["avg_ht"] >= 1.1) and (1.20 <= mk["o05ht"] <= 1.40) and (s_h["last_2h_zero"] or s_a["last_2h_zero"]):
                    tags.append("🎯PT"); h_g = True
                
                if h_p and h_o and h_g: tags.insert(0, "⚽⭐ GOLD")

                final_list.append({
                    "Ora": f["fixture"]["date"][11:16],
                    "Lega": f"{f['league']['name']} ({cnt})",
                    "Match": f"{f['teams']['home']['name']} - {f['teams']['away']['name']}",
                    "FAV": "✅" if is_gold_zone else "❌",
                    "1X2": f"{mk['q1']:.1f}|{mk['qx']:.1f}|{mk['q2']:.1f}",
                    "O2.5": f"{mk['o25']:.2f}", "O0.5H": f"{mk['o05ht']:.2f}", "GGH": f"{mk['gght']:.2f}",
                    "AVG FT": f"{s_h['avg_total']:.1f}|{s_a['avg_total']:.1f}",
                    "AVG HT": f"{s_h['avg_ht']:.1f}|{s_a['avg_ht']:.1f}",
                    "Info": " ".join(tags), "Data": f["fixture"]["date"][:10],
                    "Fixture_ID": f["fixture"]["id"]
                })
                time.sleep(0.1)

            # --- SALVATAGGIO DB LOCALE + CARICAMENTO SU GITHUB ---
            current_db = {str(r["Fixture_ID"]): r for r in st.session_state.scan_results}
            for r in final_list: current_db[str(r["Fixture_ID"])] = r
            st.session_state.scan_results = list(current_db.values())
            
            with open(DB_FILE, "w") as f: json.dump({"results": st.session_state.scan_results}, f)
            
            # Attiviamo l'aggiornamento del sito web
            upload_to_github(st.session_state.scan_results)
            st.rerun()

st.sidebar.header("👑 Arab Sniper V22.04.24")
HORIZON = st.sidebar.selectbox("Orizzonte Temporale:", options=[1, 2, 3], index=0)
target_dates = [(now_rome().date() + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]

c1, c2 = st.columns(2)
if c1.button("🚀 SCAN COMPLETO"): run_full_scan(snap=False)

if st.session_state.scan_results:
    df = pd.DataFrame(st.session_state.scan_results)
    full_view = df[df["Data"] == target_dates[HORIZON - 1]]
    if not full_view.empty:
        view = full_view.drop(columns=["Data", "Fixture_ID"])
        st.table(view)
