"""Spoken-prose layer (anti-slop): converts retrieved scheme facts into
voice-safe linear text. Removes characters TTS misreads; sentence wrap;
natural <pauses> for Timbre v3.0."""
import re

REPLACEMENTS = [
    (r'Rs\.?\s*', 'rupees '), (r'₹', ' rupees '),
    (r'https?://[^\s)]+', 'the Portal'),
    (r'scholarships\.gov\.in', 'the National Scholarship Portal'),
    (r'pfms\.nic\.in', 'the PFMS portal'),
    (r'/', ' or '), (r'\(', ', '), (r'\)', ', '), (r'\[|\]', ', '),
    (r'\|', ' and '),
    ('–', ', '),  # noqa: RUF001 - en dash: a pause, not a symbol to be read
    ('—', ', '),  # em dash
    (r'\*+', ''), (r'`+', ''), (r'#', ''),
    (r'\bSC\b', 'scheduled caste'), (r'\bST\b', 'scheduled tribe'),
    (r'\bNSP\b', 'the National Scholarship Portal'), (r'\bDBT\b', 'D B T'),
]

PAUSE = ' <pauses> '


def speakify(text):
    t = str(text or '')
    for pat, rep in REPLACEMENTS:
        t = re.sub(pat, rep, t)
    t = re.sub(r'(\d{1,3}(?:,\d{3})+)', lambda m: str(int(m.group(1).replace(',', ''))), t)
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'\s+,', ',', t)  # a replaced dash/bracket must not leave "word , word"
    t = re.sub(r',\s*(,\s*)+', ', ', t).strip(' ,')
    if t and t[-1] not in '.!?':
        t += '.'
    return t


def split_sentences(text, max_chars=110):
    chunks = re.split(r'(?<=[.!?])\s+', text)
    out = []
    for c in chunks:
        c = c.strip()
        if not c:
            continue
        # hard-wrap at word boundary if oversized
        while len(c) > max_chars + 12:
            cut = c.rfind(' ', 0, max_chars)
            cut = cut if cut > 40 else max_chars
            out.append(c[:cut].strip())
            c = c[cut:].strip()
        out.append(c)
    return out


def _fit(sents, max_chars, sep):
    """Longest run of whole sentences that fits `max_chars` once joined with `sep`.

    The limit is on the finished string, tags included. Cutting a finished string
    by index can split a <pauses> tag or end mid-sentence, so the cut is only
    ever made between sentences. A first sentence that alone exceeds the limit is
    trimmed at a word boundary and closed with a full stop."""
    kept, used = [], 0
    for s in sents:
        extra = len(s) + (len(sep) if kept else 0)
        if kept and used + extra > max_chars:
            break
        kept.append(s)
        used += extra
    if kept and len(kept[0]) > max_chars:
        cut = kept[0].rfind(' ', 0, max_chars - 1)
        cut = cut if cut > 0 else max_chars - 1
        kept = [kept[0][:cut].rstrip(' ,;:.') + '.']
    return kept


def render(text, use_tags=True, max_chars=None):
    """Voice-safe text for Timbre.

    `max_chars` bounds the final string. Whole sentences only; see `_fit`."""
    clean = speakify(text)
    sents = [s for s in re.split(r'(?<=[.!?])\s+', clean) if s.strip()]
    sep = PAUSE if use_tags else ' '
    if max_chars is not None:
        sents = _fit(sents, max_chars, sep)
    return sep.join(sents)
