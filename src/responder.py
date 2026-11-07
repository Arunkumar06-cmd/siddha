"""Siddha responder - grounded strictly in the myScheme corpus.
Voice-safe output: short sentences with <pauses> tags for Timbre v3.0."""
import re

import places

ASPECT_KEYS = {
    'documents': ['document', 'paper', 'kagaz', 'needed', 'proof', 'certificate',
                  'दस्तावेज', 'कागज', 'ஆவண'],
    'eligibility': ['eligible', 'eligibility', 'qualification', 'who can', 'kaise eligible',
                    'patra', 'patrata', 'patrta', 'पात्रता', 'पात्र', 'தகுதி'],
    'benefit': ['benefit', 'amount', 'kitna', 'paisa', 'paise', 'rupees', 'rupee',
                'लाभ', 'राशि', 'பலன்', 'தொகை'],
    'apply': ['apply', 'portal', 'nsp', 'आवेदन', 'விண்ணப்ப'],
    'renewal': ['renew', 'renewal', 'purana', 'नवीनीकरण', 'புதுப்பி'],
    'status': ['status', 'track', 'application id', 'स्थिति', 'நிலை'],
    'deadline': ['deadline', 'last date', 'last day', 'kab tak', 'akhri',
                 'tareekh', 'tarikh', 'अंतिम तारीख', 'आखिरी तारीख', 'अंतिम तिथि',
                 'கடைசி தேதி', 'கடைசி நாள்'],
}


def _has_key(ql, key):
    """ASCII keys must start a word ("paper" must not fire on "newspaper");
    Indic keys are matched as substrings because script word boundaries are fuzzy."""
    if key.isascii():
        return re.search(rf'(?<![a-z]){re.escape(key)}', ql) is not None
    return key in ql


def explicit_aspects(q):
    ql = q.lower()
    return [a for a, ks in ASPECT_KEYS.items() if any(_has_key(ql, k) for k in ks)]

def classify_aspects(q):
    return explicit_aspects(q) or ['eligibility', 'benefit', 'documents', 'apply']

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


def _clean(raw, cap=320):
    """Normalise a record field, cutting only at sentence boundaries.

    The old word-boundary cap could turn "income must not exceed Rs. 2.5 lakh"
    into "income must not exceed" and could cut a document list mid-item.
    Now: sentences are kept whole; a comma list is kept at item boundaries;
    if the opening item alone is too long it is dropped rather than cut. """
    t = _tidy(_separate_documents(raw))
    if not t or len(t) <= cap:
        return _end(t) if t else ''
    if ',' in t or ';' in t:
        items = [i.strip(' .') for i in re.split(r'\s*[,;]\s*|(?<=\.)\s+', t) if i.strip(' .')]
        kept, used = [], 0
        for item in items:
            extra = len(item) + (2 if kept else 0)
            if kept and used + extra > cap:
                break
            if not kept and len(item) > cap:
                break
            kept.append(item)
            used += extra
        if kept:
            return _end(', '.join(kept))
        return ''
    return clip_sentences(t, budget=cap, hard=max(cap, 320), more='')

_PREFIX_RE = re.compile(
    r'^(Documents Required?|Eligibility( Criteria)?|Benefits?|How to Apply|Application|Details)\s*:?\s*',
    re.IGNORECASE)
_ABBR = re.compile(r'(?i)\b(rs|no|dr|mr|mrs|ms|sr|jr|vs|approx|govt|dept|etc)\.')
_LATIN_ABBR = re.compile(r'(?i)\b(i\.e|e\.g)\.')
_LIST_NO = re.compile(r'(?<![\d.])(\d{1,2})\.(?=\s)')
_DOT = '\x00'


def _tidy(raw):
    t = re.sub(r'\s+', ' ', str(raw or '')).strip(' .,')
    return _PREFIX_RE.sub('', t).strip(' .,')


def _end(t):
    return t if not t or t[-1] in '.!?' else t + '.'


def _sentences(text):
    """Split on sentence ends without breaking "Rs. 2.5 lakh", "No. 4" or "1. Aadhaar"."""
    t = _ABBR.sub(lambda m: m.group(1) + _DOT, text)
    t = _LATIN_ABBR.sub(lambda m: m.group(0).replace('.', _DOT), t)
    t = _LIST_NO.sub(lambda m: m.group(1) + _DOT, t)
    return [p.replace(_DOT, '.').strip() for p in re.split(r'(?<=[.;!?])\s+', t) if p.strip()]


def clip_sentences(raw, budget=150, hard=320, more=' Baaki ki jaankari official page pe hai.'):
    """Shorten a rule (eligibility, benefit) without ever speaking half a rule.

    Whole sentences only. If sentences are left out, say so. A first sentence
    too long to speak whole is not read in part: the student is sent to the
    official page instead of hearing a clause with its condition cut off."""
    t = _tidy(raw)
    if not t:
        return ''
    if len(t) <= budget:
        return _end(t)
    sents = _sentences(t)
    first = sents[0].rstrip(' ;')
    if len(first) > hard:
        return 'Yeh shart lambi hai, poori jaankari official page pe dekhiye.'
    kept, used = [first], len(first)
    for sent in sents[1:]:
        sent = sent.rstrip(' ;')
        if used + 1 + len(sent) > budget:
            break
        kept.append(sent)
        used += 1 + len(sent)
    out = ' '.join(_end(k) for k in kept)
    return out + (more if len(kept) < len(sents) else '')


def clip_items(raw, budget=300, more=' Aur bhi documents hain, poori list official page pe dekhiye.'):
    """Shorten a document list at an item boundary and say when items were left out."""
    t = _tidy(_separate_documents(raw))
    if not t:
        return ''
    if len(t) <= budget:
        return _end(t)
    items = [i.strip(' .') for i in re.split(r'\s*[,;]\s*|(?<=\.)\s+', t) if i.strip(' .')]
    kept, used = [], 0
    for item in items:
        extra = len(item) + (2 if kept else 0)
        if kept and used + extra > budget:
            break
        kept.append(item)
        used += extra
    return _end(', '.join(kept)) + (more if len(kept) < len(items) else '')


def _grounded_sentence(rec, needle):
    """First sentence of the record that mentions `needle`, else None."""
    blob = ' '.join(str(rec.get(k) or '') for k in ('application', 'details', 'eligibility', 'documents', 'benefits'))
    for sent in _sentences(re.sub(r'\s+', ' ', blob)):
        if needle in sent.lower():
            return sent
    return None


def renewal_line(rec):
    sent = _grounded_sentence(rec, 'renew')
    if sent:
        return f"Record ke mutabik, {clip_sentences(sent, 200)}"
    return "Is record mein renewal ki jaankari nahi hai. Official page pe dekhiye."


def status_line(rec):
    return ("Is record mein application status dekhne ka tareeka nahi diya gaya. "
            "Jis portal pe apply kiya, uska official page dekhiye.")


DATE_RE = re.compile(
    r'((?:last date|closing date|deadline|last day)[^.]{0,100})', re.IGNORECASE
)


def deadline_line(rec):
    """Quote a date only when the record contains one; otherwise say so."""
    blob = ' '.join(str(rec.get(k) or '') for k in ('application', 'details', 'benefits'))
    match = DATE_RE.search(blob)
    if match:
        return f"Record ke mutabik, {clip_sentences(match.group(1), 130)}"
    return ("Is record mein last date nahi di gayi. Scheme ka official page "
            "scholarships.gov.in pe kholiye, wahan current date dikhegi.")


def compose(rec, aspects, overview=False):
    """Answer the requested aspects from the record.

    overview=True is the "tell me about this scholarship" answer: the opening
    sentence of eligibility and benefit only, with no per-field marker because
    the closing line already says it is a summary."""
    out = []
    more_e = '' if overview else ' Baaki conditions official page pe dekhiye.'
    more_b = '' if overview else ' Baaki ki jaankari official page pe hai.'
    if 'eligibility' in aspects:
        t = clip_sentences(rec.get('eligibility'), 100 if overview else 150, more=more_e)
        if t:
            out.append(f"Eligibility sun lo. {t}")
    if 'benefit' in aspects:
        t = clip_sentences(rec.get('benefits'), 100 if overview else 140, more=more_b)
        if t:
            out.append(f"Benefit yeh hai. {t}")
    if 'documents' in aspects:
        t = clip_items(rec.get('documents'), 240)
        if t:
            out.append(f"Documents chahiye. {t}")
    if 'deadline' in aspects:
        out.append(deadline_line(rec))
    if 'renewal' in aspects:
        out.append(renewal_line(rec))
    if 'status' in aspects:
        out.append(status_line(rec))
    if 'apply' in aspects:
        t = clip_sentences(rec.get('application'), 150, more=' Baaki ki jaankari official page pe hai.')
        if t:
            out.append(f"Apply kaise kare. {t}")
    if not out:
        out.append("Is scheme ke baare mein portal pe poori jaankari milegi.")
    return ' '.join(out)

HEDGE_HINT = "Agar yeh aapki scheme nahi hai, to scheme ka poora naam bol dijiye."


def answer(query, hits, follow_up=False, hedge=False):
    """`hedge` marks a shaky retrieval: say so instead of announcing the scheme as the answer."""
    aspects = classify_aspects(query)
    if not hits:
        spoken = ("Suno. Mujhe iss sawal ka jawab nahi mila. Scholarships.gov.in pe check kijiye, "
                  "wahaan sab schemes aur last dates dikhenge.")
        return spoken, [], False
    rec = hits[0]['record']
    # No specific question ("scholarship batao") gets a short overview that fits one
    # spoken turn instead of all four sections; documents/apply are one question away.
    overview = not explicit_aspects(query)
    if overview:
        aspects = ['eligibility', 'benefit']
    body = compose(rec, aspects, overview=overview)
    # A State scheme must never sound nationwide. If the student did not name
    # a state, say which state the chosen scheme belongs to.
    state_note = ''
    if not places.mentioned(query):
        state = places.state_of(rec)
        if state:
            state_note = f" Yeh {state} ki scheme hai."
    if follow_up:
        lead = f"Suno. Usi scheme ke liye — {rec['name']}."
    elif hedge:
        lead = f"Suno. Pakka nahi hai, par sabse milti-julti scheme yeh lag rahi hai, {rec['name']}."
    else:
        lead = f"Suno. Sabse relevant scheme yeh hai, {rec['name']}."
    closing = "Official details scholarships.gov.in pe dekhiye, wahan current dates dikhengi."
    if overview:
        closing = ("Documents ya apply kaise karein, yeh bhi pooch sakte hain. "
                   "Poori shartein official page pe dekhiye.")
    if aspects == ['deadline']:
        closing = ""  # the deadline line already points at the official page
    if hedge and not follow_up:
        closing = f"{HEDGE_HINT} {closing}".strip()
    spoken = f"{lead}{state_note} {body} {closing}".strip()
    sources = [{'name': h['record']['name'], 'score': h['rank_score'],
                'level': h['record']['level']} for h in hits[:3]]
    return spoken, sources, False
