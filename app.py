#!/usr/bin/env python3
"""
OpenCode Zen to OpenAI-Compatible API Proxy for Render.com
---------------------------------------------------------
Features:
1. Standard OpenAI Endpoints:
   - GET  /v1/models
   - POST /v1/chat/completions
2. Two Backend Engines:
   - Engine A (Zero API Key via VPS Daemon): Routes through your live OpenCode daemon
     (e.g. https://primekhatabservices.tech) where free models work 100% reliably.
   - Engine B (Direct Zen Cloud): Routes directly to https://opencode.ai/zen/v1
     when an OPENCODE_API_KEY / Zen Key is provided.
"""

import os
import json
import time
import uuid
from flask import Flask, request, jsonify, Response
import requests

app = Flask(__name__)

# Direct Zen Gateway
ZEN_BASE_URL = os.environ.get("ZEN_BASE_URL", "https://opencode.ai/zen/v1")
ZEN_CHAT_ENDPOINT = f"{ZEN_BASE_URL}/chat/completions"
ZEN_MODELS_ENDPOINT = f"{ZEN_BASE_URL}/models"

# VPS OpenCode Daemon (Live domain where free models run without limits)
VPS_URL = os.environ.get("VPS_URL", "https://primekhatabservices.tech")

API_KEY = os.environ.get("API_KEY", "")

DEFAULT_HEADERS = {
    "User-Agent": "opencode/latest/2.3.2/opencode",
    "x-opencode-client": "opencode",
    "Content-Type": "application/json"
}

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

@app.before_request
def check_auth():
    if request.method == "OPTIONS":
        return
    if request.path in ["/", "/health"]:
        return
    if API_KEY:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token == API_KEY:
                return
        return jsonify({
            "error": {
                "message": "Invalid API key provided. Set Authorization: Bearer <API_KEY>",
                "type": "invalid_request_error",
                "code": "invalid_api_key"
            }
        }), 401

@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Api-Key"
    return response

@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "online",
        "service": "OpenCode Zen OpenAI Proxy (Render)",
        "vps_backend": VPS_URL,
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
    req_data = request.get_json(silent=True)
    if not req_data:
        return jsonify({"error": {"message": "Malformed JSON body", "type": "invalid_request_error"}}), 400

    raw_model = req_data.get("model", "big-pickle")
    model_id = raw_model.replace("opencode/", "").strip()
    if not model_id or model_id not in SUPPORTED_MODELS:
        model_id = "big-pickle"

    # Extract messages
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

    client_auth = request.headers.get("Authorization", "")
    has_real_zen_key = client_auth and not any(k in client_auth for k in ["dummy", "test", "mykey", "sk-opencode"])

    # METHOD 1: Real Zen Key provided -> Direct Zen Gateway
    if has_real_zen_key:
        upstream_headers = {
            **DEFAULT_HEADERS,
            "Authorization": client_auth
        }
        resp = requests.post(ZEN_CHAT_ENDPOINT, headers=upstream_headers, json=req_data, timeout=120)
        return Response(resp.content, status=resp.status_code, content_type="application/json")

    # METHOD 2: Zero API Key -> Route via VPS OpenCode Daemon
    try:
        # Step 1: Create session on VPS
        s_resp = requests.post(
            f"{VPS_URL}/api/session",
            json={"title": f"Render {model_id}"},
            timeout=15,
            verify=False
        )
        if s_resp.status_code not in (200, 201):
            return jsonify({"error": {"message": f"VPS daemon session error: {s_resp.text}", "type": "gateway_error"}}), 502

        session_id = s_resp.json()["data"]["id"]

        # Step 2: Switch model if not default
        if model_id != "big-pickle":
            requests.post(
                f"{VPS_URL}/api/session/{session_id}/model",
                json={"model": {"id": model_id, "providerID": "opencode"}},
                timeout=10,
                verify=False
            )

        # Step 3: Send prompt
        requests.post(
            f"{VPS_URL}/api/session/{session_id}/prompt",
            json={"text": prompt_text},
            timeout=15,
            verify=False
        )

        # Step 4: Poll for completion
        assistant_reply = ""
        usage_tokens = {"input": 0, "output": 0}
        start_time = time.time()
        timeout_seconds = 60

        while time.time() - start_time < timeout_seconds:
            time.sleep(1.0)
            m_resp = requests.get(f"{VPS_URL}/api/session/{session_id}/message", timeout=10, verify=False)
            if m_resp.status_code == 200:
                messages_list = m_resp.json().get("data", [])
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
            assistant_reply = "Request processed."

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
