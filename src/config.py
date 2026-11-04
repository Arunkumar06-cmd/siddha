"""Configuration: typed, validated, single source of truth."""
import os, pathlib, logging, sys

def _env():
    env = {}
    p = pathlib.Path('/Users/arunkumar/.env')
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env

E = _env()
GNANI_API_KEY = E.get('GNANI_API_KEY', '').strip()
if not GNANI_API_KEY:
    raise RuntimeError('GNANI_API_KEY missing in ~/.env')

GNANI_BASE = 'https://api.vachana.ai'
STT_MODEL = 'prisma-v3.0'
TTS_MODEL = 'timbre-v3.0'
TTS_VOICE = 'Shivani'
TTS_LANG = 'hi-en'
TTS_SPEED = 1.0

HOST = os.getenv('SAATHI_HOST', '0.0.0.0')
PORT = int(os.getenv('SAATHI_PORT', '8765'))

LOG_FORMAT = '%(asctime)s %(levelname)s [%(name)s] %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
logger = logging.getLogger('saathi')
