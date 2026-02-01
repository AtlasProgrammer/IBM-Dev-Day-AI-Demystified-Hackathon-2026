## Connecting to DataStax Astra DB (Cassandra) — example code (does not modify the project)

This file is an **implementation template** showing how to connect this prototype to **DataStax Astra DB** (Cassandra).  
You can copy these snippets into a separate module (for example, `backend/astra/`) and gradually replace the storage layer.

> Important: Astra DB is not listed as a provided service in the hackathon guide. Integration is possible if your team has its own Astra DB instance/tokens.

---

### 1) What you need from Astra DB

- **Secure Connect Bundle** (zip file) for your database
- **Application Token** (usually in the form `AstraCS:...`)
- **Keyspace** (namespace) — e.g. `interview_autopilot`

---

### 2) Dependencies (Python)

The official Cassandra driver is sufficient:

```bash
pip install cassandra-driver
```

---

### 3) Environment variables (example)

```dotenv
ASTRA_SECURE_CONNECT_BUNDLE_PATH=C:\path\to\secure-connect-<db>.zip
ASTRA_DB_TOKEN=AstraCS:...
ASTRA_KEYSPACE=interview_autopilot

# (optional) pool/timeout settings
ASTRA_CONNECT_TIMEOUT_SECONDS=10
ASTRA_REQUEST_TIMEOUT_SECONDS=30
```

> Never commit tokens/bundles to a public repository.

---

### 4) Minimal connection code (Session)

```python
from __future__ import annotations

import os
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider


def astra_session():
    bundle_path = os.environ["ASTRA_SECURE_CONNECT_BUNDLE_PATH"]
    token = os.environ["ASTRA_DB_TOKEN"]
    keyspace = os.environ.get("ASTRA_KEYSPACE")

    # For Astra DB the username is always "token", and the password is your Application Token
    auth = PlainTextAuthProvider(username="token", password=token)
    cluster = Cluster(
        cloud={"secure_connect_bundle": bundle_path},
        auth_provider=auth,
    )

    session = cluster.connect()
    if keyspace:
        session.set_keyspace(keyspace)
    return cluster, session
```

---

### 5) CQL schema (example for this prototype)

Cassandra typically requires **denormalization per query**. For a simple prototype, start with “by key” tables.

```sql
-- keyspace (if not created yet)
CREATE KEYSPACE IF NOT EXISTS interview_autopilot
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

USE interview_autopilot;

-- users
CREATE TABLE IF NOT EXISTS users (
  user_id uuid PRIMARY KEY,
  name text,
  email text,
  role text,
  slack_handle text
);

-- candidates
CREATE TABLE IF NOT EXISTS candidates (
  candidate_id uuid PRIMARY KEY,
  name text,
  email text,
  resume_text text
);

-- interviews (by interview_id)
CREATE TABLE IF NOT EXISTS interviews_by_id (
  interview_id uuid PRIMARY KEY,
  candidate_id uuid,
  candidate_name text,
  candidate_email text,
  recruiter_name text,
  recruiter_email text,
  job_title text,
  status text,
  scheduled_start timestamp,
  scheduled_end timestamp,
  video_link text
);

-- participants by interview_id
CREATE TABLE IF NOT EXISTS interview_participants_by_interview (
  interview_id uuid,
  user_id uuid,
  user_name text,
  user_email text,
  user_role text,
  PRIMARY KEY (interview_id, user_id)
);

-- feedback by interview_id
CREATE TABLE IF NOT EXISTS feedback_by_interview (
  interview_id uuid,
  user_id uuid,
  decision text,
  comment text,
  submitted_at timestamp,
  PRIMARY KEY (interview_id, user_id)
);

-- ats record by interview_id
CREATE TABLE IF NOT EXISTS ats_by_interview (
  interview_id uuid PRIMARY KEY,
  status text,
  recommendation text,
  summary text,
  updated_at timestamp
);
```

If you need an “interview list”, add a secondary table for that query, for example:

```sql
CREATE TABLE IF NOT EXISTS interviews_by_status (
  status text,
  scheduled_start timestamp,
  interview_id uuid,
  candidate_name text,
  job_title text,
  PRIMARY KEY (status, scheduled_start, interview_id)
) WITH CLUSTERING ORDER BY (scheduled_start DESC);
```

> In Cassandra this is normal practice: 2+ tables for different “screens/queries”.

---

### 6) DAO skeleton: create and read an interview

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4


@dataclass
class InterviewRow:
    interview_id: UUID
    candidate_id: UUID
    candidate_name: str
    candidate_email: str
    recruiter_name: str
    recruiter_email: str
    job_title: str
    status: str
    scheduled_start: datetime
    scheduled_end: datetime
    video_link: str


def create_interview(session, row: InterviewRow) -> None:
    session.execute(
        """
        INSERT INTO interviews_by_id (
          interview_id, candidate_id, candidate_name, candidate_email,
          recruiter_name, recruiter_email, job_title, status,
          scheduled_start, scheduled_end, video_link
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            row.interview_id,
            row.candidate_id,
            row.candidate_name,
            row.candidate_email,
            row.recruiter_name,
            row.recruiter_email,
            row.job_title,
            row.status,
            row.scheduled_start,
            row.scheduled_end,
            row.video_link,
        ),
    )


def get_interview(session, interview_id: UUID) -> InterviewRow | None:
    r = session.execute(
        "SELECT * FROM interviews_by_id WHERE interview_id = ?",
        (interview_id,),
    ).one_or_none()
    if not r:
        return None

    return InterviewRow(
        interview_id=r.interview_id,
        candidate_id=r.candidate_id,
        candidate_name=r.candidate_name,
        candidate_email=r.candidate_email,
        recruiter_name=r.recruiter_name,
        recruiter_email=r.recruiter_email,
        job_title=r.job_title,
        status=r.status,
        scheduled_start=r.scheduled_start,
        scheduled_end=r.scheduled_end,
        video_link=r.video_link,
    )


# example usage
def demo(session):
    interview_id = uuid4()
    row = InterviewRow(
        interview_id=interview_id,
        candidate_id=uuid4(),
        candidate_name="Test Candidate",
        candidate_email="candidate@example.com",
        recruiter_name="Recruiter",
        recruiter_email="recruiter@example.com",
        job_title="Backend Engineer",
        status="scheduled",
        scheduled_start=datetime.utcnow(),
        scheduled_end=datetime.utcnow(),
        video_link="https://meet.jit.si/demo",
    )
    create_interview(session, row)
    got = get_interview(session, interview_id)
    print(got)
```

---

### 7) How to integrate with the current project (without rewriting everything)

Recommended migration path:

- **Step 1**: move DB operations into a dedicated layer (DAO/Repository), so the API/orchestrator does not care whether it’s SQLite or Astra
- **Step 2**: implement an Astra DAO alongside the SQLite DAO (feature flag `DB_BACKEND=sqlite|astra`)
- **Step 3**: switch `DB_BACKEND=astra` and run an equivalent `smoke_test` scenario

If you want, I can prepare an **exact table design for the real queries** (including “interview list”, “feedback list”, “ATS by candidate”, “calendar blocks”) and propose an optimal denormalized schema for a demo.

