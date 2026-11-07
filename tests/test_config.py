"""Config resolution: env wins, dotenv fallback, actionable failure.

These tests call the resolver with injected paths instead of reloading the
module, so they never depend on the developer's real home directory.
"""
import pathlib

import pytest

import config


def _env_file(path: pathlib.Path, text: str) -> pathlib.Path:
    path.write_text(text, encoding='utf-8')
    return path


def test_environment_variable_wins_over_files(tmp_path):
    dotenv = _env_file(tmp_path / '.env', 'GNANI_API_KEY=from-file\n')
    key = config._resolve_api_key(
        environ={'GNANI_API_KEY': 'from-env'},
        search_paths=(dotenv,),
    )
    assert key == 'from-env'


def test_dotenv_fallback_when_env_missing(tmp_path):
    dotenv = _env_file(tmp_path / '.env', 'GNANI_API_KEY="from-file"\n')
    assert config._resolve_api_key(environ={}, search_paths=(dotenv,)) == 'from-file'


def test_missing_key_raises_actionable_error(tmp_path):
    with pytest.raises(RuntimeError, match='GNANI_API_KEY not found'):
        config._resolve_api_key(environ={}, search_paths=(tmp_path / 'absent.env',))


def test_load_env_file_skips_comments_blanks_and_strips_quotes(tmp_path):
    dotenv = _env_file(
        tmp_path / '.env',
        '# comment\n\nGNANI_API_KEY = "abc"\nOTHER=1\n',
    )
    assert config._load_env_file(dotenv) == {'GNANI_API_KEY': 'abc', 'OTHER': '1'}


def test_load_env_file_missing_returns_empty(tmp_path):
    assert config._load_env_file(tmp_path / 'absent.env') == {}


def test_default_lookup_does_not_read_repository_dotenv(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    repo = tmp_path / 'repo'
    home.mkdir()
    repo.mkdir()
    (repo / '.env').write_text('GNANI_API_KEY=repo-key\n', encoding='utf-8')
    monkeypatch.setattr(pathlib.Path, 'home', classmethod(lambda cls: home))
    monkeypatch.chdir(repo)
    with pytest.raises(RuntimeError, match='GNANI_API_KEY not found'):
        config._resolve_api_key(environ={})


def test_first_file_with_a_key_wins(tmp_path):
    first = _env_file(tmp_path / 'one.env', 'GNANI_API_KEY=first\n')
    second = _env_file(tmp_path / 'two.env', 'GNANI_API_KEY=second\n')
    assert config._resolve_api_key(environ={}, search_paths=(first, second)) == 'first'


def test_blank_env_value_falls_through_to_file(tmp_path):
    dotenv = _env_file(tmp_path / '.env', 'GNANI_API_KEY=file\n')
    key = config._resolve_api_key(
        environ={'GNANI_API_KEY': '   '},
        search_paths=(dotenv,),
    )
    assert key == 'file'
