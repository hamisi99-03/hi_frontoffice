"""
MEATMAGIC — packaged entry point for PyInstaller builds.
Handles first-run database setup, then launches the desktop app.
"""
import ctypes
import os
import secrets
import sys
from pathlib import Path

_MUTEX_NAME = "MeatMagic_SingleInstance"
_single_instance_handle = None


def _ensure_single_instance():
    """Prevent a second copy of MEATMAGIC from starting on this machine."""
    global _single_instance_handle
    if sys.platform != "win32":
        return
    kernel32 = ctypes.windll.kernel32
    _single_instance_handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS -> already running
        if _single_instance_handle:
            kernel32.CloseHandle(_single_instance_handle)
            _single_instance_handle = None
        ctypes.windll.user32.MessageBoxW(
            0,
            "MEATMAGIC is already running on this computer.\n\n"
            "Use the MEATMAGIC window that is already open instead.",
            "Meat Magic Enterprises LTD",
            0x40,  # MB_ICONINFORMATION
        )
        sys.exit(0)


_ensure_single_instance()

if getattr(sys, 'frozen', False):
    exe_dir = Path(sys.executable).resolve().parent
    os.chdir(exe_dir)
    db_path = (exe_dir / 'db.sqlite3').resolve()
else:
    db_path = Path("db.sqlite3").resolve()

os.environ["MEATMAGIC_DB"] = str(db_path)

key_path = db_path.with_name("meatmagic.key")
if key_path.exists():
    os.environ["MEATMAGIC_SECRET"] = key_path.read_text().strip()
else:
    new_key = secrets.token_urlsafe(50)
    key_path.write_text(new_key)
    os.environ["MEATMAGIC_SECRET"] = new_key

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "frontoffice.settings")

import django
django.setup()

from django.core.management import call_command
from django.contrib.auth import get_user_model

# ── auto-migrate (always run — idempotent) ───────────────────────────────
first_run = not db_path.exists()

if first_run:
    print("=" * 55)
    print("  First run — setting up database...")
    print(f"  Location : {db_path}")
    print("=" * 55)

call_command("migrate", interactive=False, verbosity=1)

if first_run:
    call_command("seed_items", verbosity=1)

    User = get_user_model()
    if not User.objects.filter(is_superuser=True).exists():
        password = secrets.token_urlsafe(10)
        User.objects.create_superuser("admin", password=password)
        print()
        print("=" * 55)
        print("  ADMIN ACCOUNT CREATED")
        print("  Username : admin")
        print(f"  Password : {password}")
        print()
        print("  WRITE THIS DOWN. You will not see it again.")
        print("  Change it after first login via Django admin:")
        print("    http://127.0.0.1:8000/admin/")
        print("=" * 55)
        print()

# ── launch desktop window ────────────────────────────────────────────────
import threading
import socket

import webview

HOST = "0.0.0.0"
PORT = 8000


def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def run_server():
    from waitress import serve
    from frontoffice.wsgi import application
    serve(application, host=HOST, port=PORT, threads=10)


def main():
    threading.Thread(target=run_server, daemon=True).start()
    lan_ip = get_lan_ip()
    print(f"\n  Meat Magic Enterprises LTD is running.")
    print(f"  This computer     : http://127.0.0.1:{PORT}")
    print(f"  Other devices     : http://{lan_ip}:{PORT}\n")

    webview.create_window(
        "Meat Magic Enterprises LTD",
        f"http://127.0.0.1:{PORT}/",
        width=1200,
        height=800,
        min_size=(900, 600),
    )
    webview.start()


if __name__ == "__main__":
    main()
