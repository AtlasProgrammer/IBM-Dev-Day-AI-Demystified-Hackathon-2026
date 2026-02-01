from __future__ import annotations

from itsdangerous import BadSignature, URLSafeSerializer

from backend.core.config import settings


def _serializer() -> URLSafeSerializer:
    return URLSafeSerializer(settings.secret_key, salt="feedback-token-v1")


def make_feedback_token(*, interview_id: int, user_id: int) -> str:
    return _serializer().dumps({"interview_id": interview_id, "user_id": user_id})


def parse_feedback_token(token: str) -> tuple[int, int]:
    try:
        data = _serializer().loads(token)
    except BadSignature as e:
        raise ValueError("invalid token") from e

    interview_id = int(data.get("interview_id"))
    user_id = int(data.get("user_id"))
    return interview_id, user_id

