import multiprocessing
import threading
import time
import webbrowser

import uvicorn
from app import app


__author__ = "BeastOfSyn"
__version__ = "12.3"


def open_browser():
    time.sleep(1.2)
    webbrowser.open("http://127.0.0.1:8000")


def main():
    multiprocessing.freeze_support()
    print("=" * 72)
    print("       Configuration Comparison Tool v12.3")
    print("       Author: BeastOfSyn")
    print("=" * 72)
    print(" Local server: http://127.0.0.1:8000")
    print(" Browser will open automatically.")
    print(" Keep this console open while the application is running.")
    print(" Close this window to exit.")
    print("=" * 72)
    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
