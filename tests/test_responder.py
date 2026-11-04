from responder import answer, classify_aspects

FAKE_HIT = [{'rank_score': 0.04, 'record': {
    'name': 'Post Matric Scholarship SC Rajasthan',
    'eligibility': 'SC students, income below 2.5 lakh',
    'benefits': 'Fees and maintenance',
    'documents': 'Caste certificate, marksheet',
    'application': 'NSP portal',
    'level': 'State'}}]

def test_aspects_detects_documents():
    assert 'documents' in classify_aspects('kitne documents chahiye')
def test_aspects_empty_defaults_all():
    assert set(classify_aspects('hello')) == {'eligibility','benefit','documents','apply'}

def test_answer_grounds_on_record():
    spoken, sources, canned = answer('SC scholarship documents?', FAKE_HIT)
    assert not canned
    assert 'Caste certificate' in spoken
    assert sources[0]['name'].startswith('Post Matric')

def test_no_hits_returns_safe_fallback():
    spoken, sources, canned = answer('banana pizza', [])
    assert not canned and 'scholarships.gov.in' in spoken.lower()
    assert sources == []

def test_status_canned_flow():
    spoken, sources, canned = answer('status check kaise kare', [])
    assert canned and 'PFMS' in spoken
