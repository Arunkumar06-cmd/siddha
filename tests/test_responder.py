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
    spoken, _, canned = answer('status check kaise kare', [])
    assert canned and 'PFMS' in spoken


def test_clean_never_cuts_mid_word():
    """A dangling half-word ("Income D") looks broken and sounds broken."""
    from responder import _clean

    raw = 'Aadhaar Card Caste Certificate Income Certificate Bank Account Details'
    out = _clean(raw, 50)
    core = out.rstrip('.')
    assert len(core) <= 50
    assert raw.startswith(core)
    assert len(raw) == len(core) or raw[len(core)] == ' ', f'cut mid-word: {core[-15:]!r}'


def test_clean_terminates_short_text():
    from responder import _clean

    assert _clean('Caste certificate, marksheet', 100) == 'Caste certificate, marksheet.'


def test_clean_drops_dangling_preposition_at_cut():
    from responder import _clean

    raw = ('Proof of identity. Caste certificate. Income certificate of the family. '
           'Admission letter and fee receipt from the institute')
    out = _clean(raw, 110)
    assert len(out) <= 111
    assert out.rstrip('.').split()[-1].lower() not in {
        'a', 'an', 'and', 'from', 'of', 'the', 'to', 'for', 'with',
    }
    assert out.endswith('.')


def test_concatenated_document_list_gets_commas():
    from responder import _separate_documents

    raw = ('Aadhaar Card Caste Certificate Income Certificate Bank Account Details '
           'Passport-sized Photograph Educational Documents Proof of Admission')
    out = _separate_documents(raw)
    assert 'Aadhaar Card, Caste Certificate' in out
    assert 'Bank Account Details, Passport-sized Photograph' in out
    assert out.count(',') >= 5


def test_punctuated_documents_are_left_alone():
    from responder import _separate_documents

    raw = 'Proof of identity (Aadhaar Card). Caste certificate, income certificate.'
    assert _separate_documents(raw) == raw


def test_conjunction_in_document_list_is_not_commaed():
    from responder import _separate_documents

    raw = 'Aadhaar Card and Caste Certificate'
    assert _separate_documents(raw) == 'Aadhaar Card and Caste Certificate'
