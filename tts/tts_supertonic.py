from supertonic import TTS
import threading
from queue import Queue, Empty
import re
import sounddevice as sd
import soundfile as sf
from core.config import cfg as config

class ATOM_TTS:
    engine_name = "Supertonic"
    def __init__(self):
        tts_cfg = config.get("tts", {})
        my_cfg = tts_cfg.get("supertonic", {})

        # Queues
        self.text_queue = Queue()
        self.audio_queue = Queue()

        # Start background workers
        self.running = True
        threading.Thread(target=self._tts_worker, daemon=True).start()
        threading.Thread(target=self._play_worker, daemon=True).start()

        # Buffer for sentence aggregation
        self.buffer = ""
        # Sentence boundary regex
        self.boundary = re.compile(r"[.!?;:\n]")
        self.tts = TTS(auto_download=True)
        self.style = self.tts.get_voice_style(voice_name=my_cfg.get("voice", "M1"))

    def clean_for_tts(self, text: str) -> str:
        # remove code fences
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        
        # remove inline code
        text = re.sub(r"`([^`]+)`", r"\1", text)

        # remove styling
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        text = re.sub(r"~~([^~]+)~~", r"\1", text)

        # remove headings
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)

        # remove blockquotes
        text = re.sub(r"^\s*>+\s*", "", text, flags=re.MULTILINE)

        # convert bullets into pauses
        def bullet_to_sentence(match):
            item = match.group(1).strip()
            if not item.endswith(('.', '!', '?')):
                item += '.'
            return item

        text = re.sub(r"^\s*[•\-\*]\s+(.*)$", bullet_to_sentence, text, flags=re.MULTILINE)

        # numbered lists
        text = re.sub(r"^\s*\d+\.\s+(.*)$", bullet_to_sentence, text, flags=re.MULTILINE)

        # remove horizontal rules
        text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)

        # convert links but keep anchor text
        text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)

        # images
        text = re.sub(r"!\[([^\]]*)\]\([^\)]+\)", r"\1", text)

        # remove html tags
        text = re.sub(r"<[^>]+>", "", text)

        emoji_pattern = re.compile(
            "[" 
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F680-\U0001F6FF"  # transport & map
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U00002700-\U000027BF"  # dingbats
            "\U00002600-\U000026FF"  # misc symbols
            "]+",
            flags=re.UNICODE
        )

        text = emoji_pattern.sub("", text)

        # collapse multi-line
        text = re.sub(r"\n{2,}", "\n", text)

        return text.strip()

    def text_to_wav(self, text:str):
        wav, duration = self.tts.synthesize(self.clean_for_tts(text), voice_style=self.style)
        self.tts.save_audio(wav, "tts/output.wav")

    def play_wav_nonblocking(self, path = "tts/output.wav"):
        data, samplerate = sf.read(path)
        sd.play(data, samplerate, blocking=False)  # non-blocking

    # -----------------------------------------------------------
    # BACKGROUND: TTS worker (reads buffered sentences)
    # -----------------------------------------------------------
    def _tts_worker(self):
        while self.running:
            try:
                sentence = self.text_queue.get(timeout=0.1)
            except Empty:
                continue

            if sentence is None:
                break

            sentence = self.clean_for_tts(sentence)

            # synth to wav
            wav, duration = self.tts.synthesize(sentence, voice_style=self.style)
            self.tts.save_audio(wav, "tts/output.wav")

            # load wav to pcm
            data, samplerate = sf.read("tts/output.wav", dtype="int16")

            self.sample_rate = samplerate
            self.audio_queue.put(data)

        self.audio_queue.put(None)

    # -----------------------------------------------------------
    # BACKGROUND: audio playback worker
    # -----------------------------------------------------------
    def _play_worker(self):
        while True:
            pcm = self.audio_queue.get()

            if pcm is None:
                break

            sd.play(pcm, samplerate=self.sample_rate)
            sd.wait()