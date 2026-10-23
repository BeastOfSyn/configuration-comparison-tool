# Configuration Comparison Tool v12.3

**Author:** [BeastOfSyn](https://github.com/BeastOfSyn) &nbsp;|&nbsp; **License:** MIT

A deterministic, AST-aware DEV/PROD configuration diff engine with a
self-contained FastAPI backend and a keyboard-driven single-page web UI.
Upload two Excel exports of the same configuration module — one from your
DEV environment and one from PROD — and get a field-by-field semantic diff
in under a second.

---

## Why this exists

Standard diff tools (WinMerge, Git diff, Excel formulas) fail on enterprise
CRM configuration exports because:

- **XML attribute ordering** varies between database dumps → hundreds of false
  positives
- **Float coercion** — Excel converts `101` → `101.0`, `2024-01-01` →
  `2024-01-01 00:00:00.000`
- **Composite primary keys** — records are keyed by `(OwnerID, RuleID)`, not
  row numbers
- **Audit vs functional** — a LastModifiedOn timestamp change is *not* the same
  as a business-logic change

This tool handles all of the above.

---

## Features

| Feature | Detail |
|---|---|
| **AST-level XML diff** | Parses XML into element trees, sorts attributes and condition nodes canonically → zero false positives from attribute reordering |
| **Audit-only separation** | Records where only `LastModifiedBy`/`LastModifiedOn` changed are labelled `AUDIT-ONLY`, not `MODIFIED` |
| **Data Quality inspector** | Malformed XML, scientific-notation IDs, and truncated cell values are quarantined with plain-English diagnoses |
| **Composite key matching** | Supports multi-column primary keys (e.g. `(OwnerID, RuleID)`) |
| **Multi-module in-memory state** | Switch between PMR, Alert Rule, and Process tabs without re-uploading |
| **Keyboard navigation** | ↑/↓ rules, ←/→ filter chips, Tab/Shift+Tab modules, Home/End |
| **Zero dependencies at runtime** | Ships as a standalone Windows EXE (no Python needed) |
| **100% localhost** | No data leaves your machine |

**Supported modules:** PMR · Alert Rule · Process · Translator Actions · Translators · CIS Job · BRE · RRD · User Layout · Assignment Rule · Template Master · Layout Group View

---

## Quick start (from source)

Requires Python 3.10+.

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

The server starts on `http://127.0.0.1:8000` and your browser opens
automatically. Upload a DEV `.xlsx` and a PROD `.xlsx` for any supported
module.

---

## Standalone Windows EXE

### Download Pre-built Binary
You can download the standalone `Configuration_Comparison_Tool.exe` directly from the [latest GitHub Release](https://github.com/BeastOfSyn/configuration-comparison-tool/releases/latest) (no Python or dependencies required).

> **Note on Windows SmartScreen:** The executable is unsigned. When launching for the first time, Windows Defender SmartScreen may display an "Unrecognized app" warning. Click **"More info"** → **"Run anyway"** to launch.

### Build from Source
```bat
build.bat
```

Output: `dist\Configuration_Comparison_Tool.exe` — portable binary for 64-bit Windows.

---

## Running the test suite

The suite requires a running server on port 8010:

```bat
# Terminal 1 — start server
.venv\Scripts\activate
python -m uvicorn app:app --host 127.0.0.1 --port 8010

# Terminal 2 — run tests
python test_comprehensive.py
```

### Expected output (test fixture summary)

The six Excel files in `test_data/` are synthetic regression fixtures that
exercise all comparison verdicts. Expected results:

| Module | Total | Modified | Added | Removed | Audit-only | Data Quality | Skipped DEV/PROD |
|---|---:|---:|---:|---:|---:|---:|---:|
| PMR | 6 | 1 | 1 | 1 | 1 | 1 | 0 / 0 |
| Alert Rule | 3 | 1 | 0 | 0 | 0 | 1 | 1 / 1 |
| Process | 3 | 1 | 0 | 0 | 0 | 1 | 0 / 0 |

All 7 assertions pass against the test fixtures.

---

## Tech stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn, Pandas, OpenPyXL
- **Frontend:** Vanilla HTML5 / CSS3 / ES6 — single file, zero npm
- **Packaging:** PyInstaller (Windows EXE via `build.bat`)

---

## Project structure

```
├── engine.py              # Core diff engine — AST canonicalization, DQ pipeline
├── app.py                 # FastAPI server — file upload, compare endpoints
├── main.py                # Desktop bootstrap — starts server, opens browser
├── static/
│   └── index.html         # Single-file SPA (HTML + CSS + JS)
├── test_data/             # Synthetic Excel regression fixtures
├── test_comprehensive.py  # API integration test suite
├── test_exe_endpoints.py  # Standalone EXE smoke test (Windows only)
├── validate_build.py      # Pre-build integrity check (used by build.bat)
├── PMR_Comparison.spec    # PyInstaller spec
├── build.bat              # One-click EXE builder
└── requirements.txt
```

---

## License

MIT — see [LICENSE](LICENSE).
