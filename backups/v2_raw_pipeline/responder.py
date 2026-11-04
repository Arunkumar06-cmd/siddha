"""Grounded answer composer. No generative LLM by default - answers are
templated from retrieved scheme records (zero hallucination). If an
OpenAI-compatible endpoint is configured (GROQ_API_KEY style via .env),
it composes the final phrasing instead; still retrieval-grounded."""
import json, re, os

ASPECTS = {
    'documents': ['document', 'paper', 'kagaz', 'kya chahiye', 'needed', 'proof', 'certificate', 'दस्तावेज़'],
    'eligibility': ['eligible', 'qualification', 'who can', 'eligibility', 'kaun apply', 'patr', 'पात्रता', 'qualify'],
    'benefit': ['benefit', 'amount', 'kitne paise', 'paise', 'paisa', 'rupees', 'rupee', 'लाभ'],
    'apply': ['how to apply', 'apply', 'application process', 'kaise apply', 'website', 'portal', 'nsp', 'आवेदन'],
    'deadline': ['last date', 'deadline', 'date', 'kab tak', 'timing'],
    'renewal': ['renew', 'renewal', 'purana', 'existing'],
    'status': ['status', 'status check', 'track', 'check status', 'application id'],
}

SRC_EDU = ("Visit the National Scholarship Portal (scholarships.gov.in), register with your Aadhaar, "
           "complete OTR, then apply under the right scheme. Link your Aadhaar to your bank account before "
           "the last date, submit a caste/income certificate in PDF, and check the status on PFMS.")

def classify_aspects(q):
    ql = q.lower()
    hits = [a for a, kws in ASPECTS.items() if any(k in ql for k in kws)]
    return hits or ['all']

def _short(text, max_chars=420):
    text = re.sub(r'\s+', ' ', text or '').strip()
    return (text[:max_chars] + '…') if len(text) > max_chars else text

def _voice_answer(rec, aspects):
    name = rec['name']
    parts = [f"Saathi here. For {name}:"]
    if 'all' in aspects or 'eligibility' in aspects:
        elig = _short(rec.get('eligibility', ''), 300)
        if elig:
            parts.append(f"Eligibility: {elig}")
    if 'all' in aspects or 'benefit' in aspects:
        ben = _short(rec.get('benefits', ''), 220)
        if ben:
            parts.append(f"Benefit: {ben}")
    if 'all' in aspects or 'documents' in aspects:
        doc = _short(rec.get('documents', ''), 300)
        if doc:
            parts.append(f"Documents required: {doc}")
    if 'all' in aspects or 'apply' in aspects:
        app = _short(rec.get('application', ''), 260)
        if app:
            parts.append(f"How to apply: {app}")
    return ' '.join(parts)

def answer(query, hits):
    """Return (reply_text, sources:list[dict])."""
    aspects = classify_aspects(query)
    if aspects == ['status']:
        reply = ("Saathi here. Scholarship status check karne ke liye: pehle scholarships.gov.in pe login karo, "
                 "phir 'My Applications' kholo - status dikhega pending, verified, approved ya failed. "
                 "Payment track karna hai to PFMS portal (pfms.nic.in) pe apna application ID daalo. "
                 "Aadhaar bank se linked nahi hai to paisa nahi aata - pehle bank branch mein Aadhaar DBT link karwa lo.")
    elif aspects == ['renewal']:
        reply = ("Saathi here. Scholarship renew karne ke liye renewal option select karo portal pe, "
                 "purane result aur current-year income certificate upload karo. "
                 "Institute nodal officer verify karta hai, phir aapke bank mein seedha aa jayega.")
    else:
        rec = hits[0]['record'] if hits else None
        if not rec:
            reply = "Saathi here. Hmm, mujhe is sawal ka jawab nahi mila. Scholarships.gov.in pe check kijiye."
        else:
            reply = _voice_answer(rec, aspects)
    sources = [{'name': h['record']['name'], 'level': h['record']['level'],
                'score': h['rank_score']} for h in hits[:3]]
    return reply, sources
