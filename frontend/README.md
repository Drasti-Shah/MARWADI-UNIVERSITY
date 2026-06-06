# Marwadi University — Voice Agent Console (Next.js)

A React/Next.js (App Router, TypeScript) admin console for the voice agent.
It is a thin frontend over the FastAPI backend's `/api/*` endpoints.

## How it talks to the backend

The browser only ever calls the Next origin. `next.config.js` rewrites
`/api/*` → the FastAPI server, so the session cookie works with **no CORS
setup**. The backend target defaults to `http://127.0.0.1:8000` (127.0.0.1 — not
`localhost` — so Node doesn't resolve to IPv6 `::1`, which uvicorn doesn't listen on).
Override with the `BACKEND_URL` env var if your API runs elsewhere.

## Run it (development)

You need **both** servers running.

```powershell
# 1) Backend (from the project root, in its own terminal)
cd "e:\MARVADI UNIVERSITY"
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2) Frontend (this folder, in a second terminal)
cd "e:\MARVADI UNIVERSITY\frontend"
npm install        # first time only
npm run dev        # http://localhost:3000
```

Open **http://localhost:3000** → sign in (`admin` / `marwadi123`, set in the
backend `.env`).

> ngrok still points at the **backend** (`ngrok http 8000`) so Twilio can reach
> the call webhooks. The Next.js console is for humans and runs on :3000.

## Production build

```powershell
npm run build
npm run start      # serves the optimized build on :3000
```

## Structure
```
app/
  layout.tsx              root layout
  page.tsx                redirect -> /dashboard
  login/page.tsx          login screen
  (app)/layout.tsx        authenticated shell (sidebar + topbar stats + auth guard)
  (app)/dashboard/        overview: metrics, 7-day chart, outcomes donut, recent, funnel
  (app)/dialer/           keypad dialer
  (app)/leads/            leads CRM (add/edit status/delete/filter)
  (app)/campaigns/        create (incl. CSV upload) + run campaigns
  (app)/analytics/        14-day volume, outcomes, direction, funnel, campaign table
  (app)/logs/             call logs + transcript modal
components/                Sidebar, CallModal, charts (Bars/Donut/Funnel/HBars/MetricCard)
lib/                       api client + formatters/colors
```
Charts are dependency-free (pure CSS/SVG-free: flex bars, conic-gradient donuts).
