## watsonx Orchestrate (how to connect this project)

Per the hackathon guide, **watsonx Orchestrate must be the core component**. In this prototype, an Orchestrate agent
calls our FastAPI backend as a tool via OpenAPI.

### 1) Run the backend locally

See the root `README.md`. After startup, FastAPI is available at `http://127.0.0.1:8000`.

OpenAPI schema:

- `http://127.0.0.1:8000/openapi.json`

### 2) Create a Tool in watsonx Orchestrate (OpenAPI import)

In the Orchestrate UI:

- **Tools** → **Add tool** → **Import OpenAPI**
- paste the `openapi.json` URL (see above)
- save the tool

### 3) Create an Agent and attach the tool

Example Agent instructions to demonstrate an end-to-end scenario:

- You are “Interview Scheduling Autopilot”.
- When the recruiter provides candidate/job/interviewers/time window, call `POST /api/interviews/start`.
- Then periodically poll `GET /api/interviews/{id}` until status is `feedback_received`.
- When ready, return the final summary and ATS status to the recruiter.

### 3.1) Stronger hackathon variant: Multi-agent + Human-in-the-loop

Recommended judging scenario:

- step 1: `POST /api/scheduling/propose` → get 2–3 time slots
- step 2: ask the recruiter “which one should we approve?” (human-in-the-loop)
- step 3: `POST /api/scheduling/approve` → only after approval, create the interview

Ready playbook (instruction texts for 3–4 agents): see `orchestrate/MULTI_AGENT_PLAYBOOK.md`.

### 4) Tip: how to get candidate and interviewer IDs

Our backend provides directories:

- `GET /api/users`
- `GET /api/candidates`

### Example payload for `POST /api/interviews/start`

Use ISO datetime with timezone offset:

```json
{
  "recruiter_name": "Recruiter",
  "recruiter_email": "recruiter@example.com",
  "candidate_id": 1,
  "job_title": "Backend Engineer",
  "interviewer_user_ids": [1, 2, 3],
  "preferred_window": {
    "start": "2026-01-31T12:00:00+03:00",
    "end": "2026-01-31T18:00:00+03:00"
  },
  "duration_minutes": 60
}
```

### Important

- For demos, use **synthetic data** only (the guide prohibits real personal data).
- Deployment in the hackathon account may be unavailable — local run is OK for demo (per the guide).

