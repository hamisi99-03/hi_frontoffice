"""
Launches MEATMAGIC as a standalone desktop window.

Double-click this (or run `python run_desktop.py`) instead of using
`manage.py runserver` + a browser tab. It starts the Django server quietly
in the background and opens it in its own app window using pywebview.

Other computers on the same shop network can still reach it in a normal
browser at http://<this-computer's-LAN-IP>:8000 while this is running.
"""
import os
import socket
import threading

import webview

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "frontoffice.settings")

HOST = "0.0.0.0"   # listen on the LAN too, not just this machine
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
    import django
    django.setup()
    from waitress import serve
    from frontoffice.wsgi import application
    serve(application, host=HOST, port=PORT, threads=10)


def main():
    threading.Thread(target=run_server, daemon=True).start()
    lan_ip = get_lan_ip()
    print(f"\nMeat Magic Enterprises LTD is running.")
    print(f"  This computer : http://127.0.0.1:{PORT}")
    print(f"  Other devices on the same shop WiFi/network: http://{lan_ip}:{PORT}\n")

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
