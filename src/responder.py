"""Siddha responder - grounded strictly in the myScheme corpus.
Voice-safe output: short sentences with <pauses> tags for Timbre v3.0."""
import re

import places

ASPECT_KEYS = {
    'documents': ['document', 'paper', 'kagaz', 'needed', 'proof', 'certificate', 'दस्तावेज़'],
    'eligibility': ['eligible', 'eligibility', 'qualification', 'who can', 'patricia', 'kaise eligible', 'patr', 'पात्रता'],
    'benefit': ['benefit', 'amount', 'kitna', 'paisa', 'paise', 'rupees', 'rupee', 'लाभ'],
    'apply': ['apply', 'portal', 'nsp', 'आवेदन'],
    'renewal': ['renew', 'renewal', 'purana'],
    'status': ['status', 'track', 'application id'],
}

def classify_aspects(q):
    ql = q.lower()
    hits = [a for a, ks in ASPECT_KEYS.items() if any(k in ql for k in ks)]
    return hits or ['eligibility', 'benefit', 'documents', 'apply']

TRAILING_STOPWORDS = frozenset({
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
    'in', 'into', 'is', 'of', 'on', 'or', 'the', 'to', 'with',
})

# myScheme stores many document lists as unpunctuated concatenations
# ("Aadhaar Card Caste Certificate Income Certificate"). Without separators
# Timbre reads them as one long phrase, which is the opposite of natural.
DOCUMENT_TERMS = (
    'Aadhaar Card', 'Caste Certificate', 'Income Certificate', 'Domicile Certificate',
    'Residence Certificate', 'Birth Certificate', 'Bonafide Certificate',
    'Disability Certificate', 'Transfer Certificate', 'Migration Certificate',
    'Bank Account Details', 'Bank Details', 'Passport-sized Photograph',
    'Passport Size Photograph', 'Educational Documents', 'Self-attested Documents',
    'Proof of Admission', 'Income Declaration', 'Fee Receipt', 'Admission Letter',
    'Mark Sheet', 'Marksheet', 'Ration Card', 'Voter ID', 'PAN Card',
    'Photograph', 'Signature',
)
_TERM_RE = re.compile(
    '|'.join(re.escape(t) for t in sorted(DOCUMENT_TERMS, key=len, reverse=True)),
    re.IGNORECASE,
)


def _separate_documents(text):
    """Insert commas between concatenated document names; leave prose alone."""
    if not text or re.search(r'[.,;:]', text):
        return text
    pieces, cursor = [], 0
    for match in _TERM_RE.finditer(text):
        between = text[cursor:match.start()].strip(' ,')
        if pieces:
            low = between.lower()
            if not between:
                pieces.append(', ')
            elif low in {'and', 'or', '&'} or low.endswith((' and', ' or')):
                pieces.append(f' {between} ')
            else:
                pieces.append(f', {between}, ')
        elif between:
            pieces.append(between + ' ')
        pieces.append(match.group(0))
        cursor = match.end()
    tail = text[cursor:].strip(' ,')
    if tail:
        pieces.append(', ' + tail)
    return ''.join(pieces).strip(' ,')


def _clean(raw, cap=160):
    t = re.sub(r'\s+', ' ', str(raw or '')).strip(' .,')
    t = re.sub(r'^(Documents Required?|Eligibility( Criteria)?|Benefits?|How to Apply|Application|Details)\s*:?\s*',
               '', t, flags=re.IGNORECASE).strip(' .,')
    if len(t) > cap:
        # Cut on a word boundary, then drop any dangling preposition so the
        # voice never says "...fee receipt from" before switching sentence.
        words = t[:cap].rsplit(' ', 1)[0].rstrip(' .,;:').split()
        while words and words[-1].lower().strip('.,;:') in TRAILING_STOPWORDS:
            words.pop()
        t = ' '.join(words)
    t = t.rstrip(' .,;:')
    if t and t[-1] not in '.!?':
        t += '.'
    return t

def compose(rec, aspects):
    out = []
    if 'eligibility' in aspects:
        t = _clean(rec.get('eligibility'), 150)
        if t:
            out.append(f"Eligibility sun lo. {t}")
    if 'benefit' in aspects:
        t = _clean(rec.get('benefits'), 140)
        if t:
            out.append(f"Benefit yeh hai. {t}")
    if 'documents' in aspects:
        t = _clean(_separate_documents(rec.get('documents')), 170)
        if t:
            out.append(f"Documents chahiye. {t}")
    if 'apply' in aspects:
        t = _clean(rec.get('application'), 150)
        if t:
            out.append(f"Apply kaise kare. {t}")
    if not out:
        out.append("Is scheme ke baare mein portal pe poori jaankari milegi.")
    return ' '.join(out)

def answer(query, hits):
    aspects = classify_aspects(query)
    if 'status' in aspects:
        spoken = ("Suno. Status check karne ke liye portal pe login karke my applications kholo, "
                  "wahaan status dikhega. Agar payment nahi aayi hai, PFMS portal pe application ID daaliye. "
                  "Aur yaad rakhiye, Aadhaar bank account se linked hona bahut zaroori hai, warna paisa nahi aata.")
        return spoken, [{'name': 'NSP official flow', 'score': None, 'level': 'official'}], True
    if 'renewal' in aspects:
        spoken = ("Suno. Renewal ke liye renewal option chuniye, previous year ki fee receipt aur "
                  "income certificate upload kijiye. Institute verify karega, aur seedha bank mein paisa aayega.")
        return spoken, [{'name': 'NSP renewal flow', 'score': None, 'level': 'official'}], True
    if not hits:
        spoken = ("Suno. Mujhe iss sawal ka jawab nahi mila. Scholarships.gov.in pe check kijiye, "
                  "wahaan sab schemes aur last dates dikhenge.")
        return spoken, [], False
    rec = hits[0]['record']
    body = compose(rec, aspects)
    # A State scheme must never sound nationwide. If the student did not name
    # a state, say which state the chosen scheme belongs to.
    state_note = ''
    if not places.mentioned(query):
        state = places.state_of(rec)
        if state:
            state_note = f" Yeh {state} ki scheme hai."
    spoken = f"Suno. Sabse relevant scheme yeh hai, {rec['name']}.{state_note} {body} " \
             f"Official details scholarships.gov.in pe dekhiye, wahan current dates dikhengi."
    sources = [{'name': h['record']['name'], 'score': h['rank_score'],
                'level': h['record']['level']} for h in hits[:3]]
    return spoken, sources, False
