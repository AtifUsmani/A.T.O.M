# main.py

import sys
import signal
import yaml
import os
import threading
from tqdm import tqdm

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file) or {}

def ensure_generated_folder():
    folder_name = "generated"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

ensure_generated_folder()

USE_STT = bool(config['USE_STT'])
USE_TTS = bool(config['USE_TTS'])

from tts.tts_piper import TTS
from llm import LLM
brain = LLM()

def init_cli(progress_bar):
    global cli

    try:
        from cli import CLIStreamer
        cli = CLIStreamer(brain)
        progress_bar.update(1)
    except Exception as e:
        print(f"[ERROR] Failed to initialize CLI: {e}")

# Function to initialize STT
def init_stt(progress_bar):
    global stt, USE_STT
    if USE_STT:
        try:
            from stt.stt import STT
            stt = STT()
            progress_bar.update(1)
        except Exception as e:
            print(f"[ERROR] Failed to initialize STT: {e}")
            progress_bar.update(1)
            stt = None
            USE_STT = False

# Function to initialize TTS
def init_tts(progress_bar):
    global tts, USE_TTS
    try:
        tts = TTS()
        progress_bar.update(1)
    except Exception as e:
        print(f"[ERROR] Failed to initialize TTS: {e}")
        progress_bar.update(1)
        tts = None
        USE_TTS = False

def initialize():
    # Create a progress bar with total 2 tasks (STT and TTS)
    with tqdm(total=3, desc="Initializing") as progress_bar:
        # Start threads
        cli_thread = threading.Thread(target=init_cli, args=(progress_bar,))
        stt_thread = threading.Thread(target=init_stt, args=(progress_bar,))
        tts_thread = threading.Thread(target=init_tts, args=(progress_bar,))

        # Start the threads
        cli_thread.start()
        stt_thread.start()
        tts_thread.start()

        # Wait for the threads to finish before proceeding with the rest of the program
        cli_thread.join()
        stt_thread.join()
        tts_thread.join()

        print("Initialization completed.")

# --- Graceful Shutdown Handler -------------------------------------------------

def graceful_exit(*args):
    print("\n\n[INFO] Shutting down ATOM...")

    try:
        if USE_STT and stt:
            stt.shutdown_stt()
    except Exception as e:
        print(f"[WARN] Failed to shut down STT cleanly: {e}")

    try:
        if USE_TTS and tts:
            tts.close() if hasattr(tts, "close") else None
    except Exception as e:
        print(f"[WARN] Failed to shut down TTS cleanly: {e}")

    try:
        if hasattr(brain, "shutdown"):
            brain.shutdown()
    except Exception:
        pass

    print("[INFO] Exit complete. Goodbye.")
    sys.exit(0)

# Catch Ctrl+C globally
signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)


def main():
    # --- Main Loop -----------------------------------------------------------------
    initialize()

    while True:
        try:
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

            # Process LLM output
            try:
                # cli.stream_to_console(user_input)
                full_output = ''
                for delta in cli.stream_to_console(user_input):
                    # print(delta, end="", flush=True)
                    full_output += delta

                    # if USE_TTS and tts:
                    #     # tts.push_text(delta)
                # print(full_output)
                for_tts = tts.clean_for_tts(full_output)
                if USE_TTS and tts:
                        tts.text_to_wav(llm_output=for_tts)
                        tts.play_wav_nonblocking()
                
            except Exception as e:
                print(f"\n[ERROR] CLI/LLM streaming error: {e}")

            # if USE_TTS and tts:
            #     try:
            #         tts.finish()
            #     except Exception as e:
            #         print(f"[ERROR] TTS finish error: {e}")

        except KeyboardInterrupt:
            graceful_exit()
        except Exception as e:
            print(f"[UNHANDLED ERROR] {e}")
