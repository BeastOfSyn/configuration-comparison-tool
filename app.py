import sys
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine import compare_files

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    UPLOAD_DIR = Path(tempfile.gettempdir()) / "config_diff_uploads"
else:
    BASE_DIR = Path(__file__).resolve().parent
    UPLOAD_DIR = BASE_DIR / ".uploads"

__author__ = "BeastOfSyn"
__version__ = "12.3"

STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="Configuration Comparison Tool",
    version="12.3",
    description="AST-aware DEV/PROD configuration diff engine by BeastOfSyn",
    contact={"name": "BeastOfSyn"}
)

@app.middleware("http")
async def add_signature_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Engine-Seal"] = "BSN-CORE-42656173744f6653796e"
    response.headers["X-Author"] = "BeastOfSyn"
    return response

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/modules")
def modules():
    return {
        "pmr": {"label": "PMR"},
        "alert_rule": {"label": "Alert Rule"},
        "process": {"label": "Process"},
        "translator_actions": {"label": "Translator Actions"},
        "translators": {"label": "Translators"},
        "cis_job": {"label": "CIS Job"},
        "bre": {"label": "BRE"},
        "rrd": {"label": "RRD"},
        "user_layout": {"label": "User Layout"},
        "assignment_rule": {"label": "Assignment Rule"},
        "template_master": {"label": "Template Master"},
        "layout_group_view": {"label": "Layout Group View"},
    }

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "configuration comparison tool", "version": "12.3"}

@app.get("/api/system/signature")
def signature():
    return {
        "status": "ok",
        "author": "BeastOfSyn",
        "seal": "BSN-CORE-42656173744f6653796e",
        "engine": "Configuration AST Diff Tracker",
        "version": "12.3"
    }


@app.post("/api/compare/{module}")
async def compare(
    module: str,
    dev_file: UploadFile = File(...),
    prod_file: UploadFile = File(...),
):
    allowed = {".xlsx", ".xls", ".csv"}
    dev_suffix = Path(dev_file.filename or "").suffix.lower()
    prod_suffix = Path(prod_file.filename or "").suffix.lower()
    if dev_suffix not in allowed or prod_suffix not in allowed:
        raise HTTPException(status_code=400, detail="Please upload Excel or CSV files (.xlsx, .xls, or .csv).")

    run_id = uuid.uuid4().hex
    dev_path = UPLOAD_DIR / f"{run_id}_dev{dev_suffix}"
    prod_path = UPLOAD_DIR / f"{run_id}_prod{prod_suffix}"
    dev_path.write_bytes(await dev_file.read())
    prod_path.write_bytes(await prod_file.read())

    try:
        return compare_files(module, str(dev_path), str(prod_path), dev_file.filename or "DEV.xlsx", prod_file.filename or "PROD.xlsx")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {exc}")
    finally:
        dev_path.unlink(missing_ok=True)
        prod_path.unlink(missing_ok=True)
