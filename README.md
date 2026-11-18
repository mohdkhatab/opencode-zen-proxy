# Standalone OpenCode OpenAI Proxy for Render.com

Yeh project 100% standalone hai. Yeh Render container ke andar hi OpenCode CLI install karta hai aur local daemon start karke requests handle karta hai. Kisi external server ya domain ki zaroorat nahi hai.

---

## 1. Render.com Settings:
* **Environment:** `Python 3`
* **Build Command:** `pip install -r requirements.txt && curl -fsSL https://opencode.ai/v2/install | bash -s -- --no-modify-path`
* **Start Command:** `gunicorn app:app`
* **Instance Type:** `Free`

---

## 2. API Endpoints on Render:
* **Base URL:** `https://your-app.onrender.com/v1`
* **Chat Completions:** `POST https://your-app.onrender.com/v1/chat/completions`
* **Models Catalog:** `GET https://your-app.onrender.com/v1/models`

---

## 3. Supported Free Models:
* `big-pickle`
* `hy4-flash-free`
* `beam-free`
* `deepseek-v4.1-flash-free`
* `mimo-v2.6-flash-free`
* `longcat-2.5-free`
* `flint-40b-free`
* `nemotron-3.5-lightning-free`
