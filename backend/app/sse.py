from typing import AsyncGenerator

async def stream_llm_response(content: str, session_id: str) -> AsyncGenerator[str, None]:
    for token in content.split():
        yield token
