import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def run_cmd(cmd, label, fatal=True):
    """
    Esegue un comando, stampa stdout/stderr in tempo reale e restituisce l'exit code.
    Se fatal=True e il comando fallisce, il chiamante può decidere di uscire.
    """
    print(f"\n▶ Eseguo: {' '.join(cmd)}")
    print(f"📌 Step: {label}")

    process = subprocess.Popen(
        cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )

    try:
        if process.stdout is not None:
            for line in process.stdout:
                print(line.rstrip())
    finally:
        process.wait()

    code = process.returncode

    if code == 0:
        print(f"✅ Step completato: {label}")
    else:
        print(f"❌ Step fallito: {label} (exit code {code})")

    return code


def main():
    print("🚀 Avvio night scan guard...")
    print(f"📂 Working dir: {BASE_DIR}")

    python_exec = sys.executable

    main_code = 0

    # ==========================================
    # 1) SCAN PRINCIPALE - BLOCCANTE
    # ==========================================
    print("\n🌙 Avvio scan notturno principale...")
    main_code = run_cmd(
        [python_exec, "3appDays.py", "--auto"],
        "night multiday scan",
        fatal=True
    )

    if main_code != 0:
        print("\n🛑 Lo scan principale è fallito.")
        print("❌ Workflow segnato come FALLITO.")
        sys.exit(main_code)

    # ==========================================
    # 2) BUILD CASSE RECENTI - NON BLOCCANTE
    # ==========================================
    print("\n📦 Tentativo aggiornamento casse recenti...")
    try:
        casse_code = run_cmd(
            [python_exec, "build_casse_recenti.py"],
            "aggiornamento casse recenti",
            fatal=False
        )

        if casse_code != 0:
            print(
                f"⚠️ build_casse_recenti.py fallito con codice {casse_code}, "
                "ma il night scan principale è valido e il workflow resta verde."
            )
        else:
            print("✅ Casse recenti aggiornate correttamente.")

    except Exception as e:
        print(
            f"⚠️ Eccezione durante build_casse_recenti.py: {e}\n"
            "Il night scan principale resta comunque valido."
        )

    # ==========================================
    # 3) USCITA FINALE
    # ==========================================
    print("\n✅ Night scan completato.")
    sys.exit(0)


if __name__ == "__main__":
    main()
