from spoken import render, speakify, split_sentences


def test_strips_money_markup():
    out = speakify('Scholarship kaisa hai ₹5,000 har mahina')
    assert '₹' not in out
    assert '5,000' not in out

def test_removes_urls_and_urls_prefix():
    out = speakify('Apply at https://scholarships.gov.in/login now')
    assert 'http' not in out and 'gov.in' not in out

def test_slashes_and_brackets_are_not_read():
    out = speakify('Documents (certificate/required) [scan] needed/check')
    assert '/' not in out and '[' not in out and '(' not in out

def test_sentences_are_short():
    sents = split_sentences('These are many words joined together to force a wrap. ' * 30, 110)
    for s in sents:
        assert len(s) <= 130  # word-boundary tolerance

def test_render_adds_pauses_and_finishes():
    out = render('Hello world. This is Saathi testing.', use_tags=True)
    assert '<pauses>' in out
    assert out.rstrip().endswith('.')
