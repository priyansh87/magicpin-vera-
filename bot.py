"""
bot.py — magicpin AI Challenge: Vera Merchant Assistant Service

Implements:
1. Five HTTPS REST endpoints matching challenge-testing-brief.md:
   - GET  /v1/healthz
   - GET  /v1/metadata
   - POST /v1/context
   - POST /v1/tick
   - POST /v1/reply
2. Standalone compose() function for direct import (challenge-brief.md §7.1)
3. Concurrency-safe in-memory store for 4-contexts and active conversation history
4. Multi-turn dialog orchestration via conversation_handlers.py
"""

import os
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

from composer import compose as compose_message
from conversation_handlers import handle_reply

app = FastAPI(title="Vera Merchant Assistant", version="1.0.0")

START_TIME = time.time()

# =============================================================================
# IN-MEMORY STATE STORES
# =============================================================================
# (scope, context_id) -> {"version": int, "payload": dict}
contexts: Dict[Tuple[str, str], Dict[str, Any]] = {}

# conversation_id -> list of turns [{"from_role": str, "message": str, "ts": str}]
conversations: Dict[str, List[Dict[str, Any]]] = {}


# =============================================================================
# STANDALONE COMPOSE FUNCTION (Challenge Brief §7.1)
# =============================================================================

def compose(category: dict, merchant: dict, trigger: dict, customer: Optional[dict] = None) -> dict:
    """
    Public entry point for single-message composition.
    Inputs are dicts loaded from dataset JSON.
    Returns dict with keys: body, cta, send_as, suppression_key, rationale.
    """
    return compose_message(category, merchant, trigger, customer)


# =============================================================================
# PYDANTIC SCHEMAS
# =============================================================================

class ContextPayload(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None


class TickPayload(BaseModel):
    now: Optional[str] = None
    available_triggers: List[str] = Field(default_factory=list)


class ReplyPayload(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: Optional[str] = None
    turn_number: int


# =============================================================================
# REST ENDPOINTS
# =============================================================================

@app.get("/v1/healthz")
async def healthz():
    """Liveness probe reporting loaded context counts across all 4 scopes."""
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _), _ in contexts.items():
        if scope in counts:
            counts[scope] += 1
            
    uptime = int(time.time() - START_TIME)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "contexts_loaded": counts
    }


@app.get("/v1/metadata")
async def metadata():
    """Returns bot identity, architecture approach, and submission metadata."""
    return {
        "team_name": "Team Vera AIONE",
        "team_members": ["Priyansh"],
        "model": "openai/gpt-oss-120b (fallback: qwen/qwen3.8-27b on Groq)",
        "approach": "4-context composer powered by openai/gpt-oss-120b with zero-hallucination guardrails and Cialdini compulsion levers",
        "contact_email": "priyansh56701@gmail.com",
        "version": "1.0.0",
        "submitted_at": "2026-09-27T08:00:00Z"
    }


@app.post("/v1/context")
async def push_context(data: ContextPayload):
    """
    Ingests category, merchant, customer, or trigger context.
    Idempotent by (context_id, version).
    Rejects stale versions with HTTP 409.
    """
    key = (data.scope, data.context_id)
    current = contexts.get(key)
    
    if current is not None:
        cur_version = current.get("version", 0)
        # Idempotent re-post of the same version
        if cur_version == data.version:
            return {
                "accepted": True,
                "ack_id": f"ack_{data.context_id}_v{data.version}",
                "stored_at": datetime.now(timezone.utc).isoformat()
            }
        # Stale version rejected
        if cur_version > data.version:
            return JSONResponse(
                status_code=status.HTTP_409_CONFLICT,
                content={
                    "accepted": False,
                    "reason": "stale_version",
                    "current_version": cur_version
                }
            )

    # Store latest version
    contexts[key] = {
        "version": data.version,
        "payload": data.payload
    }
    
    return {
        "accepted": True,
        "ack_id": f"ack_{data.context_id}_v{data.version}",
        "stored_at": datetime.now(timezone.utc).isoformat()
    }


@app.post("/v1/tick")
async def tick(data: TickPayload):
    """
    Periodic wake-up: evaluates active triggers and dispatches proactive messages.
    """
    actions = []
    
    for trg_id in data.available_triggers:
        trg_entry = contexts.get(("trigger", trg_id))
        if not trg_entry:
            continue
        trg = trg_entry.get("payload", {})
        
        merchant_id = trg.get("merchant_id")
        customer_id = trg.get("customer_id")
        
        m_entry = contexts.get(("merchant", merchant_id)) if merchant_id else None
        if not m_entry:
            continue
        merchant = m_entry.get("payload", {})
        
        cat_slug = merchant.get("category_slug", "")
        cat_entry = contexts.get(("category", cat_slug))
        category = cat_entry.get("payload", {}) if cat_entry else {"slug": cat_slug}
        
        customer = None
        if customer_id:
            c_entry = contexts.get(("customer", customer_id))
            if c_entry:
                customer = c_entry.get("payload", {})
                
        # Compose message
        composed = compose(category, merchant, trg, customer)
        
        # Build action
        conv_id = f"conv_{merchant_id}_{trg_id}"
        owner_name = merchant.get("identity", {}).get("owner_first_name", "")
        
        actions.append({
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": composed.get("send_as", "vera"),
            "trigger_id": trg_id,
            "template_name": "vera_generic_v1",
            "template_params": [owner_name, merchant.get("identity", {}).get("name", ""), trg_id],
            "body": composed.get("body", ""),
            "cta": composed.get("cta", "binary"),
            "suppression_key": composed.get("suppression_key", f"{trg_id}:{merchant_id}"),
            "rationale": composed.get("rationale", "")
        })
        
    return {"actions": actions}


@app.post("/v1/reply")
async def reply(data: ReplyPayload):
    """
    Multi-turn conversation handler called when merchant or customer replies.
    """
    history = conversations.setdefault(data.conversation_id, [])
    
    # Fetch merchant and category context for personalization
    merchant_ctx = None
    category_ctx = None
    if data.merchant_id:
        m_entry = contexts.get(("merchant", data.merchant_id))
        if m_entry:
            merchant_ctx = m_entry.get("payload")
            cat_slug = merchant_ctx.get("category_slug")
            c_entry = contexts.get(("category", cat_slug))
            if c_entry:
                category_ctx = c_entry.get("payload")

    # Delegate to conversation handlers
    decision = handle_reply(
        conversation_id=data.conversation_id,
        merchant_id=data.merchant_id,
        customer_id=data.customer_id,
        from_role=data.from_role,
        message=data.message,
        turn_number=data.turn_number,
        history=history,
        merchant_context=merchant_ctx,
        category_context=category_ctx
    )
    
    # Record inbound and outbound turns in history
    history.append({
        "from_role": data.from_role,
        "message": data.message,
        "turn": data.turn_number,
        "ts": data.received_at or datetime.now(timezone.utc).isoformat()
    })
    if decision.get("action") == "send":
        history.append({
            "from_role": "bot",
            "message": decision.get("body", ""),
            "turn": data.turn_number + 1,
            "ts": datetime.now(timezone.utc).isoformat()
        })
        
    return decision


# =============================================================================
# CLI RUNNER
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"Starting Vera Assistant on port {port}...")
    uvicorn.run("bot:app", host="0.0.0.0", port=port, reload=False)
