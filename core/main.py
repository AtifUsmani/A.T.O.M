# main.py

import sys
import signal
import os
import threading
from tqdm import tqdm
from core.config import cfg as config

def ensure_generated_folder():
    folder_name = "generated"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

ensure_generated_folder()

USE_STT = bool(config['USE_STT'])

from core.llm import LLM
brain = LLM()

def init_lms(progress_bar):
    global LMS

    try:
        from core.lms import LMSTUDIO
        LMS = LMSTUDIO()
        progress_bar.update(1)

        try:
            LMS.load_model()
        except Exception as e:
            progress_bar.update(1)
            print(f"[ERROR] Failed to initialize Model: {e}")

        try:
            LMS.load_summary_model()
        except Exception as e:
            progress_bar.update(1)
            print(f"[ERROR] Failed to initialize Summary Model: {e}")
    except Exception as e:
        print(f"[ERROR] Failed to initialize LM Studio: {e}")

def init_cli(progress_bar):
    global cli

    try:
        from interfaces.cli import CLIStreamer
        cli = CLIStreamer(brain)
        progress_bar.update(1)
    except Exception as e:
        print(f"[ERROR] Failed to initialize CLI: {e}")

def init_stt(progress_bar):
    global stt, USE_STT
    if USE_STT:
        try:
            from stt.stt import STT
            stt = STT(mode='realtime')
            progress_bar.update(1)
        except Exception as e:
            print(f"[ERROR] Failed to initialize STT: {e}")
            progress_bar.update(1)
            stt = None
            USE_STT = False

def init_tts(progress_bar):
    from tts.voice import set_voice_engine

    tts_cfg = config.get("tts", {})
    tts_enabled = tts_cfg.get("enabled", False)

    if not tts_enabled:
        set_voice_engine(None)
        progress_bar.update(1)
        return

    engine_name = tts_cfg.get("engine")

    from tts.registry import TTS_ENGINES
    engine_cls = TTS_ENGINES.get(engine_name)

    if not engine_cls:
        print(
            f"[ERROR] Unknown TTS engine '{engine_name}'. "
            f"Available: {', '.join(TTS_ENGINES)}"
        )
        set_voice_engine(None)
        progress_bar.update(1)
        return

    try:
        engine = engine_cls()
        set_voice_engine(engine)
        progress_bar.update(1)

    except Exception as e:
        print(f"[ERROR] Failed to initialize TTS ({engine_name}): {e}")
        set_voice_engine(None)
        progress_bar.update(1)

def initialize():
    with tqdm(total=6, desc="Initializing") as progress_bar:
        # Start threads
        lms_thread = threading.Thread(target=init_lms, args=(progress_bar,))
        cli_thread = threading.Thread(target=init_cli, args=(progress_bar,))
        stt_thread = threading.Thread(target=init_stt, args=(progress_bar,))
        tts_thread = threading.Thread(target=init_tts, args=(progress_bar,))

        # Start the threads
        lms_thread.start()
        cli_thread.start()
        stt_thread.start()
        tts_thread.start()

        # Wait for the threads to finish before proceeding with the rest of the program
        lms_thread.join()
        cli_thread.join()
        stt_thread.join()
        tts_thread.join()

        print("Initialization completed.")

# --- Graceful Shutdown Handler -------------------------------------------------

def graceful_exit(*args):
    print("\n\n[INFO] Shutting down ATOM...")

    if config["ROBOTIC_ARM"]:
        try:
            from tools.tools import close_connections
            close_connections()
        except Exception as e:
            print(f"[WARN] Failed to close tool connections: {e}")
    else:
        pass

    try:
        LMS.unload_model()
    except Exception as e:
        print(f"[WARN] Failed to unload model: {e}")

    try:
        if USE_STT and stt:
            stt.shutdown_stt()
    except Exception as e:
        print(f"[WARN] Failed to shut down STT cleanly: {e}")
    try:
        from tts.voice import voiceEngine
        if voiceEngine and hasattr(voiceEngine, "close"):
            voiceEngine.close()
    except Exception as e:
        print(f"[WARN] Failed to shut down TTS cleanly: {e}")

    try:
        if hasattr(brain, "shutdown"):
            brain.shutdown()
    except Exception:
        pass
    
    print("\n[INFO] Exit complete. Goodbye.")
    sys.exit(0)
    
# Catch Ctrl+C globally
signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)

def main():
    # --- Main Loop -----------------------------------------------------------------
    initialize()
    i = 0

    while True:
        try:
            if i == 0:
                user_input = 'hi'
            else:
                # Get input
                if USE_STT:
                    try:
                        # user_input = stt.normal_stt()
                        user_input = stt.realtime_stt()
                    except Exception as e:
                        print(f"[ERROR] STT error: {e}")
                        continue
                else:
                    user_input = input("\nYou: ")

                # Exit condition
                if user_input.lower() in ("exit", "quit", "exit."):
                    graceful_exit()
            i = i + 1
            # Process LLM output
            try:
                # cli.stream_to_console(user_input)
                full_output = ''
                for delta in cli.stream_to_console(user_input):
                    # print(delta, end="", flush=True)
                    full_output += delta

                    # if USE_TTS and voiceEngine:
                    #     # voiceEngine.push_text(delta)
                # print(full_output)
                # for_tts = voiceEngine.clean_for_tts(full_output)
                # if USE_TTS and voiceEngine:
                #         voiceEngine.text_to_wav(llm_output=for_tts)
                #         voiceEngine.play_wav_nonblocking()
                
            except Exception as e:
                print(f"\n[ERROR] CLI/LLM streaming error: {e}")

            # if USE_TTS and voiceEngine:
            #     try:
            #         voiceEngine.finish()
            #     except Exception as e:
            #         print(f"[ERROR] TTS finish error: {e}")

        except KeyboardInterrupt:
            graceful_exit()
        except Exception as e:
            print(f"[UNHANDLED ERROR] {e}")
