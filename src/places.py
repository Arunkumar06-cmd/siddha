"""Indian state/UT detection used to keep answers geographically honest.

The corpus mixes 293 Central schemes with 849 State schemes. A state scheme
must never be presented as if it applied nationwide, and a state-specific
query should not be answered with another state's scheme.
"""
import re

# canonical name -> spelling variants seen in ASR output and the corpus
STATES = {
    'Andhra Pradesh': ('andhra pradesh', 'andhra'),
    'Arunachal Pradesh': ('arunachal pradesh', 'arunachal'),
    'Assam': ('assam',),
    'Bihar': ('bihar',),
    'Chandigarh': ('chandigarh',),
    'Chhattisgarh': ('chhattisgarh', 'chhatisgarh'),
    'Dadra and Nagar Haveli and Daman and Diu': ('dadra', 'daman', 'diu'),
    'Delhi': ('delhi',),
    'Goa': ('goa',),
    'Gujarat': ('gujarat',),
    'Haryana': ('haryana',),
    'Himachal Pradesh': ('himachal pradesh', 'himachal'),
    'Jammu and Kashmir': ('jammu and kashmir', 'jammu & kashmir', 'j&k', 'jammu', 'kashmir'),
    'Jharkhand': ('jharkhand',),
    'Karnataka': ('karnataka',),
    'Kerala': ('kerala',),
    'Ladakh': ('ladakh',),
    'Lakshadweep': ('lakshadweep',),
    'Madhya Pradesh': ('madhya pradesh',),
    'Maharashtra': ('maharashtra',),
    'Manipur': ('manipur',),
    'Meghalaya': ('meghalaya',),
    'Mizoram': ('mizoram',),
    'Nagaland': ('nagaland',),
    'Odisha': ('odisha', 'orissa'),
    'Puducherry': ('puducherry', 'pondicherry'),
    'Punjab': ('punjab',),
    'Rajasthan': ('rajasthan',),
    'Sikkim': ('sikkim',),
    'Tamil Nadu': ('tamil nadu', 'tamilnadu'),
    'Telangana': ('telangana',),
    'Tripura': ('tripura',),
    'Uttar Pradesh': ('uttar pradesh',),
    'Uttarakhand': ('uttarakhand', 'uttaranchal'),
    'West Bengal': ('west bengal', 'bengal'),
}


def _pattern(term):
    return re.compile(rf'(?<![a-z]){re.escape(term)}(?![a-z])')


_PATTERNS = [(name, [_pattern(v) for v in variants]) for name, variants in STATES.items()]


def states_in(text):
    """All canonical states/UTs mentioned in a piece of text."""
    low = str(text or '').lower()
    return {name for name, pats in _PATTERNS if any(p.search(low) for p in pats)}


def mentioned(text):
    """The state named in a user query, or None when it is ambiguous/absent."""
    found = states_in(text)
    return found.pop() if len(found) == 1 else None


def state_of(record):
    """The single state a scheme belongs to, or None if Central/ambiguous."""
    if not record or record.get('level') != 'State':
        return None
    blob = ' '.join(str(record.get(k) or '') for k in ('name', 'details', 'application'))
    found = states_in(blob)
    return found.pop() if len(found) == 1 else None


_CENTRAL_PATTERN = re.compile(r'central\s+(government|govt|sector|scheme)', re.IGNORECASE)


def mentioned_central(text):
    """True when the query explicitly asks for Central (not State) schemes."""
    return bool(_CENTRAL_PATTERN.search(str(text or '')))


_CATEGORY_WORDS = {
    'sc': ('sc', 'scheduled caste'),
    'st': ('st', 'scheduled tribe'),
    'obc': ('obc',),
    'ebc': ('ebc', 'extremely backward'),
    'minority': ('minority', 'alpasankhyak', 'alpsankhyak', 'alpa'),
    'disabled': ('disabled', 'handicap', 'divyang', 'physically'),
    'girl': ('girl', 'kanya', 'beti'),
}


def category_boost(query, record_blob):
    """1.8 when the record mentions the query's social category, 0.75 when the query names one
    and the record clearly doesn't, else 1.0."""
    q = str(query or '').lower()
    blob = str(record_blob or '').lower()
    for _level, words in _CATEGORY_WORDS.items():
        if any(re.search(rf'(?<![a-z]){re.escape(w)}(?![a-z])', q) for w in words):
            return 1.8 if any(re.search(rf'(?<![a-z]){re.escape(w)}(?![a-z])', blob) for w in words) else 0.75
    return 1.0
