# How To Use & AI-Fix Workflow

## What this is
DEV/PROD Excel config comparison tool — PMR, Alert Rule, Process, Translator
Actions, Translators, CIS Job, BRE, RRD, and more. Upload a DEV export and a
PROD export for a module, get a field-by-field diff plus a Data Quality
Inspector for corrupted/Excel-mangled values.

## Basic usage
Run from source:
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```
Or run the prebuilt standalone: `dist\Configuration_Comparison_Tool.exe`
(no Python needed). Either way, open the URL it prints and upload a DEV +
PROD `.xlsx` pair for a module.

## AI-assisted fix workflow (how the last round of fixes was done)
1. **Prompt + harvest** — give the AI the actual project zip and let it
   unzip and read the real source itself, not a description of it.
2. **Modify in place** — hand it the specific file(s) to change and have it
   edit them directly, so unrelated code doesn't drift or get rewritten.
3. **Verify against real data, not guesses** — no GUI browser is available
   in a sandboxed agent environment, so:
   - Run the real backend (`engine.py` / `compare_files`) against the real
     files in `test_data/`.
   - Feed that real output through the real frontend code in a headless DOM
     (e.g. `jsdom`) and inspect the actual rendered elements.
   - Start the real server (`uvicorn app:app`) and run the project's own
     test suite (`test_comprehensive.py`) against it.
   - If a real browser is ever available, also do a visual/pixel check —
     DOM-correctness is not the same as "looks right on screen."
4. **Caveman mode** — once the AI has the codebase loaded, keep prompts and
   replies short. Don't re-explain context every turn. Keeps token cost down
   across a long fix → verify → re-fix loop.

## Building the EXE
1. Run `build.bat` (Windows only). It auto-detects a Python install, builds
   its own isolated `.buildenv` virtualenv, installs `requirements.txt` +
   PyInstaller, runs `validate_build.py` as an integrity check, then builds
   `dist\Configuration_Comparison_Tool.exe`.
2. **If `build.bat` fails because no Python is installed on the machine at
   all** (not just a missing venv):
   - Open the project folder in Antigravity (or similar AI coding IDE).
   - Ask it to set up a Python environment: install Python if missing, then
     `python -m venv .venv`, activate, `pip install -r requirements.txt
     pyinstaller`.
   - Ask it to build the exe — either re-run `build.bat` once Python is on
     PATH, or run PyInstaller directly:
     `python -m PyInstaller --clean --noconfirm PMR_Comparison.spec`
   - Ask it to check and verify the result: launch the built exe, confirm
     it starts a server, hit `/api/health`, and run one real DEV/PROD
     comparison through the UI before trusting the build.

## Notes
- `test_comprehensive.py` expects a server already running at
  `http://127.0.0.1:8010` (see `BASE_URL` in that file) — start it with
  `python -m uvicorn app:app --host 127.0.0.1 --port 8010` first if running
  the test manually outside `build.bat`.
- `test_exe_endpoints.py` launches and tests the built `.exe` directly —
  Windows only, won't run in a Linux sandbox.
