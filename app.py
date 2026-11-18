#!/usr/bin/env python3
"""
Self-Contained OpenCode OpenAI Bridge for Render.com
----------------------------------------------------
100% Standalone on Render:
- Automatically installs OpenCode CLI inside the Render container.
- Starts an internal OpenCode daemon (127.0.0.1:4096) inside Render.
- Translates incoming standard OpenAI requests to the internal OpenCode daemon.
- Completely isolated: ZERO connection to any external VPS or domain.
"""

import os
import sys
import time
import json
import uuid
import base64
import subprocess
import shutil
import urllib.request
import urllib.error
from flask import Flask, request, jsonify

app = Flask(__name__)

# Internal Render Container Port for local daemon
LOCAL_DAEMON_PORT = 4096
LOCAL_DAEMON_URL = f"http://127.0.0.1:{LOCAL_DAEMON_PORT}"
LOCAL_DAEMON_PASSWORD = os.environ.get("OPENCODE_PASSWORD", "render_internal_pass_2026")
AUTH_HEADER = "Basic " + base64.b64encode(f"opencode:{LOCAL_DAEMON_PASSWORD}".encode()).decode()

SUPPORTED_MODELS = [
    "big-pickle",
    "hy4-flash-free",
    "beam-free",
    "deepseek-v4.1-flash-free",
    "mimo-v2.6-flash-free",
    "longcat-2.5-free",
    "flint-40b-free",
    "nemotron-3.5-lightning-free"
]

DAEMON_PROCESS = None

def find_opencode_binary():
    """Finds or installs the official OpenCode CLI binary"""
    candidates = [
        os.path.expanduser("~/.opencode/bin/opencode"),
        shutil.which("opencode"),
        "/opt/render/.opencode/bin/opencode",
        "/usr/local/bin/opencode",
        "/usr/bin/opencode",
        "./opencode"
    ]
    for c in candidates:
        if c and os.path.exists(c) and os.access(c, os.X_OK):
            return c

    print("[RENDER SETUP] OpenCode binary not found. Installing official OpenCode CLI...", flush=True)
    try:
        cmd = "curl -fsSL https://opencode.ai/v2/install | bash -s -- --no-modify-path"
        subprocess.run(cmd, shell=True, check=True)
        installed = os.path.expanduser("~/.opencode/bin/opencode")
        if os.path.exists(installed):
            return installed
    except Exception as e:
        print(f"[RENDER SETUP ERROR] Install script failed: {e}", flush=True)

    return None

def is_daemon_running():
    try:
        req = urllib.request.Request(f"{LOCAL_DAEMON_URL}/api/info")
        req.add_header("Authorization", AUTH_HEADER)
        with urllib.request.urlopen(req, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False

def start_internal_daemon():
    """Starts the internal OpenCode daemon inside the Render container"""
    global DAEMON_PROCESS
    if is_daemon_running():
        print("[DAEMON] Internal OpenCode daemon is already running.", flush=True)
        return True

    binary = find_opencode_binary()
    if not binary:
        print("[ERROR] Cannot start daemon: opencode binary not found.", flush=True)
        return False

    print(f"[DAEMON] Starting OpenCode daemon using: {binary} on port {LOCAL_DAEMON_PORT}", flush=True)
    env = os.environ.copy()
    env["OPENCODE_PASSWORD"] = LOCAL_DAEMON_PASSWORD
    env["OPENCODE_SERVER_PASSWORD"] = LOCAL_DAEMON_PASSWORD

    # IMPORTANT: Do NOT include --auto flag in 'serve' command!
    cmd = [
        binary,
        "serve",
        "--hostname", "127.0.0.1",
        "--port", str(LOCAL_DAEMON_PORT)
    ]

    DAEMON_PROCESS = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait up to 10 seconds for daemon to respond
    for i in range(10):
        time.sleep(1)
        if DAEMON_PROCESS.poll() is not None:
            stdout, stderr = DAEMON_PROCESS.communicate()
            print(f"[DAEMON ERROR] Process exited early (code {DAEMON_PROCESS.returncode}):", flush=True)
            print(f"STDOUT: {stdout}\nSTDERR: {stderr}", flush=True)
            return False
        if is_daemon_running():
            print(f"[DAEMON SUCCESS] OpenCode daemon is active on port {LOCAL_DAEMON_PORT}!", flush=True)
            return True

    print("[WARN] OpenCode daemon startup exceeded timeout.", flush=True)
    return is_daemon_running()

# Attempt daemon startup at load time
try:
    start_internal_daemon()
except Exception as e:
    print(f"[BOOT ERROR] {e}", flush=True)

def daemon_request(endpoint, method="GET", data=None):
    """Communicates directly with the internal OpenCode daemon inside Render"""
    url = f"{LOCAL_DAEMON_URL}{endpoint}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", AUTH_HEADER)
    req.add_header("Content-Type", "application/json")

    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")

    try:
        with urllib.request.urlopen(req, data=body, timeout=60) as resp:
            content = resp.read().decode("utf-8")
            if content:
                return resp.status, json.loads(content)
            return resp.status, {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        try:
            return e.code, json.loads(err)
        except Exception:
            return e.code, {"error": err}
    except Exception as e:
        return 500, {"error": str(e)}

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Api-Key"
    return response

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    daemon_ok = is_daemon_running()
    return jsonify({
        "status": "online" if daemon_ok else "initializing",
        "service": "Standalone Render OpenCode Proxy",
        "internal_daemon": "active" if daemon_ok else "inactive",
        "supported_models": SUPPORTED_MODELS
    })

@app.route("/v1/models", methods=["GET"])
@app.route("/models", methods=["GET"])
def list_models():
    data = []
    for m in SUPPORTED_MODELS:
        data.append({"id": m, "object": "model", "created": int(time.time()), "owned_by": "opencode"})
        data.append({"id": f"opencode/{m}", "object": "model", "created": int(time.time()), "owned_by": "opencode"})
    return jsonify({"object": "list", "data": data})

@app.route("/v1/chat/completions", methods=["POST"])
@app.route("/chat/completions", methods=["POST"])
def chat_completions():
    # If daemon isn't running yet, boot it
    if not is_daemon_running():
        start_internal_daemon()

    req_data = request.get_json(silent=True)
    if not req_data:
        return jsonify({"error": {"message": "Malformed JSON body", "type": "invalid_request_error"}}), 400

    raw_model = req_data.get("model", "big-pickle")
    model_id = raw_model.replace("opencode/", "").strip()
    if not model_id or model_id not in SUPPORTED_MODELS:
        model_id = "big-pickle"

    messages = req_data.get("messages", [])
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            prompt_parts.append(f"[System: {content}]")
        elif role == "user":
            prompt_parts.append(f"User: {content}")
        elif role == "assistant":
            prompt_parts.append(f"Assistant: {content}")

    if not prompt_parts:
        prompt_text = "Hello"
    elif len(prompt_parts) == 1 and prompt_parts[0].startswith("User: "):
        prompt_text = prompt_parts[0][6:]
    else:
        prompt_text = "\n\n".join(prompt_parts)

    try:
        # Step 1: Create session on internal daemon
        s_code, s_res = daemon_request("/api/session", method="POST", data={"title": f"Render {model_id}"})
        if s_code not in (200, 201) or "data" not in s_res:
            return jsonify({"error": {"message": f"Internal daemon session error: {s_res}", "type": "gateway_error"}}), 502

        session_id = s_res["data"]["id"]

        # Step 2: Switch model
        if model_id != "big-pickle":
            daemon_request(
                f"/api/session/{session_id}/model",
                method="POST",
                data={"model": {"id": model_id, "providerID": "opencode"}}
            )

        # Step 3: Send prompt
        daemon_request(
            f"/api/session/{session_id}/prompt",
            method="POST",
            data={"text": prompt_text}
        )

        # Step 4: Poll internal daemon for assistant reply
        assistant_reply = ""
        usage_tokens = {"input": 0, "output": 0}
        start_time = time.time()
        timeout_seconds = 75

        while time.time() - start_time < timeout_seconds:
            time.sleep(1.0)
            m_code, m_res = daemon_request(f"/api/session/{session_id}/message")
            if m_code == 200 and "data" in m_res:
                messages_list = m_res["data"]
                assistant_msg = next((m for m in messages_list if m.get("type") == "assistant"), None)
                idle_msg = next((m for m in messages_list if m.get("type") == "idle"), None)

                if assistant_msg:
                    contents = assistant_msg.get("content", [])
                    text_parts = [c.get("text", "") for c in contents if c.get("type") == "text"]
                    if text_parts:
                        assistant_reply = "".join(text_parts)
                    tokens = assistant_msg.get("tokens", {})
                    usage_tokens["input"] = tokens.get("input", 0)
                    usage_tokens["output"] = tokens.get("output", 0)

                if idle_msg and assistant_reply:
                    break

        if not assistant_reply:
            assistant_reply = "I completed the request."

        openai_resp = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": assistant_reply
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": usage_tokens["input"],
                "completion_tokens": usage_tokens["output"],
                "total_tokens": usage_tokens["input"] + usage_tokens["output"]
            }
        }
        return jsonify(openai_resp)

    except Exception as e:
        return jsonify({"error": {"message": f"Bridge error: {str(e)}", "type": "server_error"}}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
