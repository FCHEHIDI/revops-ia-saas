"""AI lead scoring service.

Flow
----
1. Check Redis cache (key: ``lead_score:{tenant_id}:{contact_id}``).
2. Cache hit  → return cached ScoreLeadResponse (cached=True).
3. Cache miss →
   a. Fetch contact + open deals from the database.
   b. If ``openai_api_key`` is set: call OpenAI chat completions (JSON mode).
   c. Otherwise: apply a deterministic heuristic based on deal stages.
   d. Persist result to ``lead_scores`` table.
   e. Store in Redis with TTL.
   f. Return ScoreLeadResponse (cached=False).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.crm.models import Contact, Deal
from app.models.lead_score import LeadScore
from app.scoring.schemas import ScoreLeadResponse

logger = logging.getLogger(__name__)

# Redis cache key template
_CACHE_KEY_TPL = "lead_score:{tenant_id}:{contact_id}"

# Deal-stage weights for heuristic scoring
_STAGE_WEIGHTS: dict[str, int] = {
    "closed_won": 100,
    "negotiation": 85,
    "proposal": 65,
    "qualification": 45,
    "prospecting": 25,
    "closed_lost": 5,
}

# Default score when contact has no deals at all
_NO_DEAL_SCORE = 20


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def score_lead(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    force_refresh: bool = False,
    settings: Settings,
) -> ScoreLeadResponse:
    """Score a CRM contact and return the result.

    Args:
        db: Async SQLAlchemy session.
        tenant_id: Tenant UUID — used for cache key and DB isolation.
        contact_id: Contact to score.
        force_refresh: When True, bypass Redis cache.
        settings: Application settings (redis_url, openai_api_key, etc.).

    Returns:
        ScoreLeadResponse with score, reasoning, and recommended_action.

    Raises:
        ValueError: If the contact is not found in the database.
    """
    cache_key = _CACHE_KEY_TPL.format(tenant_id=tenant_id, contact_id=contact_id)

    # 1. Try Redis cache
    if not force_refresh and settings.redis_url:
        cached = await _get_cache(settings.redis_url, cache_key)
        if cached:
            logger.debug("score_lead: cache hit for %s", cache_key)
            return ScoreLeadResponse(**cached, cached=True)

    # 2. Fetch contact
    result = await db.execute(
        select(Contact).where(
            Contact.id == contact_id,
            Contact.org_id == tenant_id,
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        raise ValueError(f"Contact {contact_id} not found for tenant {tenant_id}")

    # 3. Fetch open deals for this contact
    deal_result = await db.execute(
        select(Deal).where(
            Deal.contact_id == contact_id,
            Deal.org_id == tenant_id,
        )
    )
    deals = deal_result.scalars().all()

    # 4. Score via LLM or heuristic
    if settings.openai_api_key:
        score, reasoning, recommended_action, model_used = await _score_llm(
            contact=contact, deals=list(deals), api_key=settings.openai_api_key
        )
    else:
        score, reasoning, recommended_action, model_used = _score_heuristic(
            contact=contact, deals=list(deals)
        )

    # 5. Persist to DB
    row = LeadScore(
        id=uuid4(),
        tenant_id=tenant_id,
        contact_id=contact_id,
        score=score,
        reasoning=reasoning,
        recommended_action=recommended_action,
        model_used=model_used,
        cache_key=cache_key,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    # 6. Store in Redis
    if settings.redis_url:
        payload = {
            "contact_id": str(contact_id),
            "score": score,
            "reasoning": reasoning,
            "recommended_action": recommended_action,
            "model_used": model_used,
            "created_at": row.created_at.isoformat(),
        }
        await _set_cache(settings.redis_url, cache_key, payload, settings.lead_score_ttl_seconds)

    return ScoreLeadResponse(
        contact_id=contact_id,
        score=score,
        reasoning=reasoning,
        recommended_action=recommended_action,
        model_used=model_used,
        cached=False,
        created_at=row.created_at,
    )


# ---------------------------------------------------------------------------
# LLM scoring — OpenAI chat completions (JSON mode)
# ---------------------------------------------------------------------------

_LLM_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = """You are a B2B sales analyst. Given a CRM contact profile and their associated deals,
output a JSON object with exactly these keys:
  "score": integer 0-100 (lead quality; 100 = highest priority)
  "reasoning": string, 1-2 sentences max, explaining the score
  "recommended_action": string, short action (e.g. "Schedule demo", "Send nurture email", "Follow up on proposal")
Respond with JSON only, no markdown."""


async def _score_llm(
    *,
    contact: Contact,
    deals: list[Deal],
    api_key: str,
) -> tuple[int, str, str, str]:
    """Call OpenAI to produce a lead score.

    Args:
        contact: The CRM Contact row.
        deals: List of Deal rows for this contact.
        api_key: OpenAI API key.

    Returns:
        Tuple of (score, reasoning, recommended_action, model_name).

    Raises:
        RuntimeError: If the LLM response cannot be parsed; falls back to heuristic.
    """
    deal_summaries = [
        f"- {d.title} (stage={d.stage}, amount={d.amount} {d.currency}, "
        f"probability={d.probability}%)"
        for d in deals
    ] or ["(no open deals)"]

    user_msg = (
        f"Contact: {contact.first_name} {contact.last_name}, "
        f"title={contact.job_title or 'unknown'}, "
        f"status={contact.status}\n"
        f"Deals:\n" + "\n".join(deal_summaries)
    )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_msg},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                    "max_tokens": 150,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            score = max(0, min(100, int(parsed["score"])))
            return score, str(parsed["reasoning"]), str(parsed["recommended_action"]), _LLM_MODEL
    except Exception as exc:
        logger.warning("score_lead LLM failed (%s), falling back to heuristic", exc)
        return _score_heuristic(contact=contact, deals=deals)


# ---------------------------------------------------------------------------
# Heuristic fallback — no LLM required
# ---------------------------------------------------------------------------


def _score_heuristic(
    *,
    contact: Contact,
    deals: list[Deal],
) -> tuple[int, str, str, str]:
    """Deterministic lead score based on deal stages.

    Args:
        contact: The CRM Contact row.
        deals: List of Deal rows for this contact.

    Returns:
        Tuple of (score, reasoning, recommended_action, "heuristic").
    """
    if not deals:
        score = _NO_DEAL_SCORE
        reasoning = "No active deals found; low engagement signal."
        action = "Send discovery email"
    else:
        best_stage = max(
            deals, key=lambda d: _STAGE_WEIGHTS.get(d.stage, 0)
        ).stage
        score = _STAGE_WEIGHTS.get(best_stage, _NO_DEAL_SCORE)
        deal_count = len(deals)
        # Boost slightly for multiple deals
        if deal_count > 1:
            score = min(100, score + 5)
        reasoning = (
            f"Contact has {deal_count} deal(s); best stage is '{best_stage}'."
        )
        action = _action_for_stage(best_stage)

    return score, reasoning, action, "heuristic"


def _action_for_stage(stage: str) -> str:
    """Map deal stage to a recommended next action.

    Args:
        stage: Deal stage string.

    Returns:
        Short human-readable action recommendation.
    """
    return {
        "closed_won": "Upsell / cross-sell opportunity",
        "negotiation": "Push to close — send contract",
        "proposal": "Follow up on proposal",
        "qualification": "Schedule demo",
        "prospecting": "Send nurture email",
        "closed_lost": "Re-engage after 90 days",
    }.get(stage, "Follow up")


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------


async def _get_cache(redis_url: str, key: str) -> dict | None:
    """Fetch a JSON-encoded lead score from Redis.

    Args:
        redis_url: Redis connection URL.
        key: Cache key to look up.

    Returns:
        Parsed dict if found, None otherwise.
    """
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(redis_url, decode_responses=True)
        try:
            raw = await r.get(key)
        finally:
            await r.aclose()
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Redis get failed for %s: %s", key, exc)
    return None


async def _set_cache(redis_url: str, key: str, payload: dict, ttl: int) -> None:
    """Store a JSON-encoded lead score in Redis with TTL.

    Args:
        redis_url: Redis connection URL.
        key: Cache key.
        payload: Dict to serialize as JSON.
        ttl: Expiry in seconds.
    """
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(redis_url, decode_responses=True)
        try:
            await r.set(key, json.dumps(payload), ex=ttl)
        finally:
            await r.aclose()
    except Exception as exc:
        logger.warning("Redis set failed for %s: %s", key, exc)
