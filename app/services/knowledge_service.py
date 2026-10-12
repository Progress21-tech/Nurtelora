from app.db.database import connection

_STOP_WORDS={"the","and","for","with","from","that","this","your","you","are","can","may","will","when","what","how","does","only","use","information","please","contact","clinic","healthcare","provider","health","care","not","have","has","had","was","were","their","they","them","into","about","after","before","should","could","would","might","more","than","then","also","some","our","its","all","any","each","one","who","which","where","while","because","but","such","these","those","are","is","be","to","of","in","on","at","as","by","or","an","a","it","i","we","do","does","if","no","yes"}

def answer_is_supported(answer: str, approved_context: str) -> bool:
    """Fail closed when the generated English wording introduces unmatched claims."""
    if not answer.strip() or not approved_context.strip(): return False
    source_words={w.casefold() for w in __import__('re').findall(r"[A-Za-z]+",approved_context)}
    answer_words={w.casefold() for w in __import__('re').findall(r"[A-Za-z]+",answer)}-_STOP_WORDS
    if not answer_words or not answer_words.issubset(source_words): return False
    source_numbers=set(__import__('re').findall(r"\b\d+(?:\.\d+)?\b",approved_context))
    answer_numbers=set(__import__('re').findall(r"\b\d+(?:\.\d+)?\b",answer))
    return answer_numbers.issubset(source_numbers)

def retrieve_approved(text: str, language: str):
    # Simple deterministic keyword lookup; only reviewed approved rows can be returned.
    terms={w.lower() for w in text.split() if len(w)>3}
    if not terms: return []
    with connection() as c:
        rows=c.execute("SELECT * FROM knowledge_entries WHERE review_status='approved' AND language=? AND review_due_at>=CAST(CURRENT_DATE AS TEXT)",(language,)).fetchall()
    return [r for r in rows if terms & {w.lower() for w in (r['topic']+' '+r['intent']).split()}]

async def answer_question(text: str, language: str, natlas):
    entries=retrieve_approved(text,language)
    if not entries: return "I can't verify an answer from the reviewed information available to me. Please ask a qualified healthcare provider."
    context="\n".join(f"{e['topic']}: {e['approved_text']} (Source: {e['source_title']}, {e['source_url']})" for e in entries)
    try: answer=await natlas.generate_grounded_answer(text,language,context)
    except Exception: return "I can't provide a verified answer right now. Please ask a qualified healthcare provider."
    # Exact content-word and numeric checks are deliberately conservative; this does not
    # prove entailment, so clinician review remains required before enabling an FAQ.
    if not answer_is_supported(answer,context):
        return "I can't provide a verified answer right now. Please ask a qualified healthcare provider."
    return answer
