import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

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
}

DETAILS_FILES = {
    1: BASE_DIR / "details_day1.json",
    2: BASE_DIR / "details_day2.json",
    3: BASE_DIR / "details_day3.json",
}


def now_rome() -> datetime:
    return datetime.now(ROME_TZ) if ROME_TZ else datetime.now()


def expected_dates() -> dict[int, str]:
    base = now_rome().date()
    return {
        1: base.strftime("%Y-%m-%d"),
        2: (base + timedelta(days=1)).strftime("%Y-%m-%d"),
        3: (base + timedelta(days=2)).strftime("%Y-%m-%d"),
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

    sys.exit(code)
