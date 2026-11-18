# OpenCode Zen OpenAI-Compatible Proxy (Deploy to Render.com)

Yeh project OpenCode Zen ke real cloud gateway (`https://opencode.ai/zen/v1`) ko ek standard OpenAI-compatible API me convert karta hai.

Aap is project ko **Render.com** par 100% Free Web Service ke tor par deploy kar sakte hain.

---

## 1. Real OpenCode Zen Endpoint Details
Is project ke andar real OpenCode endpoints configure hain:
* **Chat Completions:** `https://opencode.ai/zen/v1/chat/completions`
* **Models Catalog:** `https://opencode.ai/zen/v1/models`

---

## 2. Render.com Par Deploy Kaise Karein (Step-by-Step)

### Step 1: GitHub Par Repo Banayein
1. Apne GitHub account me ek naya repository banayein (e.g. `opencode-zen-proxy`).
2. Is folder ke saare files (`app.py`, `requirements.txt`, `Procfile`, `render.yaml`) us repository me upload kar dein:
   ```bash
   git init
   git add .
   git commit -m "OpenCode Zen Proxy for Render"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/opencode-zen-proxy.git
   git push -u origin main
   ```

### Step 2: Render.com Par Service Banayein
1. [Render Dashboard](https://dashboard.render.com/) par jayein.
2. **New +** button par click karein aur **Web Service** select karein.
3. Apni GitHub repository (`opencode-zen-proxy`) select karein.
4. Settings enter karein:
   * **Name:** `my-opencode-proxy` (koi bhi naam)
   * **Language / Environment:** `Python 3`
   * **Build Command:** `pip install -r requirements.txt`
   * **Start Command:** `gunicorn app:app`
   * **Instance Type:** `Free`
5. **Deploy Web Service** par click karein.

Render aapko ek free public HTTPS URL de dega, misal ke tor par:
`https://my-opencode-proxy.onrender.com`

---

## 3. Render Public URL Ko Kaise Use Karein?

Jab Render par deployment complete ho jaye, to aap is URL ko kisi bhi application (Cursor, Cline, Roo-Code, NextChat, Python) me as standard OpenAI use kar sakte hain:

### OpenAI Base URL:
```text
https://my-opencode-proxy.onrender.com/v1
```

### Normal cURL Request (Zero Session Headers):
```bash
curl -X POST https://my-opencode-proxy.onrender.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-mykey" \
  -d '{
    "model": "big-pickle",
    "messages": [
      {"role": "user", "content": "Hello from Render!"}
    ]
  }'
```

---

## 4. Supported Free Models:
* `big-pickle`
* `hy4-flash-free`
* `beam-free`
* `deepseek-v4.1-flash-free`
* `mimo-v2.6-flash-free`
* `longcat-2.5-free`
* `flint-40b-free`
