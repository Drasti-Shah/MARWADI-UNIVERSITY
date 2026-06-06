"""Voice provider selector: Sarvam when configured, else Bhashini.

Import this everywhere instead of a specific provider:  from . import voice
Then call voice.speech_to_english_gu(...), voice.english_to_speech_gu(...), etc.
"""
from __future__ import annotations

from . import config

if config.use_sarvam():
    from . import sarvam as _impl
else:
    from . import bhashini as _impl

# Re-export the common voice surface.
speech_to_english_gu = _impl.speech_to_english_gu
speech_to_english = _impl.speech_to_english
english_to_speech_gu = _impl.english_to_speech_gu
english_to_speech = _impl.english_to_speech
gu_to_speech = _impl.gu_to_speech
translate = _impl.translate
warm_up = _impl.warm_up
aclose = _impl.aclose
to_twilio_pcm16 = _impl.to_twilio_pcm16

PROVIDER = "sarvam" if config.use_sarvam() else "bhashini"
