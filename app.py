# file: local_patient_api.py
from flask import Flask, request, jsonify
from collections import OrderedDict
import os
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import subprocess
import urllib.parse

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False

# ======= CONFIGURATION =======
OUTPUT_PATH = r"C:\Users\Signity\Documents\CitrixAutomation\CitrixParameters.txt"  # <— updated path

# 👇 CHANGE THIS VALUE ANYTIME — your flow name
FLOW_NAME = "TestCMD"  # ← edit this only

PAD_EXE_PATH = r"C:\Program Files (x86)\Power Automate Desktop\dotnet\PAD.Console.Host.exe"
ENABLE_PAD_TRIGGER = True  # set False to disable triggering PAD
PAD_TIMEOUT_SECONDS = 20  # seconds to wait for PAD launcher

# ==============================

ALL_FIELDS = [
    "patient_name",
    "patient_dob",
    "patient_mrn",
    "app_name",
    "patient_gender",
    "patient_nbr",
    "patient_ssn",
    "patient_location",
    "patient_claim",
    "patient_encounter",
    "patient_statement",
]

# ===== LOGGING =====
LOG_FILE = os.path.join(os.path.expanduser("~"), "local_patient_api.log")
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
    """
    Ensure parent directory exists and the target file exists.
    If file is missing, create it (empty) before writing.
    """
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    if not os.path.exists(path):
        # create an empty file first
        with open(path, "w", encoding="utf-8") as f:
            f.write("")


def safe_overwrite(path: str, text: str):
    """Create if missing, otherwise overwrite atomically — always one file."""
    _ensure_target_file(path)  # <— ensures the file exists first

    directory = os.path.dirname(path) or "."
    temp_path = os.path.join(directory, "__temp_write__.txt")

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def build_pad_uri(flow_name: str) -> str:
    """Construct Power Automate Desktop URI."""
    encoded_name = urllib.parse.quote(flow_name or "")
    return f"ms-powerautomate:/console/flow/run?workflowName={encoded_name}&authMode=Default"


def trigger_via_protocol(uri: str) -> dict:
    """Use Windows protocol handler to launch PAD."""
    result = {"method": "protocol_handler", "uri": uri, "success": False, "error": None}
    try:
        if os.name != "nt":
            result["error"] = "Protocol handler only works on Windows"
            return result
        os.startfile(uri)  # type: ignore[attr-defined]
        result["success"] = True
        logger.info("Triggered Power Automate via protocol handler: %s", uri)
    except Exception as e:
        result["error"] = str(e)
        logger.exception("Protocol handler trigger failed")
    return result


def trigger_via_exe(exe_path: str, uri: str) -> dict:
    """Fallback: use PAD.Console.Host.exe directly."""
    result = {
        "method": "pad_console_host",
        "exe_path": exe_path,
        "uri": uri,
        "success": False,
        "returncode": None,
        "stdout": "",
        "stderr": "",
        "error": None
    }
    try:
        if not os.path.exists(exe_path):
            result["error"] = f"PAD executable not found: {exe_path}"
            return result

        proc = subprocess.run(
            [exe_path, uri],
            check=False,
            capture_output=True,
            text=True,
            timeout=PAD_TIMEOUT_SECONDS
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
    """Trigger Power Automate using the static FLOW_NAME variable."""
    info = {"enabled": ENABLE_PAD_TRIGGER, "success": False, "flow_name": FLOW_NAME}
    if not ENABLE_PAD_TRIGGER:
        info["error"] = "Trigger disabled (ENABLE_PAD_TRIGGER=False)"
        return info

    uri = build_pad_uri(FLOW_NAME)
    proto = trigger_via_protocol(uri)
    info["method"] = proto["method"]
    info["uri"] = uri
    info["success"] = proto["success"]
    info["error"] = proto.get("error")

    if not info["success"]:
        exe = trigger_via_exe(PAD_EXE_PATH, uri)
        info.update(exe)

    return info


# ===== API ROUTES =====
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()}), 200


@app.route("/patient-intake", methods=["POST"])
def patient_intake():
    if not request.is_json:
        return jsonify({"error": "Request must be JSON"}), 400

    data = request.get_json(silent=True)
    if data is None or not isinstance(data, dict):
        return jsonify({"error": "Invalid JSON object"}), 400

    normalized = normalize_payload(data)
    json_text = json.dumps(normalized, ensure_ascii=False, indent=2)

    # 1️⃣ Write to file (create if missing, otherwise overwrite)
    file_result = {"path": OUTPUT_PATH, "success": False, "error": None}
    try:
        safe_overwrite(OUTPUT_PATH, json_text)
        file_result["success"] = True
        logger.info("Successfully wrote patient parameters to %s", OUTPUT_PATH)
    except Exception as e:
        file_result["error"] = str(e)
        logger.exception("File write failed")

    # 2️⃣ Trigger Power Automate flow (only if file write succeeded)
    pad_result = {}
    if file_result["success"]:
        pad_result = trigger_power_automate()
    else:
        pad_result = {"enabled": ENABLE_PAD_TRIGGER, "success": False, "error": "Skipped due to write failure"}

    status_code = 200 if (file_result["success"] and pad_result.get("success", True)) else 500
    return jsonify({
        "data": normalized,
        "file_write": file_result,
        "power_automate": pad_result
    }), status_code


# ===== RUN SERVER =====
if __name__ == "__main__":
    logger.info("Server started on http://127.0.0.1:5000")
    logger.info("Output file: %s", OUTPUT_PATH)
    logger.info("Flow name (static): %s", FLOW_NAME)
    logger.info("PAD exe: %s", PAD_EXE_PATH)
    app.run(host="127.0.0.1", port=5000, debug=False)
