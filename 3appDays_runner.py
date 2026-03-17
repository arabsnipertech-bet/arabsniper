import sys
import types
import importlib.util
import subprocess
import shutil
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent
APP_PATH = BASE_DIR / "3appDays.py"
ARCHIVE_DIR = BASE_DIR / "archives"


# =========================
# FAKE STREAMLIT
# =========================
class SessionState(dict):
    def __getattr__(self, name):
        return self.get(name)

    def __setattr__(self, name, value):
        self[name] = value


class DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def progress(self, *args, **kwargs):
        return self

    def empty(self):
        return None

    def write(self, *args, **kwargs):
        return None

    def markdown(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def success(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def button(self, *args, **kwargs):
        return False

    def download_button(self, *args, **kwargs):
        return False

    def subheader(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def header(self, *args, **kwargs):
        return None

    def selectbox(self, label, options=None, index=0, **kwargs):
        if options is None:
            return None
        if len(options) == 0:
            return None
        return options[index] if len(options) > index else options[0]

    def multiselect(self, label, options=None, default=None, **kwargs):
        return default or []


class FakeSidebar(DummyContext):
    pass


class FakeSecrets(dict):
    def get(self, key, default=None):
        return super().get(key, default)


class FakeStreamlitModule(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.session_state = SessionState()
        self.sidebar = FakeSidebar()
        self.secrets = FakeSecrets()

    def set_page_config(self, *args, **kwargs):
        return None

    def spinner(self, *args, **kwargs):
        return DummyContext()

    def progress(self, *args, **kwargs):
        return DummyContext()

    def columns(self, spec, **kwargs):
        if isinstance(spec, int):
            n = spec
        else:
            n = len(spec)
        return [DummyContext() for _ in range(n)]

    def button(self, *args, **kwargs):
        return False

    def markdown(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def success(self, *args, **kwargs):
        return None

    def warning(self, *args, **kwargs):
        return None

    def error(self, *args, **kwargs):
        return None

    def subheader(self, *args, **kwargs):
        return None

    def write(self, *args, **kwargs):
        return None

    def rerun(self):
        return None

    def download_button(self, *args, **kwargs):
        return False

    def dialog(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator


# Finto modulo streamlit PRIMA dell'import della web app
fake_st = FakeStreamlitModule()
sys.modules["streamlit"] = fake_st


# =========================
# IMPORT DINAMICO DI 3appDays.py
# =========================
spec = importlib.util.spec_from_file_location("app3days_module", APP_PATH)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


# =========================
# HELPERS
# =========================
LIVE_FILES = [
    "data.json",
    "data_day1.json",
    "data_day2.json",
    "data_day3.json",
    "data_day4.json",
    "data_day5.json",
    "details_day1.json",
    "details_day2.json",
    "details_day3.json",
    "details_day4.json",
    "details_day5.json",
    "quote_history.json",
]


def archive_live_files():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = ARCHIVE_DIR / ts
    target.mkdir(parents=True, exist_ok=True)

    copied = 0
    for name in LIVE_FILES:
        src = BASE_DIR / name
        if src.exists():
            shutil.copy2(src, target / name)
            copied += 1

    print(f"📦 Backup creato in: {target}", flush=True)
    print(f"📦 File copiati: {copied}", flush=True)


def run_quote_history(days, label):
    args = [
        sys.executable,
        "-u",
        str(BASE_DIR / "quote_history_updater.py"),
        "--days",
        ",".join(str(d) for d in days),
        "--label",
        label,
    ]
    print("🧠 Aggiorno quote_history:", " ".join(args), flush=True)
    result = subprocess.run(args, cwd=str(BASE_DIR))
    if result.returncode != 0:
        print("⚠️ Aggiornamento quote_history terminato con errore.", flush=True)
    return result.returncode


def run_night():
    print("🌙 RUNNER: backup file live prima del night scan...", flush=True)
    archive_live_files()

    print("🌙 RUNNER: avvio build multi-day notturna...", flush=True)
    app.HORIZON = 1
    app.run_nightly_multiday_build()
    print("✅ RUNNER: build multi-day completata.", flush=True)

    run_quote_history([1, 2, 3, 4, 5], "night")
    return 0


def run_fast_day1():
    print("⚡ RUNNER: avvio refresh Day1...", flush=True)
    app.HORIZON = 1
    app.run_full_scan(horizon=1, snap=False, update_main_site=True, show_success=False)
    print("✅ RUNNER: refresh Day1 completato.", flush=True)

    run_quote_history([1], "fast_day1")
    return 0


def run_day2_refresh():
    print("🌆 RUNNER: avvio refresh Day2...", flush=True)
    app.HORIZON = 2
    app.run_full_scan(horizon=2, snap=False, update_main_site=False, show_success=False)
    print("✅ RUNNER: refresh Day2 completato.", flush=True)

    run_quote_history([2], "refresh_day2")
    return 0


def main():
    args = sys.argv[1:]

    if "--night" in args:
        return run_night()

    if "--fast-day1" in args:
        return run_fast_day1()

    if "--refresh-day2" in args:
        return run_day2_refresh()

    print("❌ Argomento non valido. Usa: --night | --fast-day1 | --refresh-day2", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
