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

def test_status_question_with_no_hits_gets_the_safe_fallback():
    """There used to be a hard-coded NSP/PFMS flow here. It invented a process for
    schemes that are not on NSP, so it is gone; see tests/test_regressions.py."""
    spoken, sources, canned = answer('status check kaise kare', [])
    assert not canned and sources == []
    assert 'PFMS' not in spoken


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


def _hit(level, text, name='Post Matric Scholarship'):
    return [{'rank_score': 0.03, 'record': {
        'name': name, 'level': level, 'details': text,
        'eligibility': 'SC students', 'benefits': 'Scholarship',
        'documents': 'Caste certificate, income certificate',
        'application': 'Official portal'}}]


def test_state_scheme_is_named_for_state_less_query():
    """A State scheme must not be presented as if it applied nationwide."""
    spoken, _, _ = answer('SC scholarship documents?',
                          _hit('State', 'A scheme of the Government of Madhya Pradesh'))
    assert 'Yeh Madhya Pradesh ki scheme hai' in spoken


def test_state_query_does_not_get_the_caveat_twice():
    spoken, _, _ = answer('Madhya Pradesh SC scholarship documents?',
                          _hit('State', 'A scheme of the Government of Madhya Pradesh'))
    assert 'Yeh Madhya Pradesh ki scheme hai' not in spoken


def test_central_scheme_has_no_state_caveat():
    spoken, _, _ = answer('SC scholarship documents?',
                          _hit('Central', 'A scheme of the Government of India'))
    assert 'ki scheme hai' not in spoken


def test_places_detects_states_and_aliases():
    import places
    assert places.mentioned('bihar post matric scholarship') == 'Bihar'
    assert places.mentioned('orissa scholarship') == 'Odisha'
    assert places.mentioned('scholarship documents') is None
    assert places.state_of({'level': 'State', 'name': 'X', 'details': 'Government of Madhya Pradesh'}) == 'Madhya Pradesh'
    assert places.state_of({'level': 'Central', 'name': 'X', 'details': 'Madhya Pradesh'}) is None


def test_deadline_is_an_explicit_aspect():
    assert classify_aspects('aur last date kya hai?') == ['deadline']


def test_deadline_is_honest_when_the_record_has_no_date():
    rec = {'name': 'Post-Matric Scholarship for SC students', 'level': 'Central',
           'documents': 'Aadhaar Card', 'application': 'Apply on NSP.', 'benefits': 'Fees'}
    spoken, _, canned = answer('last date kya hai', [{'rank_score': 0.03, 'record': rec}])
    assert not canned
    assert 'last date nahi di gayi' in spoken
    assert 'scholarships.gov.in' in spoken
    assert not any(ch.isdigit() for ch in spoken), 'must never invent a date'


def test_deadline_quotes_a_date_that_is_in_the_record():
    rec = {'name': 'ICMR Fellowship', 'level': 'Central',
           'application': 'Last Date of Application (30th June and 31st December Every Year)',
           'benefits': 'Fellowship'}
    spoken, _, _ = answer('last date kya hai', [{'rank_score': 0.03, 'record': rec}])
    assert '30th June' in spoken


def test_follow_up_lead_names_the_scheme_again():
    spoken, _, _ = answer('last date kya hai', FAKE_HIT, follow_up=True)
    assert spoken.startswith('Suno. Usi scheme ke liye')
    assert 'Post Matric Scholarship SC Rajasthan' in spoken


def test_new_topic_lead_does_not_claim_continuity():
    spoken, _, _ = answer('documents kya chahiye', FAKE_HIT)
    assert spoken.startswith('Suno. Sabse relevant scheme yeh hai')
