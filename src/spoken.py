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
    (r'\|', ' and '), (r'–', ', '),  # noqa: RUF001 - maps en-dash to comma for the voice engine (r'—', ', '),
    (r'\*+', ''), (r'`+', ''), (r'#', ''),
    (r'\bSC\b', 'scheduled caste'), (r'\bST\b', 'scheduled tribe'),
    (r'\bNSP\b', 'the National Scholarship Portal'), (r'\bDBT\b', 'D B T'),
]

def speakify(text):
    t = str(text or '')
    for pat, rep in REPLACEMENTS:
        t = re.sub(pat, rep, t)
    t = re.sub(r'(\d{1,3}(?:,\d{3})+)', lambda m: str(int(m.group(1).replace(',', ''))), t)
    t = re.sub(r'\s+', ' ', t)
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

def render(text, use_tags=True):
    clean = speakify(text)
    sents = [s for s in re.split(r'(?<=[.!?])\s+', clean) if s.strip()]
    return (' <pauses> '.join(sents) if use_tags else ' '.join(sents))
