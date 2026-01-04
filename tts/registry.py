# tts/registry.py
from tts.tts_edge import ATOM_TTS as EdgeTTS
from tts.tts_supertonic import ATOM_TTS as SupertonicTTS
from tts.tts_piper import ATOM_TTS as PiperTTS

TTS_ENGINES = {
    "edge": EdgeTTS,
    "supertonic": SupertonicTTS,
    "piper": PiperTTS,
}