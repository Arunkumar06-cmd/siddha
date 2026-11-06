"""Deterministic follow-up resolution and session memory."""
import context
import conversation
import pipeline


def _last():
    return conversation.Turn(
        query='SC students ke liye post matric documents?',
        reply='Suno. Sabse relevant scheme yeh hai, Post-Matric Scholarship for SC students.',
        scheme={'id': 'pmsfss', 'name': 'Post-Matric Scholarship for SC students',
                'level': 'Central'},
    )


def test_no_history_is_never_a_follow_up():
    assert not context.is_follow_up('Aur last date kya hai?', None)


def test_pronoun_is_a_follow_up():
    assert context.is_follow_up('uske documents kya chahiye?', _last())


def test_bare_aspect_is_a_follow_up_and_focusable():
    q = 'Aur last date kya hai?'
    assert context.is_follow_up(q, _last())
    assert context.is_aspect_only(q)


def test_state_refinement_is_contextual_but_not_focused():
    q = 'Tamil Nadu ke liye?'
    assert context.is_follow_up(q, _last())
    assert not context.is_aspect_only(q)
    assert 'Tamil Nadu' in context.rewrite(q, _last())


def test_new_scheme_is_not_forced_into_context():
    q = 'PM Kisan scholarship ke documents kya chahiye?'
    assert not context.is_follow_up(q, _last())
    assert not context.is_aspect_only(q)
    assert context.rewrite(q, _last()) == q


def test_rewrite_anchors_a_follow_up():
    out = context.rewrite('Aur documents?', _last())
    assert out.startswith('Post-Matric Scholarship for SC students')
    assert 'Aur documents?' in out


def test_store_keeps_last_turn_and_resets():
    store = conversation.ConversationStore()
    turn = _last()
    store.record('session-abc', turn)
    assert store.last('session-abc') is turn
    store.reset('session-abc')
    assert store.last('session-abc') is None


def test_store_does_not_create_on_read():
    store = conversation.ConversationStore()
    assert store.last('never-seen') is None
    assert 'never-seen' not in store._data


def test_store_expires_idle_sessions():
    store = conversation.ConversationStore(ttl=-1)
    store.record('session-abc', _last())
    assert store.last('session-abc') is None


def test_store_caps_turns():
    store = conversation.ConversationStore()
    for i in range(conversation.MAX_TURNS + 4):
        store.record('session-abc', conversation.Turn(
            query=f'q{i}', reply='r', scheme=None))
    assert len(store.get('session-abc').turns) == conversation.MAX_TURNS


def test_pipeline_reuses_focus_without_retrieval(monkeypatch):
    rec = {
        'id': 'pmsfss', 'name': 'Post-Matric Scholarship for SC students',
        'level': 'Central',
        'eligibility': 'Scheduled Castes; passed matriculation.',
        'benefits': 'Maintenance allowance.',
        'documents': 'Photograph. Aadhaar Card. Caste Certificate.',
        'application': 'Apply on the NSP portal.',
    }
    calls = []

    def fake_search(query, k=5):
        calls.append(query)
        return [{'record': rec, 'rank_score': 0.03}]

    monkeypatch.setattr(pipeline.retriever, 'search', fake_search)
    monkeypatch.setattr(pipeline, '_eligibility_ready', lambda: False)

    sid = 'pytest-context-1'
    conversation.STORE.reset(sid)
    try:
        _, _, first = pipeline.rag_answer('SC post matric documents?', sid)
        assert first['context_used'] is False
        assert len(calls) == 1

        reply, _, second = pipeline.rag_answer('Aur last date kya hai?', sid)
        assert second['context_used'] is True
        assert second['context_name'] == rec['name']
        assert 'Usi scheme' in reply
        assert 'last date nahi di gayi' in reply
        assert len(calls) == 1, 'follow-up must not re-run retrieval'

        _, _, third = pipeline.rag_answer('PM Kisan scholarship documents?', sid)
        assert third['context_used'] is False
        assert len(calls) == 2, 'a new scheme must retrieve again'
    finally:
        conversation.STORE.reset(sid)
