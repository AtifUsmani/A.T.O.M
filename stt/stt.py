import RealtimeSTT
import logging

class STT:
    def __init__(self):
        self.recorder_normal = None
        self.recorder_realtime = None

        try:
            self.recorder_normal = RealtimeSTT.AudioToTextRecorder(
                model="tiny.en",
                enable_realtime_transcription=False
            )

            self.recorder_realtime = RealtimeSTT.AudioToTextRecorder(
                model="tiny.en",
                realtime_model_type="tiny.en",
                language="en",
                enable_realtime_transcription=True,
                # on_realtime_transcription_update=on_partial,
                # on_realtime_transcription_stabilized=on_partial,  # optional
                post_speech_silence_duration=0.7,
                silero_sensitivity=0.05,
                webrtc_sensitivity=3,
                min_length_of_recording=1.1,
                min_gap_between_recordings=0,
                no_log_file=False,
                silero_use_onnx=True,
                handle_buffer_overflow=False,
                level=logging.ERROR
            )
        except Exception as e:
            print(f"[ERROR] Failed to initialize RealtimeSTT recorder: {e}")
            self.recorder_normal = None
            self.recorder_realtime = None

    def realtime_stt(self):
        if self.recorder_realtime is None:
            print("[ERROR] STT recorder is not initialized.")
            return ""
        try:
            text = self.recorder_realtime.text()
            return text if isinstance(text, str) else ""
        except Exception as e:
            print(f"[ERROR] STT realtime_stt() failed: {e}")
            return ""

    def normal_stt(self):
        """
        Blocking speech-to-text. Returns "" on any error instead of crashing.
        """
        if self.recorder_normal is None:
            print("[ERROR] STT recorder is not initialized.")
            return ""

        try:
            text = self.recorder_normal.text()  # Blocking call
            return text if isinstance(text, str) else ""
        except Exception as e:
            print(f"[ERROR] STT normal_stt() failed: {e}")
            return ""
        
    def stt_from_bytes(self, audio_bytes):
        # Save bytes → temp wav
        with open("temp.wav", "wb") as f:
            f.write(audio_bytes)

        return self.recorder_normal.text_from_file("temp.wav")


    def shutdown_stt(self):
        """
        Safely shut down the STT system.
        """
        if self.recorder_normal is None:
            return

        try:
            self.recorder_normal.shutdown()
        except Exception as e:
            print(f"[WARN] Failed to shutdown STT recorder cleanly: {e}")
    
    def transcribe_for_api(self, audio_bytes):
        # Save bytes → temp wav
        with open("temp.wav", "wb") as f:
            f.write(audio_bytes)

        return self.transcribe_audio()

    def transcribe_audio(
            self,
        audio_input: str = "temp.wav",
        model_size: str = "tiny",
        language: str = None,
        beam_size: int = 5,
        without_timestamps: bool = True
    ) -> str:
        import io
        from faster_whisper import WhisperModel

        """
        `audio_input` can be:
        - a file path (str or Path)
        - bytes
        - a file-like object (.read())
        """

        if isinstance(audio_input, (str, bytes)):
            input_for_model = audio_input
        elif hasattr(audio_input, "read"):
            data = audio_input.read()
            input_for_model = io.BytesIO(data)
        else:
            raise ValueError("audio_input must be filepath, bytes, or file-like object")

        # Load model
        model = WhisperModel(model_size, device="auto", compute_type="auto")

        # Transcribe
        segments, info = model.transcribe(
            input_for_model,
            language=language,
            beam_size=beam_size,
        )

        # Build transcript
        transcript = []
        for seg in segments:
            if without_timestamps:
                transcript.append(seg.text)
            else:
                transcript.append(f"[{seg.start:.2f}–{seg.end:.2f}] {seg.text}")

        return " ".join(transcript)