"""Evaluation sets and metrics shared by scripts/eval_retrieval.py and calibrate_confidence.py.

Four sets, each answering a different question:

  hand    30 hand-written Hinglish/intent queries (single annotator). The only set with real
          intent paraphrases; small, so read its interval, not its point estimate.
  named   one query per record ("<name> kya hai"), n = corpus size. Checks that every scheme
          can be found by name at all. Easy by construction: a ceiling, not a benchmark.
  noisy   the same names after deterministic ASR-style damage (dropped vowel, swapped letters,
          a lost space, a phonetic slip). Checks that name lookup survives speech recognition.
  ood     queries that no scheme should answer. Used for the confidence gate: the share that
          is refused, and the share of in-domain queries that is wrongly refused.

Labels for `named` and `noisy` are generated from the corpus, so they say nothing about intent
paraphrases; `hand` is the only set that does, and it is small. The numbers are a regression
guard and a calibration source, not a claim about real-world accuracy.
"""
import random

PAIRS = [
    # exact-name anchored (control)
    ("Post-Matric Scholarship for SC students kya hai",
     "Post-Matric Scholarship for SC students"),
    ("Pragati girl students technical degree scholarship AICTE",
     "Pragati Scholarship Scheme For Girl Students (Technical Degree)"),
    ("National Means Cum Merit scholarship class 8 kaun pa sakta hai",
     "National Means-Cum-Merit Scholarship Scheme"),
    ("AICTE Swanath scholarship students kya hai",
     "AICTE-Swanath Scholarship Scheme For Students"),
    ("Saksham scholarship specially abled student degree AICTE",
     "AICTE - Saksham Scholarship Scheme For Specially-Abled Student (Degree)"),
    ("Top Class Education Scheduled Castes students scholarship",
     "Top Class Education For Scheduled Caste Students"),
    ("PM YASASVI top class school education OBC EBC DNT students",
     "PM-YASASVI: Top Class School Education"),
    ("National Scholarship for post graduate studies kaunsi scheme hai",
     "National Scholarship For Post Graduate Studies"),
    ("PM USP central sector scholarship college university students",
     "PM-USP Central Sector Scheme of Scholarship"),
    ("INSPIRE SHE scholarship higher education science students kaunsi hai",
     "Innovation In Science Pursuit For Inspired Research (INSPIRE) - Scholarship For Higher Education (SHE)"),
    ("Guru Shishya Parampara scholarship kya hai",
     "Guru Shishya Parampara"),
    ("Swami Vivekananda merit cum means scholarship kaunsi hai",
     "Swami Vivekananda Merit-cum-Means Scholarship"),
    ("Ambedkar DBT voucher scheme kya hai",
     "Ambedkar DBT Voucher Scheme"),
    ("INSPIRE MANAK award student innovation kaunsi scheme hai",
     "INSPIRE Awards - MANAK"),
    ("Guruji Student Credit Card scheme kya hai",
     "Guruji Student Credit Card"),
    ("alpasankhyak post maitrik chhatravriti yojana kya hai",
     "Alpasankhyak Post-Maitrik Chhaatravrtti Yojana"),
    # intent paraphrases (real difficulty)
    ("Risktaking engineering student nudi, help milegi scholarships",
     "Swanath"),  # control pair: expect failure -> marks the floor
    ("orphan engineering student ko AICTE scholarship kaunsi milegi",
     "Swanath"),
    ("girl students technical education scholarship AICTE kya hai",
     "Pragati Scholarship Scheme For Girl Students (Technical Degree)"),
    ("SC category post matric college scholarship kaunsa hai",
     "Post-Matric Scholarship for SC students"),
    ("specially abled student diploma scholarship AICTE",
     "AICTE - Saksham Scholarship Scheme For Specially-Abled Student (Diploma)"),
    ("disable student ke liye top class education kaunsa scholarship hai",
     "Top Class Education For Students With Disabilities"),
    ("coaching scheme SC ST OBC minority students university",
     "Coaching Schemes For Sc/st/obc (non-creamy Layer) & Minority Students For Universities"),
    ("class 8 rural student merit scholarship without income proof",
     "National Means-Cum-Merit Scholarship Scheme"),
    ("university post graduate students ke liye national scholarship",
     "National Scholarship For Post Graduate Studies"),
    ("best performing college students ko kya scholarship mileti hai",
     "PM-USP Central Sector Scheme of Scholarship"),
    ("science ke enthusiastic school students ko award kaunsa milega",
     "INSPIRE Awards - MANAK"),
    ("minority community post matric scholarship Maharashtra",
     "Alpasankhyak Post-Maitrik Chhaatravrtti Yojana"),
    ("workhouse children schooling scholarship asangathit mazdoor",
     "Asangathit Karmakar Ke Bachcho Hetu Chhatravriti Yojana"),
    ("safai karmachari ke bachcho ki coaching kaunsi scheme hai",
     "Safai Karmakaar Ke Putr/Putri Hetu Vishesh Coaching Yojana"),
]

OOD = [
    "aaj Chennai ka mausam kaisa hai", "what is the bitcoin price today", "cricket score India vs Australia",
    "biryani kaise banate hain", "tell me a joke", "who is the prime minister of Japan",
    "mujhe cinema ki ticket book karni hai", "best laptop under 50000", "kya time hua hai",
    "how do I fix a flat tyre", "Shah Rukh Khan ki nayi movie", "what is machine learning",
    "hello kaise ho", "train ticket Delhi to Mumbai", "petrol price today", "write a poem about rain",
    "diwali kab hai", "stock market kya chal raha hai", "gym membership offers",
    "mere phone ki battery jaldi khatam hoti hai", "which is the tallest mountain in the world",
    "translate good morning into French", "iPhone ya Android kaunsa better hai", "best biryani in Hyderabad",
    "how to lose weight fast", "kal baarish hogi kya", "who won the football world cup",
    "mujhe ek love song batao", "how many days are there in a leap year", "what is the capital of Australia",
]


def norm(text):
    return str(text).replace('\u2013', '-').replace('\u2014', '-').lower().strip()


def named_queries(recs):
    """(query, expected normalised name) for every record."""
    return [(f"{r['name']} kya hai", norm(r['name'])) for r in recs]


def _drop_vowel(words, rnd):
    cand = [i for i, w in enumerate(words) if len(w) > 3 and any(c in 'aeiou' for c in w[1:])]
    if cand:
        i = rnd.choice(cand)
        w = words[i]
        pos = rnd.choice([k for k in range(1, len(w)) if w[k] in 'aeiou'])
        words[i] = w[:pos] + w[pos + 1:]


def _swap(words, rnd):
    cand = [i for i, w in enumerate(words) if len(w) > 4]
    if cand:
        i = rnd.choice(cand)
        w = words[i]
        k = rnd.randrange(1, len(w) - 2)
        words[i] = w[:k] + w[k + 1] + w[k] + w[k + 2:]


def _merge(words, rnd):
    if len(words) > 2:
        i = rnd.randrange(len(words) - 1)
        words[i:i + 2] = [words[i] + words[i + 1]]


def _phonetic(words, rnd):
    subs = [('sh', 's'), ('th', 't'), ('v', 'w'), ('ph', 'f'), ('ee', 'i'), ('oo', 'u')]
    cand = [(i, a, b) for i, w in enumerate(words) for a, b in subs if a in w]
    if cand:
        i, a, b = rnd.choice(cand)
        words[i] = words[i].replace(a, b, 1)


NOISE_OPS = (_drop_vowel, _swap, _merge, _phonetic)


def asr_noise(text, rnd):
    """Two ASR-style slips applied to a lower-cased name. Deterministic for a given rnd."""
    words = text.lower().split()
    for op in rnd.sample(NOISE_OPS, 2):
        op(words, rnd)
    return ' '.join(words)


def noisy_queries(recs, seed=11, n=400):
    rnd = random.Random(seed)
    picked = rnd.sample(recs, min(n, len(recs)))
    return [(f"{asr_noise(r['name'], rnd)} kya hai", norm(r['name'])) for r in picked]


# -- metrics --------------------------------------------------------------------------

def rank_of(expected, names, substring=False):
    """1-based rank of the first hit matching `expected`, else None. Both sides are normalised."""
    expected = norm(expected)
    for i, name in enumerate(names):
        n = norm(name)
        if (expected in n) if substring else (expected == n):
            return i + 1
    return None


def metrics(ranks):
    n = len(ranks)
    return {
        'n': n,
        'recall@1': sum(1 for r in ranks if r == 1) / n,
        'recall@5': sum(1 for r in ranks if r is not None and r <= 5) / n,
        'mrr': sum((1.0 / r) if r else 0.0 for r in ranks) / n,
    }


def bootstrap_ci(ranks, stat, reps=1000, seed=3):
    """95% percentile interval for `stat(sample)` over queries resampled with replacement."""
    rnd = random.Random(seed)
    n = len(ranks)
    vals = sorted(stat([ranks[rnd.randrange(n)] for _ in range(n)]) for _ in range(reps))
    return vals[int(0.025 * reps)], vals[int(0.975 * reps) - 1]


def summarise(ranks):
    out = metrics(ranks)
    for key, fn in (('recall@1', lambda s: metrics(s)['recall@1']),
                    ('recall@5', lambda s: metrics(s)['recall@5']),
                    ('mrr', lambda s: metrics(s)['mrr'])):
        lo, hi = bootstrap_ci(ranks, fn)
        out[key + '_ci'] = [round(lo, 4), round(hi, 4)]
        out[key] = round(out[key], 4)
    return out
