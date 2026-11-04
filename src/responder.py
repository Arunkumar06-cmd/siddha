"""Saathi responder - grounded strictly in the myScheme corpus.
Voice-safe output: short sentences with <pauses> tags for Timbre v3.0."""
import re
from spoken import speakify, render

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

def _clean(raw, cap=160):
    t = re.sub(r'\s+', ' ', str(raw or '')).strip(' .,')
    t = re.sub(r'^(Documents Required?|Eligibility( Criteria)?|Benefits?|How to Apply|Application|Details)\s*:?\s*',
               '', t, flags=re.I).strip(' .,')
    return t[:cap]

def compose(rec, aspects):
    out = []
    if 'eligibility' in aspects:
        t = _clean(rec.get('eligibility'), 150)
        if t: out.append(f"Eligibility sun lo. {t}")
    if 'benefit' in aspects:
        t = _clean(rec.get('benefits'), 140)
        if t: out.append(f"Benefit yeh hai. {t}")
    if 'documents' in aspects:
        t = _clean(rec.get('documents'), 170)
        if t: out.append(f"Documents chahiye. {t}")
    if 'apply' in aspects:
        t = _clean(rec.get('application'), 150)
        if t: out.append(f"Apply kaise kare. {t}")
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
    spoken = f"Suno. Sabse relevant scheme yeh hai, {rec['name']}. {body} " \
             f"Official details scholarships.gov.in pe dekhiye, wahan current dates dikhengi."
    sources = [{'name': h['record']['name'], 'score': h['rank_score'],
                'level': h['record']['level']} for h in hits[:3]]
    return spoken, sources, False
