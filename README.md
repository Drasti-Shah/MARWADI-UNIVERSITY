# Marwadi University – Admission Voice Agent (Demo)

A Gujarati voice agent that takes a phone call, asks for the student's **latest
qualification**, **recommends a matching degree** at Marwadi University, and reads
out the key details (duration, fees, eligibility, required documents).

**Stack**
- **Twilio** – telephony (turn-based `<Record>` + `<Play>`)
- **Bhashini** – Gujarati **ASR**, **translation**, **TTS** (1 call inbound, 1 call outbound for low latency)
- **OpenAI GPT-4o-mini** – the advisor brain (reasons in English)
- **FastAPI** – webhook server
- **ngrok** – public tunnel to your local server

```
Caller (Gujarati)
   │  speaks
   ▼
Twilio  ──<Record>──▶  /process
   │                      │ download WAV
   │                      ▼
   │            Bhashini ASR + translate (gu → en)
   │                      ▼
   │              GPT-4o-mini advisor (English)
   │                      ▼
   │            Bhashini translate + TTS (en → gu)  →  reply.wav
   ◀──<Play> reply.wav──┘  then <Record> next turn
```

---

## 1. Setup

```powershell
# from the project root: e:\Marvadi University
copy .env.example .env       # then edit .env with your keys
```

Fill in `.env`:
- `OPENAI_API_KEY`
- `BHASHINI_USER_ID`, `BHASHINI_API_KEY` (from https://bhashini.gov.in/ulca → Profile → API key)
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`
- `PUBLIC_BASE_URL` = your ngrok https URL (set this **after** step 3)

## 2. Run the server

```powershell
.\run.ps1
```
(or manually: `python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt; uvicorn app.main:app --reload`)

## 3. Open the ngrok tunnel (second terminal)

```powershell
ngrok http 8000
```
Copy the `https://....ngrok-free.app` URL into `.env` as `PUBLIC_BASE_URL`, then
restart the server so it serves audio links on that URL.

## 4. Point Twilio at the webhook

In the [Twilio Console](https://console.twilio.com) → your Voice number →
**A call comes in**:
- Webhook: `https://<your-ngrok>.ngrok-free.app/voice`  (HTTP **POST**)
- (optional) Status callback: `https://<your-ngrok>.ngrok-free.app/status`

## 5. Call the number and talk in Gujarati 🎉

Try: *“મેં બારમું વિજ્ઞાન પૂરું કર્યું છે”* (“I have completed 12th Science”)
→ the agent recommends B.Tech / B.Pharm etc. with fees and documents.

---

## Data

`data/degrees.json` holds **10 degrees** in key-value format with both English and
Gujarati (`*_gu`) fields: `year, degree_name, fees, eligibility, required_documents,
duration, suitable_for, highlights`.

- `python scripts/scrape_degrees.py` – best-effort scrape of public Marwadi sources (prints findings to review).
- `python -m scripts.translate_degrees` – regenerate the Gujarati fields via Bhashini NMT.

> The fees/eligibility are representative demo figures compiled from public
> aggregators. Verify against the official site before quoting to real applicants.

---

## Latency notes
- Pipeline config (Bhashini service ids + endpoint) is fetched **once** at startup and cached.
- Inbound = **one** Bhashini call (ASR + translation chained); outbound = **one** call (translation + TTS chained).
- A single keep-alive HTTP/2 client is reused across turns.
- `<Record timeout=3>` ends a turn after 3s of silence; TTS is rendered at 8 kHz (telephony) to cut size.
- The greeting is pre-synthesized and cached on disk.

## Web console (Next.js)

The admin console is a separate **Next.js app** in [`frontend/`](frontend/) (see
[frontend/README.md](frontend/README.md) to run it on `http://localhost:3000`).
The FastAPI server is **API-only** — its root (`/`) redirects to the console
(`FRONTEND_URL`, default `http://localhost:3000`).

Sign in with `admin` / `marwadi123` (set `ADMIN_USERNAME` / `ADMIN_PASSWORD` in
`.env`). The console has six sections:

- **Dashboard** – metrics, 7-day call chart, outcomes donut, recent calls, lead funnel.
- **Dialer** – keypad to place a single outbound call.
- **Leads** – auto-captured from calls + manual add/edit-status/delete/filter.
- **Campaigns** – type or **upload a CSV** of numbers (auto-extracted from any
  column) and dial them sequentially; live progress per number.
- **Analytics** – 14-day volume, outcomes, direction split, lead funnel, campaign table.
- **Call Logs** – every call with status, duration, and the full Gujarati↔English
  transcript (click a row).

Auth is a cookie session: `/api/*` requires login, while the Twilio webhooks
(`/voice`, `/process`, `/await`, `/status`) stay public so calls keep working.
All data is persisted in `data/app.db` (SQLite). The Next.js app proxies
`/api/*` to this server, so cookies work with no CORS setup.

### REST API
```
POST /api/call                 {number}                 -> place an outbound call
GET  /api/calls                                          -> recent call logs
GET  /api/calls/{sid}                                    -> call detail + transcript
POST /api/campaigns            {name, numbers[]}         -> create a campaign
GET  /api/campaigns                                      -> campaigns + progress
GET  /api/campaigns/{id}                                 -> campaign detail
POST /api/campaigns/{id}/start                           -> start dialing
GET  /api/leads | POST /api/leads | PATCH/DELETE /api/leads/{id}  -> leads CRUD
GET  /api/overview | GET /api/analytics                  -> dashboard + analytics
GET  /api/stats                                          -> top-bar counters
POST /api/login | POST /api/logout                       -> session auth
```

> Trial Twilio accounts can only call **verified** numbers — verify each
> campaign number in the Twilio console first.

## Project layout
```
app/
  main.py          FastAPI + Twilio webhooks (/voice, /process, /await, /status); API-only root
  api.py           JSON REST API (dialer, campaigns, leads, analytics)
  auth.py          cookie-session auth for the console
  dialer.py        outbound call placement + sequential campaign runner
  db.py            SQLite persistence (calls, transcripts, campaigns, leads)
  bhashini.py      Bhashini ASR / translate / TTS client (+ float->PCM for Twilio)
  openai_agent.py  GPT-4o-mini advisor (JSON: {reply, end})
  degrees.py       loads dataset + builds the LLM catalog
  config.py        env config + assert_ready()
frontend/          Next.js admin console (see frontend/README.md)
data/degrees.json  10 scraped degrees (en + gu)
data/app.db        SQLite store (auto-created; git-ignored)
scripts/           scrape + Bhashini-translate + smoke/webhook tests + place_call
static/audio/      generated TTS wav files (served to Twilio)
```

## Turn flow (low-latency)
```
/voice    -> play greeting, <Record> caller
/process  -> start background work (download->ASR->advisor->TTS),
             play a short filler immediately, <Redirect> to /await
/await    -> play the reply as soon as it's ready (else brief hold + poll),
             then <Record> next turn, or <Hangup>
```
