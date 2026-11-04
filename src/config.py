"""Configuration: typed, validated, single source of truth.

Resolution order for the API key:
  1. GNANI_API_KEY environment variable (CI, containers)
  2. ~/.env (developer machines)
  3. ./.env (repo root, local overrides — never commit)
Raises RuntimeError with an actionable message otherwise."""
import logging
import os
import pathlib
import sys

LOG_FORMAT = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
logger = logging.getLogger('siddha')


def _load_env_file(path: pathlib.Path) -> dict:
    env = {}
    try:
        text = path.read_text(encoding='utf-8')
    except (FileNotFoundError, PermissionError):
        return env
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _resolve_api_key(environ: dict | None = None,
                     search_paths: tuple[pathlib.Path, ...] | None = None) -> str:
    """Resolve the Gnani key from env first, then dotenv files.

    Paths are injectable so this can be tested without touching the developer's
    real home directory or mutating module-level state.
    """
    environ = os.environ if environ is None else environ
    key = (environ.get('GNANI_API_KEY') or '').strip()
    if key:
        return key
    if search_paths is None:
        search_paths = (pathlib.Path.home() / '.env', pathlib.Path('.env'))
    for candidate in search_paths:
        env = _load_env_file(candidate)
        key = env.get('GNANI_API_KEY', '').strip()
        if key:
            logger.info('GNANI_API_KEY loaded from %s', candidate)
            return key
    raise RuntimeError(
        'GNANI_API_KEY not found. Set it in ~/.env, in ./.env, or as an environment '
        'variable (CI: use a placeholder — tests mock all external calls).'
    )


GNANI_API_KEY = _resolve_api_key()

GNANI_BASE = os.getenv('GNANI_BASE', 'https://api.vachana.ai')
STT_MODEL = os.getenv('STT_MODEL', 'prisma-v3.0')
TTS_MODEL = os.getenv('TTS_MODEL', 'timbre-v3.0')
TTS_VOICE = os.getenv('TTS_VOICE', 'Shivani')
TTS_LANG = os.getenv('TTS_LANG', 'hi-en')
TTS_SPEED = 1.0

HOST = os.getenv('SIDDHA_HOST', '127.0.0.1')  # secure default; set SIDDHA_HOST=0.0.0.0 to expose LAN
PORT = int(os.getenv('SIDDHA_PORT', '8765'))
