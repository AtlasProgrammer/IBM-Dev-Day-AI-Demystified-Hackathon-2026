## Interview Scheduling Autopilot & Coordinator (Prototype)

Working end-to-end prototype of an agent that:

- accepts a recruiter request (candidate, job, interviewers, time windows)
- finds a shared available slot (mock calendars)
- “creates an interview” and sends invitations (email/Slack in mock mode or via real tokens)
- sends a reminder 1 hour before
- collects feedback via unique links
- generates a summary (LLM: mock / OpenAI / IBM watsonx, if keys are provided)
- updates the “ATS” in SQLite and shows the final report

### Quick start (Windows / PowerShell)

1) Install Python 3.11+.

2) Create and activate a venv:

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3) Install dependencies:

```bash
pip install -r backend\requirements.txt
```

4) Copy env:

```bash
copy backend\.env.example backend\.env
```

5) Run the server:

```bash
python -m backend
```

Open in your browser:

- Recruiter UI: `http://127.0.0.1:8000/`
- Admin / interviews: `http://127.0.0.1:8000/interviews`

### Demo scenario

- In the main form, select a job, a candidate, and interviewers.
- The agent will pick a slot, create the interview, and send “invitations” (by default, to the server logs).
- After the interview ends, the system requests feedback from each interviewer (unique links).
- When feedback is collected (or timeout), it generates a summary and updates the “ATS”.

### Integrations

In hackathon mode, everything works end-to-end using mock integrations.

Optionally, you can connect:

- Slack Incoming Webhook (message delivery)
- Email via SMTP (real delivery)
- LLM (OpenAI or IBM watsonx.ai) for summary generation

See `backend/.env.example`.

### IBM Dev Day requirements (important)

Per the hackathon guide, **watsonx Orchestrate must be the core component**, otherwise the solution may not pass judging.
In this repository:

- our `backend` is a **tool** that the Orchestrate agent calls via API
- Orchestrate connects to our API via **OpenAPI** (FastAPI serves the schema automatically)
- summary generation supports **IBM watsonx.ai** (via the official Python SDK) + a fallback to mock

You can run and demo locally (the guide explicitly notes that deployment in the hackathon account may be unavailable).

Data note: use **synthetic/test** names/emails only, no real personal data.

Instructions for connecting to Orchestrate: see `orchestrate/README.md`.

### Structure

- `backend/` — FastAPI + SQLite + background jobs

