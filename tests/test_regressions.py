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
