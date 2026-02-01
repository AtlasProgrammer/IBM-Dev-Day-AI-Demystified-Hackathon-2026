## Multi-agent orchestration + Human-in-the-loop (watsonx Orchestrate)

Goal: strengthen the demo and comply with the guide — **watsonx Orchestrate as the core**, our FastAPI as a **tool**.

In this variant, the “complexity” comes from:

- **multi-agent orchestration** (multiple agents in Orchestrate)
- **human-in-the-loop**: the agent does not “book immediately”; it proposes **2–3 slots** and asks for approval

---

### 0) Tool setup

1) Run the backend locally.
2) Import OpenAPI into Orchestrate:
   - `GET {BASE_URL}/openapi.json`

Useful tool endpoints:

- `GET /api/users`
- `GET /api/candidates`
- `POST /api/scheduling/propose`  ← HITL step 1
- `POST /api/scheduling/approve`  ← HITL step 2
- `GET /api/interviews/{id}`      ← monitoring

---

### 1) Agent architecture (in Orchestrate)

#### Agent A — **Coordinator (primary)**
**Role:** runs the flow, talks to the recruiter, delegates to other agents.

**Instructions (paste as Agent instructions):**
- You are the primary hiring coordinator.
- Always start by collecting: candidate_id, interviewer_user_ids, preferred_window (start/end), duration_minutes.
- Then call tool `POST /api/scheduling/propose` and get 2–3 slots.
- Show the slot options and ask the user to pick one.
- After the user chooses, call `POST /api/scheduling/approve` (pass request_id, option_id, interviewer_user_ids).
- Return the interview link (`/interviews/{id}`) and explain that feedback will be requested automatically after the interview ends.
- If the user says “reschedule / none work”, rerun `propose` with the updated window.

#### Agent B — **Scheduling Agent**
**Role:** only selects slots and formats options.

**Instructions:**
- Your role: find slots and produce 2–3 options.
- Use `POST /api/scheduling/propose`.
- Return the result as a list:
  - option_id
  - start/end
  - a brief reason (“shared availability of all interviewers”)

#### Agent C — **Ops Agent**
**Role:** monitors interview status and reminds the recruiter where to find the report.

**Instructions:**
- After getting interview_id, periodically check `GET /api/interviews/{id}`.
- When status is `feedback_received`, tell the recruiter:
  - recommendation and `/reports/{id}` link

#### Agent D — **Summarizer Agent (optional)**
**Role:** “explain” the summary for the recruiter (executive-ready), even if the backend already generated it.

**Instructions:**
- When you have a summary, rewrite it into a short structure:
  - Strengths / Risks / Recommendation
- Do not invent facts — use only the provided summary/data.

---

### 2) Human-in-the-loop flow (how it looks in chat)

1) Recruiter:
> “Schedule an interview for candidate 1 for Backend Engineer with interviewers 1,2,3, window tomorrow 12–18, 60 minutes”

2) Coordinator → calls `POST /api/scheduling/propose`
Tool response:
- request_id: 12
- options: [{option_id: 55, start:..., end:...}, {option_id: 56,...}, {option_id: 57,...}]

3) Coordinator:
> “Found 3 slots. Which one should we approve? (1) option_id=55 ... (2) option_id=56 ... (3) option_id=57 ...”

4) Recruiter:
> “Approve option 2 (option_id=56)”

5) Coordinator → calls `POST /api/scheduling/approve`
Tool response:
- interview.id = 7
- report_url = ... (appears after feedback)

6) Coordinator:
> “Done: the interview is created. Link: /interviews/7. After the interview ends, the agent will request feedback and generate the report.”

---

### 3) Ready payloads (copy into an Orchestrate tool call)

#### Get directories
- `GET /api/users`
- `GET /api/candidates`

#### HITL step 1 — propose

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
  "duration_minutes": 60,
  "option_limit": 3
}
```

#### HITL step 2 — approve

```json
{
  "request_id": 12,
  "option_id": 56,
  "interviewer_user_ids": [1, 2, 3]
}
```

---

### 4) What to tell judges (short)

- **watsonx Orchestrate** is the main orchestrator: multi-agent system + human-in-the-loop approval.
- Our FastAPI is a **set of enterprise tools** (OpenAPI) for Orchestrate.
- **watsonx.ai** (optional) generates feedback summaries and recommendations.

