"""Deterministic conversation context.

No model rewrites the user's query. A follow-up is resolved with rules you can
read and test: pronouns and "aur/and" mark continuity, a short question that
names an aspect ("documents", "last date") is answered from the scheme already
on the table, and anything carrying a new scheme name or a new state is sent
back through retrieval unchanged.

The rule matters because a wrong rewrite can silently retrieve the wrong
scheme. It is better to treat a question as new than to force context onto it.
"""
from __future__ import annotations

import re

import places
import responder

# Continuity markers. "is scheme" is stripped as a phrase before content is
# counted, so "aur is scheme ki last date" is a follow-up even though it says
# "scheme".
PHRASES = (
    'us scheme', 'is scheme', 'yeh scheme', 'woh scheme', 'same scheme',
    'that scheme', 'this scheme', 'usi scheme', 'us scholarship', 'is scholarship',
    'uske', 'uska', 'uski', 'usko', 'usme', 'usmein', 'usse',
    'iske', 'iska', 'iski', 'isko', 'isme', 'ismein', 'isse',
    'unke', 'unka', 'unki', 'unko', 'wahi', 'usi',
)

PRONOUNS = frozenset({
    'uske', 'uska', 'uski', 'usko', 'usme', 'usmein', 'usse',
    'iske', 'iska', 'iski', 'isko', 'isme', 'ismein', 'isse',
    'unke', 'unka', 'unki', 'unko', 'wahi', 'usi',
})

FOLLOW_START = re.compile(r'^(aur|and|also|what about|phir|fir|ab)\b', re.IGNORECASE)

# Words that carry no topic. If a question is made only of these plus an
# aspect, it is safe to answer from the previous record.
FILLER = frozenset({
    'a', 'an', 'the', 'and', 'or', 'of', 'for', 'to', 'in', 'on', 'at', 'by',
    'is', 'are', 'was', 'were', 'it', 'its', 'this', 'that', 'these', 'those',
    'what', 'which', 'who', 'how', 'when', 'where', 'why', 'please', 'can',
    'could', 'would', 'should', 'do', 'does', 'did', 'my', 'me', 'i', 'we',
    'you', 'your', 'get', 'got', 'give', 'tell', 'show', 'need', 'needs',
    'also', 'more', 'any', 'some', 'about', 'there', 'here',
    'kya', 'hai', 'hain', 'ha', 'haan', 'na', 'bhi', 'abhi', 'ab',
    'ka', 'ki', 'ke', 'ko', 'mein', 'se', 'tak', 'liye', 'wala', 'wali',
    'aur', 'phir', 'fir', 'kab', 'kahan', 'kaun', 'kaunsa', 'kaunsi', 'kaunse',
    'kitna', 'kitni', 'kitne', 'kaise', 'karo', 'kare', 'karein', 'karna',
    'batao', 'bata', 'de', 'dijiye', 'chahiye', 'chaiye', 'milega',
    'milegi', 'milta', 'milti', 'hoga', 'hogi', 'hota', 'hoti', 'sakta',
    'sakti', 'sakte', 'student', 'students', 'bachche', 'bacche',
})

ASPECT_WORDS = frozenset({
    'document', 'documents', 'doc', 'docs', 'paper', 'papers', 'kagaz',
    'proof', 'proofs', 'certificate', 'certificates', 'needed', 'required',
    'eligible', 'eligibility', 'qualify', 'qualification', 'qualifications',
    'benefit', 'benefits', 'amount', 'paise', 'paisa', 'rupee', 'rupees',
    'apply', 'application', 'portal', 'renew', 'renewal', 'status', 'track',
    'deadline', 'last', 'date', 'dates', 'day', 'akhri', 'tareekh', 'tarikh',
    'labh', 'patrata',
})

GENERIC = frozenset({'scholarship', 'scholarships', 'scheme', 'schemes', 'yojana'})

CATEGORY = frozenset({
    'sc', 'st', 'obc', 'ebc', 'ews', 'minority', 'minorities', 'alpasankhyak',
    'disabled', 'handicap', 'divyang', 'girl', 'girls', 'kanya', 'beti',
    'general', 'gen',
})

COURSE = frozenset({
    '10th', '12th', 'matric', 'matriculation', 'graduation', 'graduate',
    'post', 'postmatric', 'post-matric', 'phd', 'btech', 'mbbs', 'ba', 'bsc',
    'msc', 'diploma', 'iti', 'course', 'college', 'school',
})


def _strip_phrases(query: str) -> str:
    q = ' '.join(str(query or '').lower().split())
    for phrase in PHRASES:
        q = re.sub(rf'(?<![a-z]){re.escape(phrase)}(?![a-z])', ' ', q)
    return ' '.join(q.split())


def _tokens(query: str) -> list[str]:
    return re.findall(r'[a-z0-9]+', _strip_phrases(query))


def _state_tokens(query: str) -> set[str]:
    found: set[str] = set()
    for name in places.states_in(query):
        for variant in places.STATES[name]:
            found.update(variant.split())
    return found


def residual(query: str) -> set[str]:
    """Content words left after removing aspect, filler, place and category."""
    toks = set(_tokens(query))
    toks -= _state_tokens(query)
    toks -= CATEGORY
    toks -= COURSE
    toks -= GENERIC
    toks -= ASPECT_WORDS
    toks -= FILLER
    return toks


def has_category(query: str) -> bool:
    return bool(set(_tokens(query)) & CATEGORY)


def has_course(query: str) -> bool:
    return bool(set(_tokens(query)) & COURSE)


def has_state(query: str) -> bool:
    return bool(places.states_in(query))


def is_follow_up(query: str, last) -> bool:
    if last is None or not getattr(last, 'scheme', None):
        return False
    q = ' '.join(str(query or '').lower().split())
    if not q:
        return False
    if any(re.search(rf'(?<![a-z]){re.escape(p)}(?![a-z])', q) for p in PHRASES):
        return True
    if set(_tokens(q)) & PRONOUNS:
        return True
    if FOLLOW_START.search(q):
        return True
    # A short question that is only an aspect, or only a place/category/course
    # qualifier, is continuing the current scheme.
    if not residual(q) and (responder.explicit_aspects(q) or has_state(q)
                            or has_category(q) or has_course(q)):
        return len(_tokens(q)) <= 9
    return False


def is_aspect_only(query: str) -> bool:
    """True when there is no new scheme, state, category or course in the query."""
    return not residual(query) and not has_state(query) and not has_category(query) and not has_course(query)


def rewrite(query: str, last) -> str:
    """Anchor a follow-up to the scheme on the table, but never to a new topic."""
    if last is None or not getattr(last, 'scheme', None):
        return query
    if residual(query):
        return query
    return f"{last.scheme['name']} {query}".strip()
