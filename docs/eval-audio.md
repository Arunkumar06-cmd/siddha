# Speech robustness evaluation (2026-11-05)

Dev-time probe, not a benchmark. 12 Hinglish scholarship utterances synthesized with Timbre (`Avinash`, same voice as the demo), degraded to telephony conditions, then transcribed with the production Prisma configuration (`prisma-v3.0`, `language_code=indic-auto`, `format=codemix`).

**Critical-term preservation** (all key English entity/domain tokens of the utterance present in the transcript):

| Condition | Passes |
|---|---|
| 16 kHz clean | 10/12 |
| 8 kHz telephony (300–3400 Hz bandpass, 7-bit quantization) | 10/12 |
| 8 kHz telephony + traffic noise (10 dB SNR) | 11/12 |
| 8 kHz telephony + fan noise (15 dB SNR) | 11/12 |

**Honest caveats**
- The two clean-condition "failures" and one traffic-condition failure are Devanagari-script transcripts (`इंजीनियरिंग स्कॉलरशिप`) — the transcript is correct; our Latin-token metric can't credit it. WER against a Latin-script reference is meaningless for this corpus; we report critical-term preservation instead.
- Utterances are synthetic TTS, not human voices; noise beds are synthesized (brown noise + honk bursts / low-passed white noise + 50 Hz hum), not field captures.
- No overlapping speech, accents, or far-field conditions were tested.
- Reproduce: `python3 scripts/eval_audio.py` (requires `GNANI_API_KEY`; uses ~24 API credits).

**What this supports:** the demo scenario (real browser mic in a quiet room) is well inside the comfortable envelope; a noisy call-quality 8 kHz path is viable for scholarship-relevant queries, with degradation expected on Hindi-script-only answers where the answer text must also be rendered for TTS.
