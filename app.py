#!/usr/bin/env python3
"""
OpenCode Zen to OpenAI-Compatible API Proxy for Render.com
---------------------------------------------------------
Deploy this on Render.com as a Free Web Service!

Real Upstream OpenCode Zen Endpoint:
  https://opencode.ai/zen/v1/chat/completions
  https://opencode.ai/zen/v1/models
"""

import os
import json
import time
import uuid
from flask import Flask, request, jsonify, Response, stream_with_context
import requests

app = Flask(__name__)

# Real OpenCode Zen Gateway Endpoints
ZEN_BASE_URL = os.environ.get("ZEN_BASE_URL", "https://opencode.ai/zen/v1")
ZEN_CHAT_ENDPOINT = f"{ZEN_BASE_URL}/chat/completions"
ZEN_MODELS_ENDPOINT = f"{ZEN_BASE_URL}/models"

# Optional Custom API Key to protect your Render deployment
# If empty, anyone with any key (or no key) can use it
API_KEY = os.environ.get("API_KEY", "")

# Headers that mimic the official OpenCode client
DEFAULT_HEADERS = {
    "User-Agent": "opencode/latest/2.3.2/opencode",
    "x-opencode-client": "opencode",
    "Content-Type": "application/json"
}

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
        "service": "OpenCode Zen OpenAI Proxy",
        "upstream_target": ZEN_CHAT_ENDPOINT,
        "default_models": [
            "big-pickle",
            "hy4-flash-free",
            "beam-free",
            "deepseek-v4.1-flash-free",
            "mimo-v2.6-flash-free",
            "longcat-2.5-free"
        ]
    })

@app.route("/v1/models", methods=["GET"])
@app.route("/models", methods=["GET"])
def list_models():
    """Proxies to OpenCode Zen real models endpoint or returns fallback"""
    try:
        resp = requests.get(ZEN_MODELS_ENDPOINT, headers=DEFAULT_HEADERS, timeout=10)
        if resp.status_code == 200:
            return Response(resp.content, status=200, mimetype="application/json")
    except Exception:
        pass

    # Fallback free model list if upstream fetch fails
    free_models = [
        "big-pickle", "beam-free", "hy4-flash-free", "deepseek-v4.1-flash-free",
        "mimo-v2.6-flash-free", "longcat-2.5-free", "flint-40b-free"
    ]
    data = [{"id": m, "object": "model", "created": int(time.time()), "owned_by": "opencode"} for m in free_models]
    return jsonify({"object": "list", "data": data})

@app.route("/v1/chat/completions", methods=["POST"])
@app.route("/chat/completions", methods=["POST"])
def chat_completions():
    """
    Receives normal OpenAI format request,
    forwards directly to OpenCode Zen endpoint:
    https://opencode.ai/zen/v1/chat/completions
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "error": {
                "message": "Malformed JSON body",
                "type": "invalid_request_error"
            }
        }), 400

    # Model mapping (Default to big-pickle if omitted)
    model = data.get("model", "big-pickle")
    if model.startswith("opencode/"):
        model = model.replace("opencode/", "")
    data["model"] = model

    # Generate unique session markers expected by OpenCode backend
    session_id = f"ses_{uuid.uuid4().hex[:24]}"
    upstream_headers = {
        **DEFAULT_HEADERS,
        "x-opencode-session": session_id,
        "x-opencode-session-id": session_id,
        "x-session-affinity": session_id,
        "X-Session-Id": session_id,
        "session-id": session_id,
        "thread-id": session_id,
        "x-opencode-project": "1751ba12936fd079fff18cea3db58f28811c2004"
    }

    # If user passed their own Zen / OpenCode API key, forward it
    client_auth = request.headers.get("Authorization", "")
    if client_auth and not client_auth.startswith("Bearer sk-dummy"):
        upstream_headers["Authorization"] = client_auth

    stream = data.get("stream", False)

    try:
        if stream:
            # Streaming response support
            upstream_resp = requests.post(
                ZEN_CHAT_ENDPOINT,
                headers=upstream_headers,
                json=data,
                stream=True,
                timeout=120
            )

            def generate():
                for chunk in upstream_resp.iter_content(chunk_size=1024):
                    if chunk:
                        yield chunk

            return Response(
                stream_with_context(generate()),
                status=upstream_resp.status_code,
                content_type=upstream_resp.headers.get("Content-Type", "text/event-stream")
            )
        else:
            # Standard non-streaming response
            upstream_resp = requests.post(
                ZEN_CHAT_ENDPOINT,
                headers=upstream_headers,
                json=data,
                timeout=120
            )
            return Response(
                upstream_resp.content,
                status=upstream_resp.status_code,
                content_type="application/json"
            )

    except requests.exceptions.Timeout:
        return jsonify({
            "error": {
                "message": "Upstream OpenCode Zen timed out.",
                "type": "timeout_error"
            }
        }), 504
    except Exception as e:
        return jsonify({
            "error": {
                "message": f"Bridge internal error: {str(e)}",
                "type": "server_error"
            }
        }), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
