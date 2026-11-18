# Standalone OpenAI & Anthropic Compatible OpenCode Proxy for Render.com

Yeh project 100% standard OpenAI-Compatible aur Anthropic-Compatible APIs provide karta hai. Isme saare free OpenCode models, specific model lookup endpoint, Anthropic `/v1/messages` endpoint, aur API Key authentication shamil hai.

---

## 1. Endpoints Overview

| Method | Endpoint | Format | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/v1/models` | OpenAI | Sabhi available free models ki list return karta hai. |
| `GET` | `/v1/models/<model_id>` | OpenAI | Kisi specific model ki detail return karta hai (e.g. `/v1/models/big-pickle`). |
| `POST` | `/v1/chat/completions` | OpenAI | Standard OpenAI Chat Completion (Streaming aur Non-streaming dono supported). |
| `POST` | `/v1/messages` | Anthropic | Standard Anthropic Messages API (Streaming aur Non-streaming dono supported). |
| `GET` | `/health` | Status | Server status aur internal daemon check. |

---

## 2. API Key Authentication

Boht saare tools (Cursor, Claude Dev, Cline, Roo-Code, NextChat) me API Key field compulsory hoti hai.
* **OpenAI Tools:** `Authorization: Bearer sk-opencode-free`
* **Anthropic Tools:** `x-api-key: sk-ant-free` (ya `Authorization: Bearer sk-ant-free`)
* **Custom API Key (Optional):** Agar aap chahein to Render Dashboard par Environment Variable me `CUSTOM_API_KEY="sk-my-secret-key"` set kar sakte hain, to sirf wahi key allow hogi.

---

## 3. All 11 Supported Free Models:

1. `big-pickle`
2. `hy4-flash-free`
3. `beam-free`
4. `deepseek-v4.1-flash-free`
5. `longcat-2.5-free`
6. `flint-40b-free`
7. `mimo-v2.6-flash-free`
8. `nemotron-3.5-lightning-free`
9. `nemotron-3.5-super-vl-free`
10. `iceman-free`
11. `inkling-2-small-free`

*(Har model ke aage `opencode/` laga kar bhi call kiya ja sakta hai, jaise `opencode/big-pickle`).*

---

## 4. Usage Examples (cURL)

### A. OpenAI Model List Check:
```bash
curl https://your-app.onrender.com/v1/models \
  -H "Authorization: Bearer sk-opencode-free"
```

### B. OpenAI Single Model Detail:
```bash
curl https://your-app.onrender.com/v1/models/big-pickle \
  -H "Authorization: Bearer sk-opencode-free"
```

### C. OpenAI Chat Completion:
```bash
curl -X POST https://your-app.onrender.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-opencode-free" \
  -d '{
    "model": "big-pickle",
    "messages": [
      {"role": "user", "content": "Hello, write 1 sentence."}
    ]
  }'
```

### D. Anthropic Messages API:
```bash
curl -X POST https://your-app.onrender.com/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: sk-ant-free" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "big-pickle",
    "messages": [
      {"role": "user", "content": "Hello Anthropic!"}
    ]
  }'
```
