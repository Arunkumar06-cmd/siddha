"""OpenAI-compatible chat-completions client (opt-in, for the eligibility path).

Never required: when LLM_API_KEY is absent or the provider fails, callers fall
back to the existing grounded responder, unchanged. The key is read from the
environment or the same dotenv files Gnani uses (resolved by eligibility.py),
never committed, never logged.
"""
import os
import pathlib

import requests

LLM_API_BASE = os.getenv('LLM_API_BASE', 'https://api.deepseek.com/v1').rstrip('/')
LLM_MODEL = os.getenv('LLM_MODEL', 'deepseek-chat')
_TIMEOUT = 25


def configured():
    """True when an LLM endpoint is explicitly configured."""
    return bool((os.getenv('LLM_API_KEY') or '').strip())


def _load_env_file(path):
    env = {}
    try:
        for line in path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except (FileNotFoundError, PermissionError, OSError):
        pass
    return env


def _key():
    key = (os.getenv('LLM_API_KEY') or '').strip()
    if key:
        return key
    for candidate in (pathlib.Path.home() / '.env', pathlib.Path('.env')):
        key = _load_env_file(candidate).get('LLM_API_KEY', '').strip()
        if key:
            return key
    return None


def complete(messages, max_tokens=400, temperature=0.1):
    """Send one chat turn; raise on any failure so callers can fall back safely."""
    key = _key()
    if not key:
        raise RuntimeError('LLM_API_KEY not configured')
    r = requests.post(
        f'{LLM_API_BASE}/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json={
            'model': LLM_MODEL,
            'messages': messages,
            'temperature': temperature,
            'max_tokens': max_tokens,
        },
        timeout=_TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(f'LLM http {r.status_code}')
    j = r.json()
    return j['choices'][0]['message']['content']
