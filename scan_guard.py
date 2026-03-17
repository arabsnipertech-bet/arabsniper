import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from league_rules import is_hard_excluded_league, is_minor_risk_league

try:
    from zoneinfo import ZoneInfo
    ROME_TZ = ZoneInfo("Europe/Rome")
except Exception:
    ROME_TZ = None

BASE_DIR = Path(__file__).resolve().parent

DAY_FILES = {
    1: BASE_DIR / "data_day1.json",
    2: BASE_DIR / "data_day2.json",
    3: BASE_DIR / "data_day3.json",
    4: BASE_DIR / "data_day4.json",
    5: BASE_DIR / "data_day5.json",
}

DETAILS_FILES = {
    1: BASE_DIR / "details_day1.json",
    2: BASE_DIR / "details_day2.json",
    3: BASE_DIR / "details_day3.json",
    4: BASE_DIR / "details_day4.json",
    5: BASE_DIR / "details_day5.json",
}


def now_rome() -> datetime:
    return datetime.now(ROME_TZ) if ROME_TZ else datetime.now()


def expected_dates() -> dict[int, str]:
    base = now_rome().date()
    return {
        1: base.strftime("%Y-%m-%d"),
        2: (base + timedelta(days=1)).strftime("%Y-%m-%d"),
        3: (base + timedelta(days=2)).strftime("%Y-%m-%d"),
        4: (base + timedelta(days=3)).strftime("%Y-%m-%d"),
        5: (base + timedelta(days=4)).strftime("%Y-%m-%d"),
    }


def read_json_file(path: Path):
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def extract_day_date_from_data_file(path: Path) -> str | None:
    payload = read_json_file(path)
    if not isinstance(payload, list) or not payload:
        return None

    first = payload[0]
    if not isinstance(first, dict):
        return None

    value = str(first.get("Data") or "").strip()
    return value or None


def extract_day_date_from_details_file(path: Path) -> str | None:
    payload = read_json_file(path)
    if not isinstance(payload, dict):
        return None

    value = str(payload.get("date") or "").strip()
    if value:
        return value

    details = payload.get("details")
    if not isinstance(details, dict) or not details:
        return None

    for _, item in details.items():
        if isinstance(item, dict):
            value = str(item.get("date") or "").strip()
            if value:
                return value

    return None


def validate_data_files() -> list[str]:
    issues = []
    exp = expected_dates()

    for day_num, path in DAY_FILES.items():
        actual = extract_day_date_from_data_file(path)
        if actual is None:
            issues.append(f"{path.name} mancante o non valido")
            continue

        if actual != exp[day_num]:
            issues.append(
                f"{path.name} data incoerente: trovato {actual}, atteso {exp[day_num]}"
            )

    return issues


def validate_details_files() -> list[str]:
    issues = []
    exp = expected_dates()

    for day_num, path in DETAILS_FILES.items():
        actual = extract_day_date_from_details_file(path)
        if actual is None:
            issues.append(f"{path.name} mancante, vuoto o non valido")
            continue

        if actual != exp[day_num]:
            issues.append(
                f"{path.name} data incoerente: trovato {actual}, atteso {exp[day_num]}"
            )

    return issues


def parse_float(value) -> float:
    try:
        return float(str(value).replace(",", ".").strip())
    except Exception:
        return 0.0


def count_signal_rows(rows: list[dict]) -> int:
    count = 0
    for row in rows:
        info = str(row.get("Info") or "").upper()
        if any(tag in info for tag in ("GOLD", "BOOST", "OVER", "PT")):
            count += 1
    return count


def analyze_day_dataset(day_num: int):
    path = DAY_FILES[day_num]
    payload = read_json_file(path)

    if not isinstance(payload, list):
        print(f"📉 DAY{day_num}: dataset non leggibile")
        return

    total = len(payload)
    excluded = 0
    minor = 0
    incomplete_markets = 0

    for row in payload:
        league = str(row.get("Lega") or "")
        q_o25 = parse_float(row.get("O2.5"))
        q_o05h = parse_float(row.get("O0.5H"))
        q_o15h = parse_float(row.get("O1.5H"))

        if is_hard_excluded_league(league):
            excluded += 1

        if is_minor_risk_league(league):
            minor += 1

        if q_o25 <= 0 or q_o05h <= 0 or q_o15h <= 0:
            incomplete_markets += 1

    signals = count_signal_rows(payload)

    good_rows = total - excluded - incomplete_markets
    if total == 0:
        status = "VUOTO"
    elif good_rows <= 3:
        status = "DEBOLE"
    elif good_rows <= 10:
        status = "MEDIO"
    else:
        status = "BUONO"

    print("")
    print(f"📊 DAY{day_num} QUALITY REPORT")
    print(f" - match totali: {total}")
    print(f" - femminili/amichevoli/youth/reserve: {excluded}")
    print(f" - campionati minori sospetti: {minor}")
    print(f" - mercati incompleti o nulli: {incomplete_markets}")
    print(f" - righe con segnali utili: {signals}")
    print(f" - giudizio dataset: {status}")


def quality_report():
    print("")
    print("🧪 POST-SCAN QUALITY CHECK")
    for day_num in (1, 2, 3, 4, 5):
        analyze_day_dataset(day_num)
    print("")


def should_run_auto() -> bool:
    print(f"🕒 Ora Roma: {now_rome().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🔎 Controllo integrità file giorno...")

    issues = []
    issues.extend(validate_data_files())
    issues.extend(validate_details_files())

    if issues:
        print("⚠️ Rilevate incoerenze. Eseguo AUTO completo.")
        for issue in issues:
            print(f" - {issue}")
        return True

    exp = expected_dates()
    print("✅ Tutti i file giorno sono coerenti:")
    print(f" - Day1 = {exp[1]}")
    print(f" - Day2 = {exp[2]}")
    print(f" - Day3 = {exp[3]}")
    print(f" - Day4 = {exp[4]}")
    print(f" - Day5 = {exp[5]}")
    print("➡️ Posso eseguire FAST su Day1.")
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

    quality_report()

    print("📦 Tentativo aggiornamento casse recenti...")
    try:
        casse_code = run_command([python_exe, "build_casse_recenti.py"])
        if casse_code != 0:
            print(f"⚠️ build_casse_recenti.py ha restituito codice {casse_code}, ma non blocco il night scan.")
    except Exception as e:
        print(f"⚠️ Errore build_casse_recenti.py ignorato: {e}")

    sys.exit(code)
