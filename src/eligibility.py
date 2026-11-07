"""Eligibility reasoner — the one question Siddha couldn't answer before.

Architecture: the LLM *extracts* a profile and *classifies* record coverage.
Siddha's code composes the spoken reply deterministically from the records and
the classification; the LLM never speaks freely, so eligibility can never be
invented. Any failure (missing key, timeout, bad JSON) makes callers fall back
to the original grounded responder unchanged.

Opt-in via LLM_API_KEY (any OpenAI-compatible endpoint — e.g. a free DeepSeek
key). When absent, this module is inert and the existing pipeline is untouched.
"""
import json
import re

import llm
import places
import spoken
from config import logger

# crude intent check — deliberately loose; false positives just mean "LLM
# classified eligibility", false negatives mean "grounded responder answered".
INTENT_RE = re.compile(
    r'(eligible|eligibility|qualify|qualifying|qualification|milegi|milega|कौनसी scheme|'
    r'पात्र|पात्रता)',
    re.IGNORECASE,
)

_PROFILE_KEYS = ('age', 'income_lakh_pa', 'category', 'state', 'course', 'marks_percent', 'girl')

PROFILE_SYSTEM = """You extract a student profile from an Indian voice query.
Output ONLY JSON with these keys (null when unknown):
{
  "age": integer or null,
  "income_lakh_pa": number or null,   # income in lakhs/year
  "category": "SC" | "ST" | "OBC" | "EBC" | "EWS" | "minority" | "GEN" | null,
  "state": state name (English spelling) | null,
  "course": e.g. "B.Tech" | "MBBS" | "12th" | "BA" | null,
  "marks_percent": number or null,
  "girl": true | false | null
}
Hindi digits must be converted. 1,50,000 rupees -> 1.5. If the query only implies a field, leave it null. Never invent a value you cannot hear.
"""



COMBINED_SYSTEM = """You are Siddha's eligibility engine. Work in two steps inside your reasoning, but output ONLY one JSON object.

Step 1 — extract the student profile JSON (age, income_lakh_pa, category, state, course, marks_percent, girl; null when unknown). Hindi digits must be converted; 1,50,000 rupees -> 1.5.

Step 2 — classify each of the 1-3 records using ONLY the provided record text (never outside knowledge):
- "eligible": the record's eligibility text clearly covers this student
- "not":     the record's eligibility text excludes this student (e.g. wrong category)
- "unsure":  the record is silent on a profile field that matters
Report the decisive field ("income_lakh_pa" | "category" | "marks_percent" | "state" | "course" | "girl" | "age" | null) and a short verbatim quote from the record in "quote". If not eligible for every record, "best": null.

Output ONLY this JSON shape:
{
  "profile": {"age": ..., "income_lakh_pa": ..., "category": ..., "state": ..., "course": ..., "marks_percent": ..., "girl": ...},
  "verdicts": [
    {"record": 1, "verdict": "eligible|not|unsure", "decisive": "... or null", "quote": "short verbatim line or null"},
    {"record": 2, "verdict": "...", "decisive": "...", "quote": "..."},
    {"record": 3, "verdict": "...", "decisive": "...", "quote": "..."}
  ],
  "best": 1 | 2 | 3 | null
}
"""

VERDICT_SYSTEM = """You are Siddha's eligibility checker. You may ONLY use the scheme
records provided below — never outside knowledge. Number the records from 1.

For each record decide:
- "eligible": the record's eligibility text clearly covers this student
- "not":     the record's eligibility text excludes this student (e.g. wrong category)
- "unsure":  the record is silent on a profile field that matters

Also report the single decisive profile field if any ("income_lakh_pa",
"category", "marks_percent", "state", "course", "girl", "age") or null.
Quote the single most relevant eligibility line verbatim in "quote".
If the student is clearly NOT eligible for every record, set "best": null.

Output ONLY JSON:
{
  "verdicts": [
    {"record": 1, "verdict": "eligible|not|unsure", "decisive": "... or null", "quote": "short verbatim line or null"},
    {"record": 2, "verdict": "...", "decisive": "...", "quote": "..."},
    {"record": 3, "verdict": "...", "decisive": "...", "quote": "..."}
  ],
  "best": 1 | 2 | 3 | null
}
"""


def intended(query):
    return bool(INTENT_RE.search(str(query or '')))


def _parse_json(text):
    text = re.sub(r'^```(?:json)?|```$', '', text.strip(), flags=re.MULTILINE).strip()
    start = text.find('{')
    if start < 0:
        return None
    try:
        return json.loads(text[start:text.rfind('}') + 1])
    except json.JSONDecodeError:
        return None


def _quote_in_record(quote, rec):
    """True when the LLM's quote is verbatim text from the record.

    The prompt asks for a verbatim line, but a model can paraphrase or invent one.
    A spoken eligibility verdict must never contain a sentence the record does not
    have, so an unverified quote falls back to the grounded responder instead."""
    if not quote:
        return True                       # no quote: the caller uses a neutral phrase
    q = re.sub(r'\s+', ' ', str(quote)).strip().lower()
    if len(q) < 8:
        return False
    blob = ' '.join(str(rec.get(k) or '') for k in ('eligibility', 'details', 'benefits', 'documents'))
    blob = re.sub(r'\s+', ' ', blob).lower()
    return q in blob


def extract_profile(query):
    raw = llm.complete(
        [{'role': 'system', 'content': PROFILE_SYSTEM},
         {'role': 'user', 'content': query}],
        max_tokens=300,
    )
    payload = _parse_json(raw)
    if not isinstance(payload, dict):
        return None
    return _normalize_profile(payload.get('profile') or payload)


def _normalize_profile(profile):
    if not isinstance(profile, dict):
        return {}
    out = {k: profile.get(k) for k in _PROFILE_KEYS}
    for key in ('income_lakh_pa', 'marks_percent'):
        if out[key] is not None:
            try:
                out[key] = float(out[key])
            except (TypeError, ValueError):
                out[key] = None
    if out['age'] is not None:
        try:
            out['age'] = int(out['age'])
        except (TypeError, ValueError):
            out['age'] = None
    return out


def advise(query, hits):
    """Return (spoken_reply, sources) when the LLM judges eligibility, else None."""
    if not hits:
        return None
    # For a scholarship-eligibility talk the decision is about education
    # records; drop labour/agriculture/etc. candidates from the judging pool
    # when education records are available.
    def _is_education(h):
        return 'education' in str(h['record'].get('category', '')).lower()

    def _slot_score(h):
        blob = ' '.join(str(h['record'].get(k) or '') for k in ('name', 'eligibility', 'category', 'details'))
        education = _is_education(h)
        return (places.category_boost(query, blob), education, h['rank_score'])

    # Prefer records that match BOTH the student's category and Education; the
    # corpus's ST/SC-flagged schemes can otherwise be out-ranked by agriwelfare
    # schemes that also mention SC/ST in passing.
    top = sorted(hits, key=_slot_score, reverse=True)[:3]
    records = []
    for i, h in enumerate(top, 1):
        r = h['record']
        eligibility = (r.get('eligibility') or '').strip()[:1200]
        records.append(
            f"Record {i} — {r['name']} ({r['level']})\n"
            f"Eligibility: {eligibility}\n"
            f"Documents: {(r.get('documents') or '').strip()[:400]}"
        )
    raw = llm.complete(
        [{'role': 'system', 'content': COMBINED_SYSTEM},
         {'role': 'user', 'content': f"Query: {query}\n\n" + '\n\n'.join(records)}],
        max_tokens=1500,
    )
    payload = _parse_json(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get('verdicts'), list):
        logger.info('eligibility_no_result reason=parse_failure')
        return None
    verdicts = {int(v.get('record') or 0): v for v in payload['verdicts']}

    def _pick():
        best = payload.get('best')
        if isinstance(best, int) and 1 <= best <= len(top):
            return best
        for i in range(1, len(top) + 1):
            if verdicts.get(i, {}).get('verdict') == 'eligible':
                return i
        return None

    pick_idx = _pick()
    if pick_idx is None:
        # All 'not' or all 'unsure' -> honest negative answer naming the closest record.
        first, v = top[0], verdicts.get(1, {})
        if v.get('verdict') == 'not':
            quote = v.get('quote')
            if not _quote_in_record(quote, first['record']):
                logger.info('eligibility_no_result reason=unverified_quote')
                return None
            reason = v.get('decisive') or 'category'
            reply = (f"Suno. {first['record']['name']} mein eligibility case jaata hai: "
                     f"record kehta hai {quote or reason}. Aap is scheme ke liye qualify nahi karte. "
                     f"Exact details scholarships.gov.in pe dikhengi.")
            sources = [{'name': h['record']['name'], 'score': h['rank_score'], 'level': h['record']['level']}
                       for h in top]
            return spoken.speakify(reply), sources
        logger.info('eligibility_no_result reason=no_eligible_or_not_pick')
        return None

    h = top[pick_idx - 1]
    v = verdicts.get(pick_idx, {})
    quote = v.get('quote')
    if not _quote_in_record(quote, h['record']):
        logger.info('eligibility_no_result reason=unverified_quote')
        return None
    quote = quote or 'eligibility detail official record mein hai'
    reply = (f"Suno. {h['record']['name']} ki eligibility ho sakti hai. "
             f"Record kehta hai, {quote}. "
             f"Documents chahiye: {h['record'].get('documents') or 'ye record mein nahi hai'}. "
             f"Exact eligibility scholarships.gov.in pe verify karein.")
    sources = [{'name': x['record']['name'], 'score': x['rank_score'], 'level': x['record']['level']}
               for x in top]
    return spoken.speakify(reply), sources
