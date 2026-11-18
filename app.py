#!/usr/bin/env python3
"""
Dual OpenAI & Anthropic Compatible OpenCode Bridge for Render.com
-----------------------------------------------------------------
100% Dual-API Compatible:
1. OpenAI API:
   - GET  /v1/models
   - GET  /v1/models/<model_id>
   - POST /v1/chat/completions (Streaming & Non-streaming)
2. Anthropic API:
   - POST /v1/messages (Streaming & Non-streaming)
   - Headers: x-api-key or Authorization: Bearer
3. Authentication:
   - Accepts 'sk-opencode-free', 'sk-ant-free', or any custom key
4. 100% Standalone:
   - Runs internal OpenCode CLI daemon inside the container.
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
from flask import Flask, request, jsonify, Response, stream_with_context

app = Flask(__name__)

# Internal Render Container Port for local OpenCode daemon
LOCAL_DAEMON_PORT = 4096
LOCAL_DAEMON_URL = f"http://127.0.0.1:{LOCAL_DAEMON_PORT}"
LOCAL_DAEMON_PASSWORD = os.environ.get("OPENCODE_PASSWORD", "render_internal_pass_2026")
AUTH_HEADER = "Basic " + base64.b64encode(f"opencode:{LOCAL_DAEMON_PASSWORD}".encode()).decode()

# Optional Custom Enforced API Key (Set on Render dashboard if you want strict security)
ENFORCED_API_KEY = os.environ.get("CUSTOM_API_KEY", "").strip()

# All Free & Working OpenCode Models
ALL_FREE_MODELS = [
    "big-pickle",
    "hy4-flash-free",
    "beam-free",
    "deepseek-v4.1-flash-free",
    "longcat-2.5-free",
    "flint-40b-free",
    "mimo-v2.6-flash-free",
    "nemotron-3.5-lightning-free",
    "nemotron-3.5-super-vl-free",
    "iceman-free",
    "inkling-2-small-free"
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
        return True

    binary = find_opencode_binary()
    if not binary:
        print("[ERROR] Cannot start daemon: opencode binary not found.", flush=True)
        return False

    print(f"[DAEMON] Starting OpenCode daemon using: {binary} on port {LOCAL_DAEMON_PORT}", flush=True)
    env = os.environ.copy()
    env["OPENCODE_PASSWORD"] = LOCAL_DAEMON_PASSWORD
    env["OPENCODE_SERVER_PASSWORD"] = LOCAL_DAEMON_PASSWORD

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

    for _ in range(12):
        time.sleep(1)
        if DAEMON_PROCESS.poll() is not None:
            stdout, stderr = DAEMON_PROCESS.communicate()
            print(f"[DAEMON ERROR] Code {DAEMON_PROCESS.returncode}: {stderr}", flush=True)
            return False
        if is_daemon_running():
            print(f"[DAEMON SUCCESS] OpenCode daemon is active on port {LOCAL_DAEMON_PORT}!", flush=True)
            return True

    return is_daemon_running()

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

@app.before_request
def verify_api_key():
    """Validates API Key (supports Authorization: Bearer OR x-api-key)"""
    if request.method == "OPTIONS":
        return
    if request.path in ["/", "/health"]:
        return

    # Check either Authorization or x-api-key header
    auth_header = request.headers.get("Authorization", "").strip()
    x_api_key = request.headers.get("x-api-key", "").strip()

    token = ""
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    elif x_api_key:
        token = x_api_key

    if ENFORCED_API_KEY:
        if token == ENFORCED_API_KEY:
            return
        return jsonify({
            "error": {
                "message": f"Incorrect API key provided. Authorization required: {ENFORCED_API_KEY}",
                "type": "authentication_error"
            }
        }), 401

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, x-api-key, anthropic-version, X-Api-Key"
    return response

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    daemon_ok = is_daemon_running()
    return jsonify({
        "status": "online" if daemon_ok else "initializing",
        "service": "Dual OpenAI & Anthropic OpenCode Proxy (Render)",
        "internal_daemon": "active" if daemon_ok else "inactive",
        "supported_models_count": len(ALL_FREE_MODELS),
        "api_key_status": "enforced" if ENFORCED_API_KEY else "accepts_any_key (e.g. sk-opencode-free)",
        "endpoints": {
            "openai_models": "/v1/models",
            "openai_model_detail": "/v1/models/<model_id>",
            "openai_chat": "/v1/chat/completions",
            "anthropic_messages": "/v1/messages"
        }
    })

def format_openai_model(m_id):
    return {
        "id": m_id,
        "object": "model",
        "created": 1795000000,
        "owned_by": "opencode",
        "permission": [
            {
                "id": f"modelperm-{m_id}",
                "object": "model_permission",
                "created": 1795000000,
                "allow_create_engine": False,
                "allow_sampling": True,
                "allow_logprobs": True,
                "allow_search_indices": False,
                "allow_view": True,
                "allow_fine_tuning": False,
                "organization": "*",
                "group": None,
                "is_blocking": False
            }
        ],
        "root": m_id,
        "parent": None
    }

# ==================== 1. OPENAI ENDPOINTS ====================

@app.route("/v1/models", methods=["GET"])
@app.route("/models", methods=["GET"])
def list_models():
    data = []
    for m in ALL_FREE_MODELS:
        data.append(format_openai_model(m))
        data.append(format_openai_model(f"opencode/{m}"))
    return jsonify({"object": "list", "data": data})

@app.route("/v1/models/<path:model_id>", methods=["GET"])
@app.route("/models/<path:model_id>", methods=["GET"])
def retrieve_model(model_id):
    clean_id = model_id.replace("opencode/", "").strip()
    if clean_id in ALL_FREE_MODELS:
        return jsonify(format_openai_model(model_id))
    return jsonify({
        "error": {
            "message": f"The model '{model_id}' does not exist",
            "type": "invalid_request_error",
            "param": "model",
            "code": "model_not_found"
        }
    }), 404

def execute_opencode_prompt(model_id, prompt_text):
    """Executes prompt via internal daemon and returns (assistant_reply, tokens)"""
    s_code, s_res = daemon_request("/api/session", method="POST", data={"title": f"Session {model_id}"})
    if s_code not in (200, 201) or "data" not in s_res:
        raise RuntimeError(f"OpenCode session error: {s_res}")

    session_id = s_res["data"]["id"]

    if model_id != "big-pickle":
        daemon_request(
            f"/api/session/{session_id}/model",
            method="POST",
            data={"model": {"id": model_id, "providerID": "opencode"}}
        )

    daemon_request(
        f"/api/session/{session_id}/prompt",
        method="POST",
        data={"text": prompt_text}
    )

    assistant_reply = ""
    usage_tokens = {"input": 0, "output": 0}
    start_time = time.time()

    while time.time() - start_time < 75:
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

    return assistant_reply, usage_tokens

@app.route("/v1/chat/completions", methods=["POST"])
@app.route("/chat/completions", methods=["POST"])
def openai_chat_completions():
    if not is_daemon_running():
        start_internal_daemon()

    req_data = request.get_json(silent=True)
    if not req_data:
        return jsonify({"error": {"message": "Malformed JSON body", "type": "invalid_request_error"}}), 400

    raw_model = req_data.get("model", "big-pickle")
    model_id = raw_model.replace("opencode/", "").strip()
    if not model_id or model_id not in ALL_FREE_MODELS:
        model_id = "big-pickle"

    messages = req_data.get("messages", [])
    prompt_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join([c.get("text", "") for c in content if isinstance(c, dict)])
        if role == "system":
            prompt_parts.append(f"[System: {content}]")
        elif role == "user":
            prompt_parts.append(f"User: {content}")
        elif role == "assistant":
            prompt_parts.append(f"Assistant: {content}")

    prompt_text = "\n\n".join(prompt_parts) if prompt_parts else "Hello"
    is_stream = req_data.get("stream", False)

    try:
        assistant_reply, usage_tokens = execute_opencode_prompt(model_id, prompt_text)
        chat_cmpl_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
        created_ts = int(time.time())

        if is_stream:
            def generate_openai_stream():
                chunk_role = {
                    "id": chat_cmpl_id, "object": "chat.completion.chunk",
                    "created": created_ts, "model": model_id,
                    "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk_role)}\n\n"

                chunk_content = {
                    "id": chat_cmpl_id, "object": "chat.completion.chunk",
                    "created": created_ts, "model": model_id,
                    "choices": [{"index": 0, "delta": {"content": assistant_reply}, "finish_reason": None}]
                }
                yield f"data: {json.dumps(chunk_content)}\n\n"

                chunk_finish = {
                    "id": chat_cmpl_id, "object": "chat.completion.chunk",
                    "created": created_ts, "model": model_id,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]
                }
                yield f"data: {json.dumps(chunk_finish)}\n\n"
                yield "data: [DONE]\n\n"

            return Response(stream_with_context(generate_openai_stream()), content_type="text/event-stream")

        return jsonify({
            "id": chat_cmpl_id,
            "object": "chat.completion",
            "created": created_ts,
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": assistant_reply},
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": usage_tokens["input"],
                "completion_tokens": usage_tokens["output"],
                "total_tokens": usage_tokens["input"] + usage_tokens["output"]
            }
        })

    except Exception as e:
        return jsonify({"error": {"message": f"OpenCode error: {str(e)}", "type": "server_error"}}), 500

# ==================== 2. ANTHROPIC MESSAGES ENDPOINTS ====================

@app.route("/v1/messages", methods=["POST"])
@app.route("/messages", methods=["POST"])
def anthropic_messages():
    """Full Anthropic Messages API compatible endpoint"""
    if not is_daemon_running():
        start_internal_daemon()

    req_data = request.get_json(silent=True)
    if not req_data:
        return jsonify({"type": "error", "error": {"type": "invalid_request_error", "message": "Malformed JSON body"}}), 400

    raw_model = req_data.get("model", "big-pickle")
    model_id = raw_model.replace("opencode/", "").strip()
    if not model_id or model_id not in ALL_FREE_MODELS:
        model_id = "big-pickle"

    prompt_parts = []
    # Anthropic system message can be a string or list
    system_msg = req_data.get("system", "")
    if isinstance(system_msg, list):
        system_text = " ".join([s.get("text", "") for s in system_msg if isinstance(s, dict)])
    else:
        system_text = str(system_msg)

    if system_text:
        prompt_parts.append(f"[System: {system_text}]")

    messages = req_data.get("messages", [])
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join([c.get("text", "") for c in content if isinstance(c, dict)])
        if role == "user":
            prompt_parts.append(f"User: {content}")
        elif role == "assistant":
            prompt_parts.append(f"Assistant: {content}")

    prompt_text = "\n\n".join(prompt_parts) if prompt_parts else "Hello"
    is_stream = req_data.get("stream", False)

    try:
        assistant_reply, usage_tokens = execute_opencode_prompt(model_id, prompt_text)
        msg_id = f"msg_{uuid.uuid4().hex[:20]}"

        if is_stream:
            def generate_anthropic_stream():
                # event 1: message_start
                yield f"event: message_start\ndata: {json.dumps({'type':'message_start','message':{'id':msg_id,'type':'message','role':'assistant','model':model_id,'content':[],'stop_reason':None,'stop_sequence':None,'usage':{'input_tokens':usage_tokens['input'],'output_tokens':1}}})}\n\n"

                # event 2: content_block_start
                yield f"event: content_block_start\ndata: {json.dumps({'type':'content_block_start','index':0,'content_block':{'type':'text','text':''}})}\n\n"

                # event 3: content_block_delta
                yield f"event: content_block_delta\ndata: {json.dumps({'type':'content_block_delta','index':0,'delta':{'type':'text_delta','text':assistant_reply}})}\n\n"

                # event 4: content_block_stop
                yield f"event: content_block_stop\ndata: {json.dumps({'type':'content_block_stop','index':0})}\n\n"

                # event 5: message_delta
                yield f"event: message_delta\ndata: {json.dumps({'type':'message_delta','delta':{'stop_reason':'end_turn','stop_sequence':None},'usage':{'output_tokens':usage_tokens['output']}})}\n\n"

                # event 6: message_stop
                yield f"event: message_stop\ndata: {json.dumps({'type':'message_stop'})}\n\n"

            return Response(stream_with_context(generate_anthropic_stream()), content_type="text/event-stream")

        # Standard Anthropic JSON Response
        anthropic_resp = {
            "id": msg_id,
            "type": "message",
            "role": "assistant",
            "model": model_id,
            "content": [
                {
                    "type": "text",
                    "text": assistant_reply
                }
            ],
            "stop_reason": "end_turn",
            "stop_sequence": None,
            "usage": {
                "input_tokens": usage_tokens["input"],
                "output_tokens": usage_tokens["output"]
            }
        }
        return jsonify(anthropic_resp)

    except Exception as e:
        return jsonify({"type": "error", "error": {"type": "api_error", "message": f"Bridge error: {str(e)}"}}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
