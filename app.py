# Version 1.0.6
from flask import Flask, request, jsonify
from collections import OrderedDict
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import urllib
import getpass
import ctypes
import ctypes.wintypes
import requests
import subprocess
import sys
import threading

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# ===== VERSIONING =====
APP_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_VERSION_FILE = os.path.join(APP_DIR, "version.txt")
GITHUB_VERSION_URL = "https://raw.githubusercontent.com/vivek007-dotcom/test/main/version.txt"
GITHUB_APP_URL = "https://raw.githubusercontent.com/vivek007-dotcom/test/main/app.py"

def get_local_version():
    try:
        with open(LOCAL_VERSION_FILE, "r") as f:
            return f.read().strip().replace("version=", "").strip()
    except:
        return "0.0.0"

def get_remote_version():
    try:
        r = requests.get(GITHUB_VERSION_URL, timeout=5)
        if r.status_code == 200:
            return r.text.strip().replace("version=", "").strip()
    except:
        pass
    return None

def update_app_if_needed():
    local = get_local_version()
    remote = get_remote_version()
    logger.info(f"Local version={local}, Remote version={remote}")
    if remote and remote != local:
        logger.info(f"Updating app.py from version {local} to {remote}")
        try:
            SCHEDTASKS_EXE = r"C:\Windows\System32\schtasks.exe"
            trigger_path = os.path.join(APP_DIR, "update_trigger.py")
            run_time = (datetime.now() + timedelta(seconds=10)).strftime("%H:%M")

            subprocess.run([
                SCHEDTASKS_EXE, "/Create", "/TN", "FlaskAPI_Restart",
                "/TR", f'"{sys.executable}" "{trigger_path}"',
                "/SC", "ONCE", "/ST", run_time,
                "/F"
            ], check=False)

            r = requests.get(GITHUB_APP_URL, timeout=10)
            if r.status_code == 200:
                with open(__file__, "w", encoding="utf-8") as f:
                    f.write(r.text)
                with open(LOCAL_VERSION_FILE, "w") as f:
                    f.write(remote)

            logger.info("Update successful. Scheduled restart via schtasks.")
            os._exit(0)
        except Exception:
            logger.exception("Update failed")
    return False
    
# ===== USERNAME RESOLUTION =====
def get_active_user():
    WTS_CURRENT_SERVER_HANDLE = ctypes.c_void_p(0)
    WTS_CURRENT_SESSION = ctypes.wintypes.DWORD(-1)
    WTSUserName = 5

    buf = ctypes.c_void_p()
    bytes_returned = ctypes.wintypes.DWORD()

    result = ctypes.windll.wtsapi32.WTSQuerySessionInformationW(
        WTS_CURRENT_SERVER_HANDLE,
        WTS_CURRENT_SESSION,
        WTSUserName,
        ctypes.byref(buf),
        ctypes.byref(bytes_returned)
    )

    if result and bytes_returned.value > 0:
        username = ctypes.wstring_at(buf)
        ctypes.windll.wtsapi32.WTSFreeMemory(buf)
        return username
    else:
        return getpass.getuser()

USERNAME = get_active_user()
DOCUMENTS_DIR = os.path.join("C:\\Users", USERNAME, "Documents", "CitrixAutomation")
OUTPUT_PATH = os.path.join(DOCUMENTS_DIR, "CitrixParameters.txt")
LOG_FILE = os.path.join(DOCUMENTS_DIR, "local_patient_api.log")
os.makedirs(DOCUMENTS_DIR, exist_ok=True)

FLOW_NAME = "TestCMD"
PAD_EXE_PATH = r"C:\Program Files (x86)\Power Automate Desktop\dotnet\PAD.Console.Host.exe"
ENABLE_PAD_TRIGGER = True
PAD_TIMEOUT_SECONDS = 20

ALL_FIELDS = [
    "patient_name", "patient_dob", "patient_mrn", "app_name",
    "patient_gender", "patient_nbr", "patient_ssn", "patient_location",
    "patient_claim", "patient_encounter", "patient_statement"
]

# ===== LOGGING =====
logger = logging.getLogger("local_patient_api")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=500000, backupCount=3, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)

# ===== HELPERS =====
def normalize_payload(data: dict) -> OrderedDict:
    normalized = OrderedDict()
    for key in ALL_FIELDS:
        val = data.get(key, "") if isinstance(data, dict) else ""
        normalized[key] = "" if val is None else val
    return normalized

def _ensure_target_file(path: str):
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("")

def safe_overwrite(path: str, text: str):
    _ensure_target_file(path)
    temp_path = os.path.join(os.path.dirname(path), "__temp_write__.txt")
    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass

def build_pad_uri(flow_name: str) -> str:
    encoded_name = urllib.parse.quote(flow_name or "")
    return f"ms-powerautomate:/console/flow/run?workflowName={encoded_name}&authMode=Default"

def trigger_via_protocol(uri: str) -> dict:
    result = {"method": "protocol_handler", "uri": uri, "success": False, "error": None}
    try:
        if os.name != "nt":
            result["error"] = "Protocol handler only works on Windows"
            return result
        os.startfile(uri)
        result["success"] = True
        logger.info("Triggered Power Automate via protocol handler: %s", uri)
    except Exception as e:
        result["error"] = str(e)
        logger.exception("Protocol handler trigger failed")
    return result

def trigger_via_exe(exe_path: str, uri: str) -> dict:
    result = {
        "method": "pad_console_host", "exe_path": exe_path, "uri": uri,
        "success": False, "returncode": None, "stdout": "", "stderr": "", "error": None
    }
    try:
        if not os.path.exists(exe_path):
            result["error"] = f"PAD executable not found: {exe_path}"
            return result
        proc = subprocess.run(
            [exe_path, uri], check=False, capture_output=True, text=True, timeout=PAD_TIMEOUT_SECONDS
        )
        result["returncode"] = proc.returncode
        result["stdout"] = (proc.stdout or "").strip()
        result["stderr"] = (proc.stderr or "").strip()
        result["success"] = (proc.returncode == 0)
        logger.info("PAD.Console.Host.exe executed, returncode=%s", proc.returncode)
    except Exception as e:
        result["error"] = str(e)
        logger.exception("PAD.Console.Host.exe launch failed")
    return result

def trigger_power_automate() -> dict:
    info = {"enabled": ENABLE_PAD_TRIGGER, "success": False, "flow_name": FLOW_NAME}
    if not ENABLE_PAD_TRIGGER:
        info["error"] = "Trigger disabled (ENABLE_PAD_TRIGGER=False)"
        return info
    uri = build_pad_uri(FLOW_NAME)
    proto = trigger_via_protocol(uri)
    info.update(proto)
    if not info["success"]:
        exe = trigger_via_exe(PAD_EXE_PATH, uri)
        info.update(exe)
    return info

# ===== API ROUTES =====
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()}), 200

@app.route("/version", methods=["GET"])
def version():
    return jsonify({"version": get_local_version()}), 200

@app.route("/patient-intake", methods=["POST"])
def patient_intake():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON object"}), 400

    normalized = normalize_payload(data)
    json_text = json.dumps(normalized, ensure_ascii=False, indent=2)

    file_result = {"path": OUTPUT_PATH, "success": False, "error": None}
    try:
        safe_overwrite(OUTPUT_PATH, json_text)
        file_result["success"] = True
        logger.info("Successfully wrote patient parameters to %s", OUTPUT_PATH)
    except Exception as e:
        file_result["error"] = str(e)
        logger.exception("File write failed")

    pad_result = trigger_power_automate() if file_result["success"] else {
        "enabled": ENABLE_PAD_TRIGGER,
        "success": False,
        "error": "Skipped due to write failure"
    }

    status_code = 200 if (file_result["success"] and pad_result.get("success", True)) else 500
    response = jsonify({
        "data": normalized,
        "file_write": file_result,
        "power_automate": pad_result
    })

    # Run update check AFTER sending response (non-blocking)
    def background_update():
        try:
            update_app_if_needed()
        except Exception as e:
            logger.exception("Background update check failed")

    threading.Thread(target=background_update, daemon=True).start()

    return response, status_code

# ===== ENTRY POINT =====
if __name__ == "__main__":
    logger.info("Server started on http://127.0.0.1:3000")
    app.run(host="127.0.0.1", port=3000, debug=False)








