# API

Base: `/api`. All requests: JSON. All errors: `{"error": "..."}` with typed status code.

## POST /api/ask_text
**Body:** `{"text": string (2–500 chars)}`
**200:** `{transcript, reply, sources[], audio_wav_b64}`
**422:** Invalid request (empty text / too long)
**429:** Rate limit (30/min/IP)
**502:** Provider failure (STT/TTS) — typed, no stack trace

## POST /api/ask_audio
**Body:** `multipart/form-data` with field `audio` (WAV/MP3/OGG/M4A ≤ 8 MB)
**200:** `{transcript, detected_language_code, reply, sources[], audio_wav_b64}`
**413:** Audio too large · **415:** Decode error · **502:** Provider failure

## GET /api/health
**200:** `{status: "ok", version}` · **503:** corpus missing / no key

## GET /api/metrics
**200:** counters, `stt_circuit`, `tts_circuit`, `rate_limit_per_min`

## Example
```bash
curl -s -X POST http://127.0.0.1:8765/api/ask_text \
  -H 'Content-Type: application/json' \
  -d '{"text":"SC student post-matric ke liye kaunse documents chahiye"}'
```
