import subprocess
import time
import sys

MAX_RETRY = 2

def run_scan():
    try:
        print("🚀 Avvio Night Scan...")
        result = subprocess.run(
            ["python", "3appDays.py", "--snap"],
            capture_output=True,
            text=True
        )

        print(result.stdout)
        print(result.stderr)

        if result.returncode != 0:
            print("❌ Errore durante lo scan")
            return False

        print("✅ Night Scan completato")
        return True

    except Exception as e:
        print(f"❌ Eccezione: {e}")
        return False


def main():
    attempt = 0

    while attempt <= MAX_RETRY:
        success = run_scan()

        if success:
            print("🏁 Fine processo")
            sys.exit(0)

        attempt += 1
        print(f"🔁 Retry {attempt}/{MAX_RETRY} tra 30 secondi...")
        time.sleep(30)

    print("💥 Scan fallito definitivamente")
    sys.exit(1)


if __name__ == "__main__":
    main()
