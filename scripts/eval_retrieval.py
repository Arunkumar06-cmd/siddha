"""Labeled retrieval evaluation over the shipped corpus.

30 queries spanning Hinglish, code-mixed Devanagari, and intent paraphrases —
one expected scheme name per query (case-insensitive substring of the record
name). Reports recall@1, recall@5 and MRR so a model swap can be measured,
not vibed. No network except the one-time embedding model download.

Usage:
    python3 scripts/eval_retrieval.py            # current retriever (BGE-M3)
"""
import sys

sys.path.insert(0, 'src')

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
     "AICTE – Saksham Scholarship Scheme For Specially-Abled Student (Degree)"),
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
     "INSPIRE Awards – MANAK"),
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
     "AICTE – Saksham Scholarship Scheme For Specially-Abled Student (Diploma)"),
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
     "INSPIRE Awards – MANAK"),
    ("minority community post matric scholarship Maharashtra",
     "Alpasankhyak Post-Maitrik Chhaatravrtti Yojana"),
    ("workhouse children schooling scholarship asangathit mazdoor",
     "Asangathit Karmakar Ke Bachcho Hetu Chhatravriti Yojana"),
    ("safai karmachari ke bachcho ki coaching kaunsi scheme hai",
     "Safai Karmakaar Ke Putr/Putri Hetu Vishesh Coaching Yojana"),
]

assert len(PAIRS) == 30

import retriever  # noqa: E402

hits_at = []
for query, expect in PAIRS:
    hits = retriever.search(query, k=8)
    names = [h['record']['name'] for h in hits]
    rank = next((i + 1 for i, n in enumerate(names) if expect.lower() in n.lower()), None)
    hits_at.append(rank)
    status = f"rank {rank}" if rank else "MISS"
    print(f"[{status:>6}] {query[:64]}")

r1 = sum(1 for r in hits_at if r == 1) / len(hits_at)
r5 = sum(1 for r in hits_at if r is not None and r <= 5) / len(hits_at)
mrr = sum((1.0 / r) if r else 0 for r in hits_at) / len(hits_at)
print(f"\nrecall@1={r1:.2f}  recall@5={r5:.2f}  MRR={mrr:.2f}  n={len(hits_at)}")
