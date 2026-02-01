from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

import httpx

from backend.core.config import settings
from backend.models import ATSRecommendation, FeedbackDecision

try:
    from ibm_watsonx_ai.foundation_models import ModelInference
except Exception:
    ModelInference = None


@dataclass(frozen=True)
class FeedbackItem:
    interviewer_name: str
    decision: FeedbackDecision
    comment: str


@dataclass(frozen=True)
class SummaryResult:
    strengths: list[str]
    risks: list[str]
    recommendation: ATSRecommendation
    narrative: str


def _mock_summary(items: list[FeedbackItem]) -> SummaryResult:
    passes = sum(1 for i in items if i.decision == FeedbackDecision.pass_)
    fails = sum(1 for i in items if i.decision == FeedbackDecision.fail)
    needs = sum(1 for i in items if i.decision == FeedbackDecision.need_more_info)

    if passes == 0 and fails == 0 and needs == 0:
        rec = ATSRecommendation.insufficient_data
    elif fails >= 2:
        rec = ATSRecommendation.no_hire
    elif passes >= 2 and fails == 0:
        rec = ATSRecommendation.hire
    elif fails == 0 and (passes >= 1 and needs >= 1):
        rec = ATSRecommendation.mixed
    else:
        rec = ATSRecommendation.mixed

    strengths: list[str] = []
    risks: list[str] = []
    for it in items:
        c = (it.comment or "").strip()
        if not c:
            continue
        if it.decision == FeedbackDecision.pass_:
            strengths.append(c)
        elif it.decision == FeedbackDecision.fail:
            risks.append(c)
        else:
            risks.append(c)

    narrative = "\n".join(
        [
            "Automatic summary (mock):",
            f"- Pass: {passes}, Fail: {fails}, Need more info: {needs}",
            "- Key comments:",
            *[f"  - {it.interviewer_name}: {it.decision.value} — {(it.comment or '').strip()}" for it in items],
        ]
    )
    return SummaryResult(strengths=strengths[:5], risks=risks[:5], recommendation=rec, narrative=narrative)


async def _watsonx_summary(*, candidate_name: str, job_title: str, items: list[FeedbackItem]) -> SummaryResult:
    if not ModelInference:
        return _mock_summary(items)

    if not (settings.watsonx_api_key and settings.watsonx_url and settings.watsonx_project_id):
        return _mock_summary(items)

    model_id = settings.watsonx_model_id or "ibm/granite-13b-chat-v2"
    feedback_text = "\n".join(
        [
            f"- {i.interviewer_name}: {i.decision.value}. {i.comment}".strip()
            for i in items
        ]
    )
    prompt = (
        "You are a recruiting assistant. Consolidate interview feedback for the candidate.\n"
        "Return ONLY valid JSON with the following fields:\n"
        '  "strengths": [strings], "risks": [strings], '
        '"recommendation": "Hire"|"No Hire"|"Mixed / Need debrief"|"Insufficient data", '
        '"narrative": string\n'
        "Language: English.\n\n"
        f"Candidate: {candidate_name}\n"
        f"Job: {job_title}\n"
        "Feedback:\n"
        f"{feedback_text}\n"
    )

    def _call() -> dict:
        mi = ModelInference(
            model_id=model_id,
            credentials={"apikey": settings.watsonx_api_key, "url": settings.watsonx_url},
            project_id=settings.watsonx_project_id,
        )
        resp = mi.generate_text(
            prompt=prompt,
            params={
                "decoding_method": "greedy",
                "max_new_tokens": 500,
                "temperature": 0.2,
            },
        )
        if isinstance(resp, str):
            return json.loads(resp)
        if isinstance(resp, dict):
            text = (
                resp.get("results", [{}])[0].get("generated_text")
                if isinstance(resp.get("results"), list)
                else resp.get("generated_text")
            )
            if isinstance(text, str):
                return json.loads(text)
            return resp
        return json.loads(str(resp))

    try:
        obj = await asyncio.to_thread(_call)
    except Exception:
        try:
            obj = _call()
        except Exception:
            return _mock_summary(items)

    rec_map = {
        "Hire": ATSRecommendation.hire,
        "No Hire": ATSRecommendation.no_hire,
        "Mixed / Need debrief": ATSRecommendation.mixed,
        "Insufficient data": ATSRecommendation.insufficient_data,
    }

    return SummaryResult(
        strengths=list(obj.get("strengths") or [])[:5],
        risks=list(obj.get("risks") or [])[:5],
        recommendation=rec_map.get(obj.get("recommendation"), ATSRecommendation.mixed),
        narrative=str(obj.get("narrative") or "").strip(),
    )


async def _openai_summary(*, candidate_name: str, job_title: str, items: list[FeedbackItem]) -> SummaryResult:
    if not settings.openai_api_key:
        return _mock_summary(items)

    prompt = {
        "candidate": candidate_name,
        "job_title": job_title,
        "feedback": [
            {"interviewer": i.interviewer_name, "decision": i.decision.value, "comment": i.comment}
            for i in items
        ],
        "output_schema": {
            "strengths": ["..."],
            "risks": ["..."],
            "recommendation": "Hire|No Hire|Mixed / Need debrief|Insufficient data",
            "narrative": "...",
        },
    }

    system = (
        "You are a recruiting assistant. Consolidate interview feedback for the candidate. "
        "Return ONLY valid JSON strictly matching output_schema. Language: English."
    )

    async with httpx.AsyncClient(timeout=25.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": settings.openai_model,
                "temperature": 0.2,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
                ],
                "response_format": {"type": "json_object"},
            },
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        obj = json.loads(content)

    rec_map = {
        "Hire": ATSRecommendation.hire,
        "No Hire": ATSRecommendation.no_hire,
        "Mixed / Need debrief": ATSRecommendation.mixed,
        "Insufficient data": ATSRecommendation.insufficient_data,
    }

    return SummaryResult(
        strengths=list(obj.get("strengths") or [])[:5],
        risks=list(obj.get("risks") or [])[:5],
        recommendation=rec_map.get(obj.get("recommendation"), ATSRecommendation.mixed),
        narrative=str(obj.get("narrative") or "").strip(),
    )


async def summarize_feedback(
    *,
    candidate_name: str,
    job_title: str,
    items: list[FeedbackItem],
) -> SummaryResult:
    if settings.mock_llm or settings.llm_provider == "mock":
        return _mock_summary(items)

    if settings.llm_provider == "watsonx":
        return await _watsonx_summary(candidate_name=candidate_name, job_title=job_title, items=items)

    if settings.llm_provider == "openai":
        return await _openai_summary(candidate_name=candidate_name, job_title=job_title, items=items)

    return _mock_summary(items)

