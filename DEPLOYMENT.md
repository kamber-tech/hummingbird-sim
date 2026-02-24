# Hummingbird Sim — Deployment Guide

## Architecture

```
Browser → [Vercel] Next.js frontend → [Render] FastAPI backend → Python simulation
```

## Repos

| Repo | Purpose | URL |
|------|---------|-----|
| `kamber-tech/hummingbird-sim` | FastAPI backend + simulation modules | https://github.com/kamber-tech/hummingbird-sim |
| `kamber-tech/hummingbird-web` | Next.js frontend | https://github.com/kamber-tech/hummingbird-web |

---

## Frontend (Vercel) ✅ DEPLOYED

**Live URL:** https://hummingbird-web-xi.vercel.app

**Inspect:** https://vercel.com/kamber-techs-projects/hummingbird-web

**Pages:**
- `/` — Main simulator dashboard (mode selector, range/power sliders, results with charts)
- `/sweep` — Range sweep analysis (efficiency vs range for all atmospheric conditions)
- `/financial` — Financial model (ROI, NPV, SBIR alignment, production scaling)

**Env vars set:**
```
NEXT_PUBLIC_API_URL = https://hummingbird-sim-api.onrender.com
```

**To redeploy after code changes:**
```bash
cd /Users/admin/.openclaw/workspace/projects/hummingbird-web
git add -A && git commit -m "..." && git push
vercel --prod --yes
```

---

## Backend (Render) ⚠️ MANUAL STEP REQUIRED

The Render CLI needs browser-based workspace authentication that can't be done headlessly.

### Manual Setup (5 minutes in browser):

1. Go to: https://dashboard.render.com
2. Login as `kamber@zeitindustries.com`
3. Click **New +** → **Web Service**
4. Select **"Build and deploy from a Git repository"**
5. Connect `kamber-tech/hummingbird-sim`
6. Configure:
   - **Name:** `hummingbird-sim-api`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r api/requirements.txt`
   - **Start Command:** `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free (or Starter for always-on)
7. Click **Create Web Service**

The `render.yaml` in the repo root will be auto-detected and can also be used with:
- **New +** → **Blueprint** → connect the same repo

**Expected URL:** `https://hummingbird-sim-api.onrender.com`

### Verify after deploy:
```bash
curl https://hummingbird-sim-api.onrender.com/health
# → {"status": "ok"}

curl -X POST https://hummingbird-sim-api.onrender.com/simulate \
  -H "Content-Type: application/json" \
  -d '{"mode":"laser","range_m":2000,"power_kw":5,"condition":"clear"}'
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/simulate` | Run single scenario |
| GET | `/sweep?mode=laser&power_kw=5` | Range sweep (all conditions) |
| GET | `/safety?mode=laser&power_kw=15` | Safety analysis |
| GET | `/hardware?mode=laser&power_kw=5&range_m=2000` | Hardware BOM |
| POST | `/financial` | Financial model |

**POST /simulate body:**
```json
{
  "mode": "laser | microwave | compare",
  "range_m": 2000,
  "power_kw": 5.0,
  "condition": "clear | haze | smoke | rain"
}
```

**POST /financial body:**
```json
{
  "system_cost_usd": 500000,
  "power_kw": 2.3,
  "convoy_distance_km": 50,
  "convoy_trips_month": 4
}
```

---

## Local Development

### Backend
```bash
cd /Users/admin/.openclaw/workspace/projects/hummingbird-sim
.venv/bin/uvicorn api.main:app --port 8000 --reload

# Test
curl http://localhost:8000/health
curl -X POST http://localhost:8000/simulate \
  -H "Content-Type: application/json" \
  -d '{"mode":"laser","range_m":2000,"power_kw":5,"condition":"clear"}'
```

### Frontend
```bash
cd /Users/admin/.openclaw/workspace/projects/hummingbird-web

# Point to local API
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local

npm run dev
# → http://localhost:3000
```

---

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 16, TypeScript, Tailwind CSS v4, Recharts |
| Backend | FastAPI, Uvicorn, Python 3.11 |
| Physics | NumPy, SciPy (Gaussian beam, Friis equation, phased arrays) |
| Hosting | Vercel (frontend), Render (backend) |
| CI/CD | GitHub → Vercel auto-deploy on push |
