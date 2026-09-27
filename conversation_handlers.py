"""
conversation_handlers.py — Multi-turn Conversation Manager for Vera

Handles inbound merchant and customer turns:
1. Auto-Reply Detection (canned WhatsApp Business responses)
2. Intent Commitment Transition (switching immediately to action, no qualification)
3. Hostility / Opt-out Handling (graceful apology & exit)
4. Context-aware follow-ups
"""

import re
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


# Canned auto-reply patterns commonly seen in WhatsApp Business
AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"our team will respond shortly",
    r"we are currently (?:away|unavailable|closed)",
    r"this is an automated (?:response|message)",
    r"automated assistant",
    r"auto-reply",
    r"will get back to you",
    r"shukriya.*hamari team tak pahuncha",
    r"automated message",
    r"we have received your message",
    r"thanks for reaching out",
]

# Hostility and opt-out patterns
HOSTILITY_PATTERNS = [
    r"stop messaging",
    r"\bstop\b",
    r"unsubscribe",
    r"useless spam",
    r"\bspam\b",
    r"don'?t message",
    r"leave me alone",
    r"remove (?:my number|me)",
    r"mat bhejo",
    r"band karo",
    r"pareshan mat",
    r"fraud",
    r"report",
]

# Commitment and action intent patterns
COMMITMENT_PATTERNS = [
    r"ok lets do it",
    r"let'?s do it",
    r"whats next",
    r"what'?s next",
    r"go ahead",
    r"yes please",
    r"send me the abstract",
    r"send (?:it|details|draft)",
    r"proceed",
    r"confirm",
    r"haan kar do",
    r"chalo karte hain",
    r"mujhe judna hai",
    r"i want to join",
    r"ready to start",
    r"book it",
    r"publish it",
]

# Deferral patterns ("busy right now", "call later")
DEFERRAL_PATTERNS = [
    r"busy right now",
    r"busy now",
    r"call (?:me )?later",
    r"talk later",
    r"later please",
    r"after some time",
    r"bad me baat karte",
]


@dataclass
class ConversationState:
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    turns: List[Dict[str, Any]] = field(default_factory=list)
    auto_reply_count: int = 0
    state: str = "active"  # "active", "ended", "waiting"


def is_auto_reply(message: str, history: List[Dict[str, Any]] = None) -> bool:
    """Detect if incoming message is a canned auto-reply."""
    if is_commitment(message):
        return False
    msg_lower = message.strip().lower()
    
    # Check regex patterns
    for pat in AUTO_REPLY_PATTERNS:
        if re.search(pat, msg_lower):
            return True
            
    # Check repetition in history (same message 2+ times = canned)
    if history:
        prior_merchant_msgs = [
            turn.get("message", turn.get("msg", "")).strip().lower()
            for turn in history
            if turn.get("from_role") == "merchant" or turn.get("from") == "merchant"
        ]
        if prior_merchant_msgs.count(msg_lower) >= 2 and len(msg_lower) > 15:
            return True
            
    return False


def is_hostile(message: str) -> bool:
    """Detect hostility or opt-out intent."""
    msg_lower = message.strip().lower()
    for pat in HOSTILITY_PATTERNS:
        if re.search(pat, msg_lower):
            return True
    return False


def is_commitment(message: str) -> bool:
    """Detect explicit intent commitment to proceed."""
    msg_lower = message.strip().lower()
    for pat in COMMITMENT_PATTERNS:
        if re.search(pat, msg_lower):
            return True
    return False


def is_deferral(message: str) -> bool:
    """Detect request to wait or follow up later."""
    msg_lower = message.strip().lower()
    for pat in DEFERRAL_PATTERNS:
        if re.search(pat, msg_lower):
            return True
    return False


def handle_reply(
    conversation_id: str,
    merchant_id: Optional[str],
    customer_id: Optional[str],
    from_role: str,
    message: str,
    turn_number: int,
    history: List[Dict[str, Any]],
    merchant_context: Optional[Dict[str, Any]] = None,
    category_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Core multi-turn response engine called by POST /v1/reply.
    Returns:
        { "action": "send"|"wait"|"end", "body": "...", "cta": "...", "rationale": "..." }
    """
    msg_clean = message.strip()
    
    # 1. Check for Hostility / Opt-out
    if is_hostile(msg_clean):
        return {
            "action": "end",
            "body": "Understood, apologies for the disturbance. We won't message you again. Wishing your business the best!",
            "rationale": "Merchant signaled opt-out / hostile response; exited immediately with courteous acknowledgment."
        }
        
    # 2. Check for Auto-reply
    if is_auto_reply(msg_clean, history):
        return {
            "action": "end",
            "rationale": "Detected canned WhatsApp Business auto-reply pattern; ended conversation gracefully to avoid wasting turns."
        }

    # 3. Check for Deferral
    if is_deferral(msg_clean):
        return {
            "action": "wait",
            "wait_seconds": 3600,
            "rationale": "Merchant indicated they are busy now; backing off for 1 hour."
        }

    # 4. Check for Commitment / Action Intent
    # Crucial Rule: When merchant says "yes / let's do it / what's next", SWITCH TO ACTION MODE.
    # NEVER ask qualifying questions ("would you", "do you", "how about", "can you tell").
    if is_commitment(msg_clean):
        owner_name = ""
        biz_name = "your business"
        if merchant_context:
            identity = merchant_context.get("identity", {})
            owner_name = identity.get("owner_first_name", "")
            biz_name = identity.get("name", "your business")
            
        salutation = f"Done {owner_name}! " if owner_name else "Done! "
        action_body = (
            f"{salutation}Next steps are in motion — sending you the draft right here to confirm. "
            f"Here is the draft update for {biz_name}. Proceeding with publication as soon as you confirm."
        )
        return {
            "action": "send",
            "body": action_body,
            "cta": "binary",
            "rationale": "Detected clear commitment intent; switched immediately to action mode with confirmed next steps, zero re-qualifying."
        }

    # 5. Default Contextual In-flight Continuation
    owner_name = ""
    if merchant_context:
        owner_name = merchant_context.get("identity", {}).get("owner_first_name", "")
    prefix = f"{owner_name}, " if owner_name else ""

    return {
        "action": "send",
        "body": f"{prefix}Got it. Here is the verified next step ready for your review. Confirm with YES to proceed.",
        "cta": "binary",
        "rationale": "Acknowledged merchant input and advanced the action with a low-friction binary commitment."
    }
