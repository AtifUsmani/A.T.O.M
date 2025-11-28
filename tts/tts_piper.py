import subprocess
import threading
import numpy as np
from queue import Queue, Empty
import re
import wave
from piper import PiperVoice
import sounddevice as sd
import soundfile as sf

class TTS:
    def __init__(self, model_path="tts/en_US-lessac-medium.onnx", sample_rate=22050):
        self.model_path = model_path
        self.sample_rate = sample_rate

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
        self.voice = PiperVoice.load(self.model_path)

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

    def text_to_wav(self, llm_output):
        with wave.open("tts/output.wav", "wb") as wav_file:
            self.voice.synthesize_wav(llm_output, wav_file)

    def play_wav_nonblocking(self, path = "tts/output.wav"):
        data, samplerate = sf.read(path)
        sd.play(data, samplerate, blocking=False)  # non-blocking

    # -----------------------------------------------------------
    # INTERNAL: convert text → PCM using Piper
    # -----------------------------------------------------------
    def _synthesize(self, text):
        p = subprocess.Popen(
            ["piper", "--model", self.model_path, "--output_raw"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE
        )
        raw, _ = p.communicate(text.encode("utf-8"))
        return np.frombuffer(raw, dtype=np.int16)

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

            pcm = self._synthesize(sentence)
            self.audio_queue.put(pcm)

        self.audio_queue.put(None)

    # -----------------------------------------------------------
    # BACKGROUND: audio playback worker
    # -----------------------------------------------------------
    def _play_worker(self):
        while True:
            pcm = self.audio_queue.get()

            if pcm is None:
                sd.wait()
                break

            sd.play(pcm, samplerate=self.sample_rate)

    # -----------------------------------------------------------
    # PUBLIC: Push streaming text (this is called from LLM loop)
    # -----------------------------------------------------------
    def push_text(self, text_chunk):
        """
        Accept raw delta tokens from the LLM
        and convert them into full sentences.
        """

        if not text_chunk:
            return

        self.buffer += text_chunk

        # If a sentence boundary exists → flush one full sentence
        if self.boundary.search(self.buffer):
            sentences = re.split(r"([.!?;:\n])", self.buffer)

            # Combine pairs: ["Hello", ".", " How are", "?", " ..."]
            combined = []
            for i in range(0, len(sentences) - 1, 2):
                combined.append(sentences[i] + sentences[i+1])

            # Send complete sentences to TTS
            for s in combined:
                clean = s.strip()
                if clean:
                    self.text_queue.put(clean)

            # Keep the leftover partial sentence
            self.buffer = sentences[-1]

    # -----------------------------------------------------------
    # PUBLIC: call at the end to flush leftover text
    # -----------------------------------------------------------
    def finish(self):
        leftover = self.buffer.strip()
        if leftover:
            self.text_queue.put(leftover)

        self.buffer = ""

        self.text_queue.put(None)
        self.running = False