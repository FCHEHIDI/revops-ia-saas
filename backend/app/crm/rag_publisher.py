import logging
import json
from uuid import UUID, uuid4
from app.config import settings

try:
    import redis.asyncio as aioredis
except ImportError:
    aioredis = None

logger = logging.getLogger(__name__)

async def publish_deal_index_job(deal_id: UUID, tenant_id: UUID, content: str, metadata: dict):
    redis_url = settings.redis_url
    if not redis_url or not aioredis:
        logger.debug("RAG job: no redis_url/redis client, skipping publish.")
        return
    try:
        redis = aioredis.from_url(redis_url)
        job_id = f"job_crm_{uuid4()}"
        payload = {
            "job_id": job_id,
            "schema_version": "1.0",
            "type": "crm_entity_index",
            "priority": "low",
            "tenant_id": str(tenant_id),
            "entity_type": "deal_note",
            "entity_id": str(deal_id),
            "content": content,
            "metadata": json.dumps(metadata),
        }
        await redis.xadd("rag:index:jobs", payload)
    except Exception as e:
        logger.warning(f"RAG publish failed: {str(e)}")
