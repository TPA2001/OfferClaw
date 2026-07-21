import httpx
import json
import logging

logger = logging.getLogger("offerclaw.llm")


async def chat_json(system: str, user: str) -> dict:
    """
    LLM chat completion that returns JSON
    
    Args:
        system: System prompt
        user: User prompt
        
    Returns:
        dict: JSON response
    """
    # Mock implementation for demo
    # In production, replace with actual LLM API call
    logger.info(f"LLM request - System: {system[:50]}...")
    logger.info(f"LLM request - User: {user[:100]}...")
    
    # Return mock JSON for now
    return {"mappings": []}