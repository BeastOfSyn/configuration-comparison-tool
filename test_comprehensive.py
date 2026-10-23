import py_compile
import json
import urllib.request
import urllib.error
import mimetypes
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 1. Compile checks
for py_file in ["engine.py", "app.py", "main.py", "validate_build.py"]:
    py_compile.compile(str(ROOT / py_file), doraise=True)
print("1. Python py_compile: ALL PASS")

# 2. HTML checks
html_file = ROOT / "static" / "index.html"
html_content = html_file.read_text(encoding="utf-8")
assert html_content.count("<html") == 1, "Multiple <html tags found"
assert html_content.count("</html>") == 1, "Multiple </html> tags found"
assert html_content.count("<script>") == 1, "Multiple <script> tags found"
assert html_content.count("</script>") == 1, "Multiple </script> tags found"

before_script, script_and_after = html_content.split("<script>", 1)
script_body, after_script = script_and_after.split("</script>", 1)
assert after_script.strip() in ["</body>\n</html>", "</body></html>"], f"Unexpected content after </script>: {repr(after_script)}"
print("2. HTML Structure & Script encapsulation: ALL PASS")

# 3. Test HTTP Endpoints via urllib
BASE_URL = "http://127.0.0.1:8010"

def get_json(path):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def post_multipart(path, file1_name, file1_bytes, file2_name, file2_bytes):
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()

    # dev_file
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="dev_file"; filename="{file1_name}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n")
    body.extend(file1_bytes)
    body.extend(b"\r\n")

    # prod_file
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="prod_file"; filename="{file2_name}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n")
    body.extend(file2_bytes)
    body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

# Health
health_data = get_json("/api/health")
assert health_data["status"] == "ok", f"Health status not ok: {health_data}"
print("3. GET /api/health: PASS ->", health_data)

# Modules
mod_data = get_json("/api/modules")
assert "pmr" in mod_data and "alert_rule" in mod_data and "process" in mod_data
print("4. GET /api/modules: PASS ->", list(mod_data.keys()))

# Compare PMR
pmr_dev_bytes = (ROOT / "test_data" / "pmr_dev.xlsx").read_bytes()
pmr_prod_bytes = (ROOT / "test_data" / "pmr_prod.xlsx").read_bytes()
pmr_res = post_multipart("/api/compare/pmr", "pmr_dev.xlsx", pmr_dev_bytes, "pmr_prod.xlsx", pmr_prod_bytes)
assert pmr_res["summary"]["total"] == 6
assert pmr_res["summary"]["modified"] == 1
assert pmr_res["summary"]["added"] == 1
assert pmr_res["summary"]["removed"] == 1
assert pmr_res["summary"]["audit_only"] == 1
assert pmr_res["summary"]["data_quality"] == 1
print("5. POST /api/compare/pmr: PASS -> Summary:", pmr_res["summary"])

# Compare Alert Rule
alert_dev_bytes = (ROOT / "test_data" / "alert_dev.xlsx").read_bytes()
alert_prod_bytes = (ROOT / "test_data" / "alert_prod.xlsx").read_bytes()
alert_res = post_multipart("/api/compare/alert_rule", "alert_dev.xlsx", alert_dev_bytes, "alert_prod.xlsx", alert_prod_bytes)
assert alert_res["summary"]["total"] == 3
assert alert_res["summary"]["modified"] == 1
assert alert_res["summary"]["data_quality"] == 1
assert alert_res["summary"]["skipped_dev"] == 1
assert alert_res["summary"]["skipped_prod"] == 1
print("6. POST /api/compare/alert_rule: PASS -> Summary:", alert_res["summary"])

# Compare Process
proc_dev_bytes = (ROOT / "test_data" / "proc_dev.xlsx").read_bytes()
proc_prod_bytes = (ROOT / "test_data" / "proc_prod.xlsx").read_bytes()
proc_res = post_multipart("/api/compare/process", "proc_dev.xlsx", proc_dev_bytes, "proc_prod.xlsx", proc_prod_bytes)
assert proc_res["summary"]["total"] == 3
assert proc_res["summary"]["modified"] == 1
assert proc_res["summary"]["data_quality"] == 1
print("7. POST /api/compare/process: PASS -> Summary:", proc_res["summary"])

print("\nALL BACKEND & API TESTS PASSED SUCCESSFULLY!")
