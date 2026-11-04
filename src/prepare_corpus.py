"""Filter the myScheme dump to scholarship/education-relevant schemes and
write a compact, multilingual-ready JSONL corpus for RAG."""
import json
import logging
import re

import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger(__name__)

SRC = 'data/updated_data.csv'
OUT = 'data/scholarships.jsonl'

KEYWORDS = re.compile(
    r'scholar|stipend|fellowship|fellowship|merit[- ]cum[- ]means|obc.*scholar|'
    r'post[- ]matric|pre[- ]matric|minority scholar|top class education|'
    r'financial assistance.*(student|education|studies)|education loan|fee reimbursement|'
    r'coaching.*(student|minorit)|nsp\b|dbt', re.IGNORECASE)

def keep(row):
    text = ' '.join(str(row.get(c, '')) for c in
                    ['scheme_name', 'details', 'benefits', 'eligibility', 'application', 'tags'])
    return bool(KEYWORDS.search(text))

df = pd.read_csv(SRC)
df = df.dropna(how='all')
df = df[[keep(r) for _, r in df.iterrows()]]
log.info('scholarship/education rows: %d', len(df))

def clean(s):
    s = re.sub(r'\s+', ' ', str(s or '')).strip()
    return s

records = []
for _, r in df.iterrows():
    name = clean(r.get('scheme_name'))
    if not name or name.lower() == 'nan':
        continue
    rec = {
        'id': str(r.get('slug') or name).strip().lower(),
        'name': name,
        'category': clean(r.get('schemeCategory')),
        'level': clean(r.get('level')),
        'details': clean(r.get('details')),
        'eligibility': clean(r.get('eligibility')),
        'benefits': clean(r.get('benefits')),
        'documents': clean(r.get('documents')),
        'application': clean(r.get('application')),
        'tags': clean(r.get('tags')),
    }
    records.append(rec)

with open(OUT, 'w', encoding='utf-8') as f:
    for rec in records:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
log.info('wrote %s schemes=%d', OUT, len(records))
