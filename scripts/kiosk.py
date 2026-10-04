"""Open the plant UI full-screen so it starts with no tap: sound and the microphone work at once.

    python -m scripts.kiosk                      # http://127.0.0.1:5173, full screen
    python -m scripts.kiosk --window             # same, in a normal window
    python -m scripts.kiosk --url http://127.0.0.1:5174

Browsers normally keep sound and the microphone off until someone taps the page. This starts
Edge or Chrome with a separate profile where autoplay is allowed and the microphone prompt is
accepted automatically, so the plant can talk right away and the touch sensor or "Hi <name>"
can start a chat. Use it only on the demo laptop. Press Alt+F4 to leave full screen mode.
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
PROFILE = Path(__file__).resolve().parent.parent / ".kiosk-profile"


def find_browser() -> str | None:
    for name in ("msedge", "google-chrome", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return next((path for path in CANDIDATES if os.path.exists(path)), None)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default="http://127.0.0.1:5173")
    parser.add_argument("--window", action="store_true", help="a normal window instead of full screen")
    args = parser.parse_args()
    browser = find_browser()
    if not browser:
        sys.exit("Couldn't find Edge or Chrome. Open the URL in a browser and tap once instead.")
    flags = [
        f"--user-data-dir={PROFILE}",
        "--autoplay-policy=no-user-gesture-required",
        "--use-fake-ui-for-media-stream",
        "--no-first-run",
        "--disable-features=Translate",
    ]
    flags += [f"--app={args.url}", "--start-maximized"] if args.window else ["--kiosk", args.url]
    subprocess.Popen([browser, *flags])
    print(f"Opened {args.url} in {Path(browser).stem}.")


if __name__ == "__main__":
    main()
