import subprocess, time, urllib.request, json, uuid, os
from pathlib import Path

exe_path = Path("dist/Configuration_Comparison_Tool.exe").resolve()
print("Starting EXE:", exe_path)

proc = subprocess.Popen([str(exe_path)])

# Poll with retry until server is ready (onefile unpack takes a few seconds)
health_data = None
for _ in range(25):
    time.sleep(1)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2) as resp:
            health_data = json.loads(resp.read().decode())
            break
    except Exception:
        pass

if not health_data:
    proc.terminate()
    raise RuntimeError("Timed out waiting for EXE to boot Uvicorn on http://127.0.0.1:8000")

try:
    print("Health check:", health_data)
    assert health_data["service"] == "configuration comparison tool"
    assert health_data["version"] == "12.3"

    with urllib.request.urlopen("http://127.0.0.1:8000/api/modules") as resp:
        mod_data = json.loads(resp.read().decode())
        print("Modules:", list(mod_data.keys()))

    def post_multipart(path, file1_name, file1_bytes, file2_name, file2_bytes):
        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
        body = bytearray()
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="dev_file"; filename="{file1_name}"\r\n'.encode("utf-8"))
        body.extend(b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n")
        body.extend(file1_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="prod_file"; filename="{file2_name}"\r\n'.encode("utf-8"))
        body.extend(b"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n")
        body.extend(file2_bytes)
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode("utf-8"))
        req = urllib.request.Request(
            f"http://127.0.0.1:8000{path}",
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))

    ROOT = Path(".")
    pmr_res = post_multipart("/api/compare/pmr", "pmr_dev.xlsx", (ROOT/"test_data"/"pmr_dev.xlsx").read_bytes(), "pmr_prod.xlsx", (ROOT/"test_data"/"pmr_prod.xlsx").read_bytes())
    print("PMR Comparison Summary:", pmr_res["summary"])
    print("PMR DQ items count:", len(pmr_res["data_quality"]))
    if pmr_res["data_quality"]:
        print("PMR DQ Reasons:", pmr_res["data_quality"][0]["dq_reasons"])
        print("PMR DQ Field Issues:", pmr_res["data_quality"][0].get("field_issues"))

    alert_res = post_multipart("/api/compare/alert_rule", "alert_dev.xlsx", (ROOT/"test_data"/"alert_dev.xlsx").read_bytes(), "alert_prod.xlsx", (ROOT/"test_data"/"alert_prod.xlsx").read_bytes())
    print("Alert Comparison Summary:", alert_res["summary"])
    print("Alert DQ count:", len(alert_res["data_quality"]))

    proc_res = post_multipart("/api/compare/process", "proc_dev.xlsx", (ROOT/"test_data"/"proc_dev.xlsx").read_bytes(), "proc_prod.xlsx", (ROOT/"test_data"/"proc_prod.xlsx").read_bytes())
    print("Process Comparison Summary:", proc_res["summary"])
    print("Process DQ count:", len(proc_res["data_quality"]))

    print("\n>>> SUCCESS: ALL ENDPOINTS ON STANDALONE EXE VALIDATED PERFECTLY! <<<")
finally:
    proc.terminate()
    proc.wait()
