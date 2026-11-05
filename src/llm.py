"""OpenAI-compatible chat-completions client (opt-in, for the eligibility path).

Never required: when LLM_API_KEY is absent or the provider fails, callers fall
back to the existing grounded responder, unchanged. Configuration (base URL,
model, key) resolves from the environment, then ~/.env, then ./.env — the same
dotenv files Gnani uses. Never committed, never logged.
"""
import os
import pathlib
import time

import requests

_TIMEOUT = 35


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


def _env(name, default):
    value = (os.getenv(name) or '').strip()
    if value:
        return value
    for candidate in (pathlib.Path.home() / '.env', pathlib.Path('.env')):
        value = _load_env_file(candidate).get(name, '').strip()
        if value:
            return value
    return default


LLM_API_BASE = _env('LLM_API_BASE', 'https://api.deepseek.com/v1').rstrip('/')
LLM_MODEL = _env('LLM_MODEL', 'deepseek-chat')


def configured():
    """True when an LLM endpoint is configured (env or dotenv)."""
    return bool(_key())


def _key():
    return _env('LLM_API_KEY', '') or None


def complete(messages, max_tokens=400, temperature=0.1):
    """Send one chat turn; a single retry on 429 (retry-after honoured); any
    other failure raises so callers fall back to grounded templates."""
    key = _key()
    if not key:
        raise RuntimeError('LLM_API_KEY not configured')
    for attempt in range(2):
        r = requests.post(
            f'{LLM_API_BASE}/chat/completions',
            headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
            json={
                'model': LLM_MODEL,
                'messages': messages,
                'temperature': temperature,
                'max_tokens': max_tokens,
                # nemotron-family models default to reasoning mode, which burns the
                # whole budget on reasoning_content and returns content=None.
                'chat_template_kwargs': {'enable_thinking': False},
            },
            timeout=_TIMEOUT,
        )
        if r.status_code == 429 and attempt == 0:
            try:
                wait = min(float(r.headers.get('retry-after', '2') or '2'), 2)
            except ValueError:
                wait = 2
            time.sleep(wait)
            continue
        break
    if r.status_code != 200:
        raise RuntimeError(f'LLM http {r.status_code}')
    j = r.json()
    return j['choices'][0]['message']['content']
