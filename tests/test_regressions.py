"""Regression tests for defects found in the pre-submission review.

Each test fails on the code as it was before the fix:
  * canned NSP/PFMS answers invented a process for every scheme
  * eligibility could be spoken as half a rule ("income must not exceed")
  * audio was cut by string index at 600 chars, mid-sentence or mid-tag
  * Hindi/Tamil follow-ups were tokenised to nothing and answered from the old scheme
  * substring keyword matching ("paper" fired on "newspaper")
"""
import pytest

import context
import conversation
from responder import answer, clip_items, clip_sentences, explicit_aspects
from spoken import render, speakify

BARE = {
    'name': 'Sample Scholarship', 'level': 'Central',
    'eligibility': 'Students.', 'benefits': 'Support.',
    'documents': 'Marksheet', 'application': 'Apply at the office.',
}

EM_DASH = chr(0x2014)
EN_DASH = chr(0x2013)


def _hit(rec=None):
    return [{'rank_score': 0.03, 'record': rec or BARE}]


# -- no invented process ---------------------------------------------------

@pytest.mark.parametrize('query', ['status check kaise kare', 'renewal kaise karein'])
def test_status_and_renewal_never_invent_a_process(query):
    spoken, _, _ = answer(query, _hit())
    for invented in ('PFMS', 'Aadhaar linked', 'upload', 'application ID'):
        assert invented not in spoken, f'{invented!r} is not in the record'


def test_status_with_no_hits_is_the_safe_fallback_not_a_canned_flow():
    spoken, sources, _ = answer('status check kaise kare', [])
    assert 'PFMS' not in spoken
    assert 'scholarships.gov.in' in spoken.lower()
    assert sources == []


def test_renewal_is_quoted_only_when_the_record_says_it():
    rec = dict(BARE, application='Students must renew every year with a fresh marksheet.')
    spoken, _, _ = answer('renewal kaise karein', _hit(rec))
    assert 'renew every year' in spoken
    spoken, _, _ = answer('renewal kaise karein', _hit())
    assert 'renewal ki jaankari nahi hai' in spoken


# -- never speak half a rule -----------------------------------------------

def test_a_rule_is_never_cut_before_its_condition():
    rule = ('Annual family income must not exceed Rs. 2.5 lakh per annum. '
            + 'Applicant must have passed the previous examination with at least fifty percent marks. ' * 3)
    out = clip_sentences(rule, budget=100)
    assert 'must not exceed Rs. 2.5 lakh per annum.' in out
    assert 'official page' in out, 'left-out sentences must be acknowledged'


def test_an_overlong_first_sentence_is_not_read_in_part():
    rule = 'Applicant ' + 'who satisfies every one of the listed conditions ' * 12 + 'is eligible.'
    out = clip_sentences(rule, budget=100, hard=200)
    assert 'official page' in out
    assert 'Applicant who' not in out


def test_short_rules_pass_through_whole():
    assert clip_sentences('SC students, income below 2.5 lakh') == 'SC students, income below 2.5 lakh.'


def test_document_lists_are_cut_at_item_boundaries():
    docs = ', '.join(f'Document number {i}' for i in range(40))
    out = clip_items(docs, 100)
    assert 'Aur bhi documents hain' in out
    body = out.split(' Aur bhi')[0].rstrip('.')
    assert all(item.startswith('Document number ') for item in body.split(', '))


# -- keyword matching respects word boundaries ------------------------------

def test_aspect_keywords_do_not_fire_inside_other_words():
    assert 'documents' not in explicit_aspects('i read the newspaper today')
    assert 'eligibility' not in explicit_aspects('patriot scholarship')
    assert 'documents' in explicit_aspects('which papers are needed')


# -- audio cap cuts on sentence boundaries ---------------------------------

def test_render_cap_never_splits_a_tag_or_a_sentence():
    text = ' '.join(f'Sentence number {i} has a few words in it.' for i in range(40))
    out = render(text, use_tags=True, max_chars=200)
    assert len(out) <= 200
    assert out.endswith('.')
    assert not out.rstrip().endswith('<pauses>')
    assert out.count('<pauses>') == out.count('<') == out.count('>')


def test_render_cap_trims_a_single_overlong_sentence_at_a_word():
    out = render('word ' * 300, max_chars=100)
    assert len(out) <= 100 and out.endswith('word.')


def test_render_without_cap_is_unchanged():
    text = 'One. Two. Three.'
    assert render(text) == 'One. <pauses> Two. <pauses> Three.'


def test_dash_becomes_a_pause_not_a_symbol():
    assert speakify(f'Usi scheme ke liye {EM_DASH} Name.') == 'Usi scheme ke liye, Name.'
    assert speakify(f'Class 10 {EN_DASH} 12') == 'Class 10, 12.'


# -- Hindi and Tamil follow-ups --------------------------------------------

def _last():
    return conversation.Turn(
        query='q', reply='r',
        scheme={'id': 'pmsfss', 'name': 'Post-Matric Scholarship for SC students', 'level': 'Central'})


@pytest.mark.parametrize('query', [
    'और अंतिम तारीख क्या है',            # Hindi: and, last date, what
    'इस योजना की अंतिम तारीख क्या है',    # Hindi: this scheme's last date
    'கடைசி தேதி என்ன',                    # Tamil: last date, what
])
def test_indic_aspect_only_questions_stay_on_the_current_scheme(query):
    assert context.is_follow_up(query, _last())
    assert context.is_aspect_only(query)
    assert not context.residual(query)


@pytest.mark.parametrize('query', [
    'पीएम किसान छात्रवृत्ति के दस्तावेज़ क्या हैं',    # Hindi: PM Kisan scholarship documents
    'முதல்வர் உதவித்தொகை ஆவணங்கள் என்ன',          # Tamil: Chief Minister scholarship documents
])
def test_a_new_scheme_named_in_an_indic_script_is_not_forced_into_context(query):
    """Before the fix every Indic character was discarded, the residual came out
    empty, and this was answered from the previous scheme with no retrieval."""
    assert context.residual(query), 'the scheme name must survive tokenising'
    assert not context.is_aspect_only(query)
    assert context.rewrite(query, _last()) == query


# -- deadlines, status and renewal are grounded, not guessed -----------------

def test_a_past_deadline_is_not_presented_as_current():
    """The old regex quoted any 'last date' phrase, including a 2022 date, as if it
    were today's deadline."""
    rec = dict(BARE, application='Last date for submission is 31/12/2022.')
    spoken, _, _ = answer('last date kya hai', _hit(rec))
    assert '31 December 2022' in spoken
    assert 'beet chuki hai' in spoken
    assert 'Record ke mutabik, Last date' not in spoken


def test_a_deadline_phrase_without_a_concrete_date_is_not_turned_into_one():
    rec = dict(BARE, application='The last date is generally the first week of April every year.')
    spoken, _, _ = answer('last date kya hai', _hit(rec))
    assert 'last date nahi di gayi' in spoken
    assert 'April' not in spoken


def test_a_current_deadline_is_quoted_without_claiming_a_past_one():
    import datetime
    future = datetime.date.today() + datetime.timedelta(days=30)
    rec = dict(BARE, application=f'The last date for submission is {future.day:02d}/{future.month:02d}/{future.year}.')
    spoken, _, _ = answer('last date kya hai', _hit(rec))
    assert f'{future.day} {future.strftime("%B %Y")}' in spoken
    assert 'beet chuki hai' not in spoken


def test_status_is_quoted_when_the_record_has_a_tracking_line():
    rec = dict(BARE, application=(
        'Check Application Status: visit the official website and enter your application ID.'))
    spoken, _, _ = answer('application status kaise dekhe', _hit(rec))
    assert 'Check Application Status' in spoken
    assert 'nahi diya gaya' not in spoken


def test_status_falls_back_when_the_record_has_no_tracking_line():
    spoken, _, _ = answer('application status kaise dekhe', _hit())
    assert 'nahi diya gaya' in spoken


def test_renewal_does_not_quote_a_renewal_document_as_the_process():
    """'Last Subscription Renewal Copy' is a document in the documents list; quoting
    it as the renewal process told the student nothing about how to renew."""
    rec = dict(BARE, documents='Original ID Card. Last Subscription Renewal Copy. Death Certificate.')
    spoken, _, _ = answer('renewal kaise karein', _hit(rec))
    assert 'renewal ki jaankari nahi hai' in spoken
    assert 'Renewal Copy' not in spoken


def test_renewal_prefers_the_process_sentence_over_a_document_list():
    rec = dict(BARE,
               documents='Original ID Card. Renewal Copy. Death Certificate.',
               application='Submit an annual renewal request through the portal with the previous mark sheet.')
    spoken, _, _ = answer('renewal kaise karein', _hit(rec))
    assert 'annual renewal request' in spoken
    assert 'Renewal Copy' not in spoken


@pytest.mark.parametrize('text, expected', [
    ('Last date: 2026-11-10', (2026, 11, 10)),
    ('Last date: 31/12/2026', (2026, 12, 31)),
    ('Last date: 03/31/2026', (2026, 3, 31)),
    ('Last date: 31st October 2026', (2026, 10, 31)),
    ('Last date: October 31, 2026', (2026, 10, 31)),
    ('Last date: April 2026', (2026, 4, 30)),
    ('Last date: first week of April every year', None),
    ('Launched in 2021 and open now', None),
])
def test_deadline_date_parser_accepts_only_concrete_dates(text, expected):
    from responder import _parse_date
    found = _parse_date(text)
    actual = (found.year, found.month, found.day) if found else None
    assert actual == expected
