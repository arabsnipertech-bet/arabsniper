import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
    ROME_TZ = ZoneInfo("Europe/Rome")
except Exception:
    ROME_TZ = None

BASE_DIR = Path(__file__).resolve().parent
DAY1_FILE = BASE_DIR / "data_day1.json"


def now_rome() -> datetime:
    return datetime.now(ROME_TZ) if ROME_TZ else datetime.now()


def get_today_str() -> str:
    return now_rome().strftime("%Y-%m-%d")


def extract_date_from_day1() -> str | None:
    if not DAY1_FILE.exists():
        return None

    try:
        with open(DAY1_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)

        if not isinstance(payload, list) or not payload:
            return None

        first = payload[0]
        if isinstance(first, dict):
            return str(first.get("Data") or "").strip() or None

        return None

    except Exception:
        return None


def should_run_auto() -> bool:
    today = get_today_str()
    day1_date = extract_date_from_day1()

    if day1_date is None:
        print("⚠️ data_day1.json mancante o non valido → fallback AUTO")
        return True

    if day1_date != today:
        print(f"⚠️ data_day1.json fermo a {day1_date}, oggi Roma è {today} → fallback AUTO")
        return True

    print(f"✅ data_day1.json già aggiornato a oggi ({today}, timezone Roma) → FAST normale")
    return False


def run_command(args: list[str]) -> int:
    print("▶ Eseguo:", " ".join(args))
    result = subprocess.run(args, cwd=str(BASE_DIR))
    return result.returncode


if __name__ == "__main__":
    python_exe = sys.executable or "python"

    if should_run_auto():
        code = run_command([python_exe, "3appDays.py", "--auto"])
    else:
        code = run_command([python_exe, "3appDays.py", "--fast"])

    sys.exit(code)
