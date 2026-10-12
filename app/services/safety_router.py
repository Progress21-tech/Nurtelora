"""Conservative symptom guard. Not a validated clinical triage system."""
import re

GENERIC_ESCALATION = ("I can't assess symptoms or diagnose through this service. Please contact your antenatal clinic or a qualified healthcare professional now. "
                      "If you believe this is an emergency, contact local emergency services or go to the nearest appropriate health facility.")
SYMPTOM_PATTERNS = [re.compile(p, re.I) for p in (
    r"\b(diagnos(e|is)|what is wrong with me|is this symptom|should i take|can i take|medicine for|is it safe|is it normal|what should i do about)\b",
    r"\b(bleeding|pain|hurt|convulsion|seizure|faint(ed|ing)?|breath(ing)?|dizzy|headache|swollen|fever|vomit(ing)?|fluid|discharge|water broke|contraction|baby (is )?not moving|reduced baby movement)\b")]

def requires_safety_route(text: str) -> bool:
    return any(p.search(text or "") for p in SYMPTOM_PATTERNS)

def safety_response(text: str, enabled: bool = False) -> str | None:
    if not requires_safety_route(text): return None
    # Pending professional review, only the generic human-escalation fallback is permitted.
    return GENERIC_ESCALATION
