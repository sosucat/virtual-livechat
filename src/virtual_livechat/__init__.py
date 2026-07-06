import os
import sys
import time
import random
import pyautogui
import ollama
import re
import json
import shutil
import subprocess
import difflib
import threading
from collections import deque
# Optional OCR support
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

# Optional speech-to-text support using Google's Web Speech API via SpeechRecognition
try:
    import speech_recognition as sr
    SR_AVAILABLE = True
except Exception:
    SR_AVAILABLE = False


def _safe_print(*args, **kwargs):
    """Print safely by encoding with the console encoding and replacing errors to avoid UnicodeEncodeError crashes."""
    enc = sys.stdout.encoding or 'utf-8'
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = []
        for a in args:
            try:
                safe_args.append(str(a))
            except Exception:
                safe_args.append(repr(a))
        try:
            out = ' '.join(safe_args)
            sys.stdout.buffer.write(out.encode(enc, 'replace') + (kwargs.get('end', '\n').encode(enc, 'replace')))
        except Exception:
            # Fallback to printing utf-8 replaced
            sys.stdout.buffer.write(out.encode('utf-8', 'replace') + b"\n")


def record_spoken_context(duration=4):
    """Record short audio and return transcribed text using Google Web Speech API.

    Preferred method: use sounddevice + soundfile (no PyAudio required) to capture audio, then feed into SpeechRecognition's AudioFile for transcription.
    Falls back to sr.Microphone() if sounddevice is not available.
    """
    if not SR_AVAILABLE:
        print("[Info] speech_recognition not installed — spoken context unavailable.")
        return None
    r = sr.Recognizer()

    # Try sounddevice-based capture first (does not require PyAudio)
    try:
        import sounddevice as sd
        import soundfile as sf
        import tempfile
        import os
        fs = 16000
        print(f"Recording {duration}s of spoken context via sounddevice — please speak now...")
        data = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
        sd.wait()
        tf = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
        try:
            sf.write(tf.name, data, fs)
            # Use SpeechRecognition's AudioFile wrapper to transcribe the saved wav
            source = sr.AudioFile(tf.name)
            source.__enter__()
            audio = r.record(source)
            try:
                text = r.recognize_google(audio)
                print('[Info] Transcribed spoken context:', text)
                return text
            except sr.UnknownValueError:
                print('[Info] Speech was not understood.')
                return None
            except sr.RequestError as e:
                print(f'[Info] Speech recognition service failed: {e}')
                return None
            finally:
                try:
                    source.__exit__(None, None, None)
                except Exception:
                    pass
        finally:
            try:
                os.unlink(tf.name)
            except Exception:
                pass
    except Exception as e:
        # If sounddevice path fails (missing package or no microphone), fall back to sr.Microphone
        try:
            with sr.Microphone() as source:
                print(f"Recording {duration}s of spoken context — please speak now...")
                r.adjust_for_ambient_noise(source, duration=0.5)
                audio = r.listen(source, phrase_time_limit=duration)
            try:
                text = r.recognize_google(audio)
                print('[Info] Transcribed spoken context:', text)
                return text
            except sr.UnknownValueError:
                print('[Info] Speech was not understood.')
                return None
            except sr.RequestError as e:
                print(f'[Info] Speech recognition service failed: {e}')
                return None
        except Exception as e2:
            print(f'[Info] Failed recording audio: {e} ; fallback error: {e2}')
            return None

# Choose default model: prefer llava if it's already available locally via the Ollama CLI.
# Fallback to moondream otherwise.
def _choose_default_model():
    preferred = 'llava'
    fallback = 'moondream'
    try:
        if shutil.which('ollama') is None:
            return fallback
        # call ollama list to see available models (fast; does not pull models)
        proc = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0 and preferred in proc.stdout:
            return preferred
    except Exception:
        pass
    return fallback

MODEL_NAME = _choose_default_model()
# MODEL_NAME = 'moondream'  # previous default

# A list of simulated usernames to make the chat look authentic
USERNAMES = [
    "GamerX_99", "PandaExpress", "SpeedRunner", "KappaLord", "PixelArtist", 
    "NoobMaster", "W00t_Twitch", "StreamSniper", "GlitchCat", "PogChamp_1", 
    "VibeCheck", "Slayer_Z", "ChromaKey", "MutedMic", "AFK_Brain"
]

import ctypes
from ctypes import wintypes
from PIL import ImageGrab

def _list_monitors_windows():
    """Return a list of monitor rects as dicts: left, top, width, height."""
    monitors = []
    try:
        user32 = ctypes.windll.user32
        # Define RECT
        class RECT(ctypes.Structure):
            _fields_ = [('left', ctypes.c_long), ('top', ctypes.c_long), ('right', ctypes.c_long), ('bottom', ctypes.c_long)]
        MonitorEnumProc = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(RECT), wintypes.LPARAM)
        def _callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
            r = lprcMonitor.contents
            monitors.append({'left': r.left, 'top': r.top, 'width': r.right - r.left, 'height': r.bottom - r.top})
            return 1
        user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_callback), 0)
    except Exception:
        pass
    return monitors


def capture_screen():
    """Capture the second monitor (index 1) on Windows using PIL.ImageGrab. Fallback to pyautogui full-screen.

    Returns path to saved PNG screenshot (temp_screen.png).
    """
    screenshot_path = "temp_screen.png"
    # Try Windows monitor listing via ctypes + PIL
    try:
        monitors = _list_monitors_windows()
        if monitors:
            # choose second monitor if present, otherwise primary
            mon = monitors[2] if len(monitors) >= 3 else monitors[0]
            left = mon['left']; top = mon['top']; right = left + mon['width']; bottom = top + mon['height']
            img = ImageGrab.grab(bbox=(left, top, right, bottom))
            img.save(screenshot_path)
            return screenshot_path
    except Exception:
        # fall back to pyautogui
        pass

    # Fallback: whole-screen screenshot via pyautogui
    try:
        screenshot = pyautogui.screenshot()
        screenshot.save(screenshot_path)
        return screenshot_path
    except Exception:
        # As a last resort, create a blank 1x1 PNG so callers don't crash
        from PIL import Image
        Image.new('RGB', (1,1), (0,0,0)).save(screenshot_path)
        return screenshot_path

def generate_chat_reactions(image_path, user_context=None):
    """Sends the screenshot to the local model and requests chat reactions.

    user_context: optional string provided by the user (e.g., from speech-to-text).
    """
    base_prompt = (
        "You are an active live streaming chat audience (like Twitch or YouTube Live) watching a remote worker working on their PC. "
        "First, carefully inspect the screenshot and provide 1–2 short factual observations ABOUT WHAT IS VISIBLY ON THE SCREEN. "
        "Be literal and do NOT infer intentions, identities, or unseen context. Keep observations to concrete visible elements.\n\n"
        "Then, using ONLY those observations, write 3 to 5 distinct short chat reactions (1 line each) that a live audience would make. Reactions must reference only the facts you listed and must NOT hallucinate details. Use typical internet slang and emotes when appropriate.\n\n"
        "OUTPUT FORMAT (exact):\n"
        "FACTS:\n"
        "- <one factual observation per line, 1–2 lines>\n\n"
        "REACTIONS:\n"
        "- <reaction line 1>\n"
        "- <reaction line 2>\n"
        "- <reaction line 3>\n\n"
        "If the image is unreadable or blank, the FACTS section should contain a single line: '- UNREADABLE_IMAGE' and the REACTIONS section should be empty (no reaction lines).\n\n"
    )

    # Optionally run OCR to extract visible text and include it as a preliminary FACT
    ocr_text = None
    if OCR_AVAILABLE:
        try:
            img = Image.open(image_path)
            ocr_text = pytesseract.image_to_string(img).strip()
            img.close()
            if ocr_text:
                base_prompt += "If any readable text is visible on the screen, include it as a FACT line prefixed with 'OCR_TEXT: '.\n\n"
        except Exception:
            ocr_text = None

    # Add a couple few-shot examples to anchor expected format and style
    examples = (
        "Example 1:\nFACTS:\n- A red health bar at top-left\n- Large white text at bottom: YOU DIED\n\nREACTIONS:\n- Pog that last hit!\n- No way, clutch comeback incoming\n- RIP, deserves a respawn\n\n"
        "Example 2:\nFACTS:\n- A browser window showing a music player with play/pause icon\n- Large yellow 'LIVE' badge at top-right\n\nREACTIONS:\n- This track slapsss 🔥\n- Tune in, this is the vibe\n- Turn it up, chat!\n\n"
        "Example 3:\nFACTS:\n- A code editor with a highlighted compiler error on line 42\n- The error message contains 'NullReferenceException'\n\nREACTIONS:\n- Oh no, null refs strikes again 😬\n- Somebody call the debugger!\n- Patch incoming, squad\n\n"
        "Example 4:\nFACTS:\n- A document editor showing large text: 'Quarterly Report - Draft'\n- A small comment bubble on the right saying 'Please review figures'\n\nREACTIONS:\n- Oof, crunch time for that report 📊\n- Review the numbers, don't trust auto-format!\n- Someone send coffee ☕\n\n"
        "Example 5:\nFACTS:\n- A video player paused at 01:23 with big 'LIVE' indicator\n- The play button is visible and the timeline is near the end\n\nREACTIONS:\n- Let's goooo, final boss time!\n- That cliffhanger though 😱\n- Chat, spam hype emotes!\n\n"
        "Example 6:\nFACTS:\n- A terminal window showing 'BUILD FAILED' in red\n- Several stack trace lines are visible above the message\n\nREACTIONS:\n- Build failed? Time to rubber-duck it 🦆\n- Debuggers assemble!\n- Re-run with verbose, chat\n\n"
    )

    # If user provided spoken context, include it prominently so the model can use it
    if user_context:
        uc = ' '.join(user_context.split())
        base_prompt += f"USER_CONTEXT: {uc}\n\n; Use this user-provided context to influence reactions but do not invent new facts.\n\n"

    # Embed image via markdown (many local LLM tooling accepts markdown image tags)
    prompt_main = base_prompt + f"Screenshot: ![screenshot]({image_path})\n\n"

    # If OCR produced text, prefill it into FACTS so the model must reference exact text
    if ocr_text:
        # sanitize single-line
        one_line = ' '.join(ocr_text.split())
        prefilled = "FACTS:\n- OCR_TEXT: \"" + one_line.replace('"', "'") + "\"\n\nREACTIONS:\n"
        prompt = examples + prefilled + prompt_main
    else:
        prompt = examples + prompt_main

    try:
        # Try to call ollama.chat with low temperature for less hallucination
        try:
            response = ollama.chat(
                model=MODEL_NAME,
                messages=[{
                    'role': 'user',
                    'content': prompt,
                    'images': [image_path]
                }],
                temperature=0.2,
                max_tokens=200
            )
        except TypeError:
            # some ollama client variants don't accept temperature/max_tokens
            try:
                response = ollama.chat(
                    model=MODEL_NAME,
                    messages=[{
                        'role': 'user',
                        'content': prompt,
                        'images': [image_path]
                    }]
                )
            except Exception:
                # last resort: try the older prompt-only signature without extras
                try:
                    response = ollama.chat(model=MODEL_NAME, prompt=prompt)
                except Exception as e:
                    raise
        except Exception:
            # generic fallback: try prompt-only signatures
            try:
                response = ollama.chat(model=MODEL_NAME, prompt=prompt)
            except Exception:
                response = ollama.chat(model=MODEL_NAME, messages=[{'role':'user','content':prompt}])

        # Normalize response to text
        content_text = ""
        if isinstance(response, str):
            content_text = response
        elif isinstance(response, dict):
            # Common patterns: {'message': {'content': '...'}}, or {'choices':[{'message':{'content':...}}]}
            if 'message' in response and isinstance(response['message'], dict) and 'content' in response['message']:
                content_text = response['message']['content']
            elif 'content' in response:
                content_text = response['content']
            elif 'choices' in response and isinstance(response['choices'], list) and len(response['choices'])>0:
                # choices may have text or message
                first = response['choices'][0]
                if isinstance(first, dict):
                    if 'message' in first and isinstance(first['message'], dict) and 'content' in first['message']:
                        content_text = first['message']['content']
                    elif 'text' in first:
                        content_text = first['text']
                    elif 'content' in first:
                        content_text = first['content']
            else:
                # last resort: stringify for debugging
                content_text = json.dumps(response)
        else:
            content_text = str(response)

        # If the response embeds a Message(...) or similar debug repr, try to extract the inner content
        msg_match = re.search(r"message\s*=\s*Message\([^)]*content=([\'\"])(.*?)\1", content_text, re.DOTALL)
        if msg_match:
            content_text = msg_match.group(2)
        else:
            # fallback: extract any content='...'/content="..." pattern
            content_match = re.search(r"content=([\'\"])(.*?)\1", content_text, re.DOTALL)
            if content_match:
                content_text = content_match.group(2)

        # Unescape common escaped newlines/quotes so strings like "a\n b" become real newlines
        if isinstance(content_text, str):
            content_text = content_text.replace('\\r\\n', '\r\n').replace('\\n', '\n').replace('\\"', '"').replace("\\'", "'")

        # Split into lines and remove common list prefixes using regex
        raw_lines = [ln.strip() for ln in content_text.strip().splitlines() if ln.strip()]
        clean = []
        for line in raw_lines:
            # remove leading list bullets/numbers like "1. ", "- ", "* ", "• "
            line = re.sub(r'^\s*([0-9]+[.)]\s*|[-\u2022\*]\s*)', '', line)
            # also strip any leading '- ' or numbering characters
            line = line.strip()
            if line:
                clean.append(line)
        # If result looks like JSON array like ["a","b"], try to parse
        if len(clean) == 1 and (clean[0].startswith('[') and clean[0].endswith(']')):
            try:
                arr = json.loads(clean[0])
                if isinstance(arr, list):
                    clean = [str(x).strip() for x in arr if str(x).strip()]
            except Exception:
                pass

        # Remove stray trailing backslashes from unescaped output
        clean = [c.rstrip('\\') for c in clean]

        # Attempt to extract FACTS and REACTIONS sections if the model followed the required format
        facts = []
        reactions = []
        fact_idx = None
        react_idx = None
        for i, v in enumerate(clean):
            up = v.strip().upper()
            if up.startswith('FACTS'):
                fact_idx = i
            if up.startswith('REACTIONS'):
                react_idx = i
                break
        # collect facts lines (between FACTS: and REACTIONS:)
        if fact_idx is not None:
            for v in clean[fact_idx+1: react_idx if react_idx is not None else None]:
                if not v or v.strip().endswith(':'):
                    break
                facts.append(v)
        # collect reactions lines (after REACTIONS:)
        if react_idx is not None:
            for v in clean[react_idx+1:]:
                if not v or v.strip().endswith(':'):
                    break
                reactions.append(v)

        # If OCR was available and produced text, include it as a fact for relevance checks
        if ocr_text:
            facts.append('OCR_TEXT: ' + ' '.join(ocr_text.split()))

        # Relevance scoring using exact and fuzzy matches
        def words(s):
            return [w.lower() for w in re.findall(r"\w+", s) if len(w)>2]
        fact_words = set()
        for f in facts:
            fact_words.update(words(f))

        def fuzzy_match(word, candidates, cutoff=0.7):
            # return True if word is similar to any candidate word
            for c in candidates:
                if difflib.SequenceMatcher(None, word, c).ratio() >= cutoff:
                    return True
            return False

        scored = []  # list of (score, reaction)
        for r in reactions:
            rw = words(r)
            exact = len(set(rw) & fact_words)
            fuzzy = 0
            for w in rw:
                if fuzzy_match(w, fact_words):
                    fuzzy += 1
            score = exact * 2 + fuzzy
            scored.append((score, r))

        # Keep reactions with score >= 1 (either exact or fuzzy match)
        filtered_reactions = [r for sc, r in scored if sc >= 1]
        if filtered_reactions:
            return filtered_reactions

        # If strict filtering removed all reactions, re-prompt the model with explicit facts to force grounded replies
        if facts:
            retry_prompt = (
                "The previous reply did not produce reactions that reference the FACTS.\n"
                "You will be given a short FACTS list. Using ONLY those facts, produce exactly 3 short chat REACTIONS (one per line). Each reaction MUST include at least one word or phrase from the FACTS. Do NOT invent new facts or details. Output exactly 3 lines and nothing else.\n\n"
                "FORMAT EXAMPLE:\n"
                "FACTS:\n"
                "- A red health bar at top-left\n\n"
                "REACTIONS:\n"
                "- Pog that red health bar saved them!\n"
                "- That 'YOU DIED' text is brutal, rip.\n"
                "- Chat, spam the revive emotes.\n\n"
                "Now produce reactions for these FACTS:\n"
                "FACTS:\n"
            )
            for f in facts:
                retry_prompt += f"- {f}\n"
            retry_prompt += "\nREACTIONS:\n"
            try:
                try:
                    retry_resp = ollama.chat(model=MODEL_NAME, messages=[{'role':'user','content':retry_prompt}], temperature=0.15, max_tokens=120)
                except TypeError:
                    retry_resp = ollama.chat(model=MODEL_NAME, messages=[{'role':'user','content':retry_prompt}])

                # normalize retry_resp into text similar to main flow
                retry_text = ''
                if isinstance(retry_resp, str):
                    retry_text = retry_resp
                elif isinstance(retry_resp, dict):
                    if 'message' in retry_resp and isinstance(retry_resp['message'], dict) and 'content' in retry_resp['message']:
                        retry_text = retry_resp['message']['content']
                    elif 'content' in retry_resp:
                        retry_text = retry_resp['content']
                    elif 'choices' in retry_resp and isinstance(retry_resp['choices'], list) and len(retry_resp['choices'])>0:
                        first = retry_resp['choices'][0]
                        if isinstance(first, dict):
                            if 'message' in first and isinstance(first['message'], dict) and 'content' in first['message']:
                                retry_text = first['message']['content']
                            elif 'text' in first:
                                retry_text = first['text']
                            elif 'content' in first:
                                retry_text = first['content']
                    else:
                        retry_text = json.dumps(retry_resp)
                else:
                    # fallback to string repr for custom objects
                    retry_text = str(retry_resp)


                # split and clean
                lines = [ln.strip() for ln in retry_text.strip().splitlines() if ln.strip()]
                cleaned = [re.sub(r'^\s*([0-9]+[.)]\s*|[-\u2022\*]\s*)', '', ln).strip() for ln in lines]
                # score again
                final = []
                for ln in cleaned:
                    rw = words(ln)
                    if any(fuzzy_match(w, fact_words) or (set([w]) & fact_words) for w in rw):
                        final.append(ln)
                if final:
                    return final[:5]
            except Exception as e:
                pass

        # As a last resort, return empty (irrelevant)
        return []

    except Exception as e:
        print(f"\n[System Error]: Failed to contact Ollama or parse response. Error: {e}")
        return []

# Continuous STT listener support (fills a rolling context buffer)
_CONTEXT_DEQUE = None
_CONTEXT_LOCK = None
_LISTENER_THREAD = None
_LISTENER_RUNNING = False
_LISTENER_OK = False


def get_continuous_context():
    """Return joined transcripts from the rolling STT buffer, or None if empty."""
    global _CONTEXT_DEQUE, _CONTEXT_LOCK
    if _CONTEXT_DEQUE is None:
        return None
    with _CONTEXT_LOCK:
        if not _CONTEXT_DEQUE:
            return None
        return ' '.join(list(_CONTEXT_DEQUE))


def stt_status():
    """Return a status dict for the STT listener and recent transcripts.

    Returns: {'running': bool, 'size': int, 'recent': [str,...]}
    """
    global _CONTEXT_DEQUE, _CONTEXT_LOCK, _LISTENER_RUNNING, _LISTENER_THREAD
    # Consider the thread alive instead of the separate _LISTENER_OK flag to reflect reality
    running = False
    try:
        running = bool(_LISTENER_RUNNING and _LISTENER_THREAD is not None and _LISTENER_THREAD.is_alive())
    except Exception:
        running = bool(_LISTENER_RUNNING)
    status = {'running': running, 'size': 0, 'recent': []}
    if _CONTEXT_DEQUE is None:
        return status
    with _CONTEXT_LOCK:
        status['size'] = len(_CONTEXT_DEQUE)
        # return up to last 5 entries
        status['recent'] = list(_CONTEXT_DEQUE)[-5:]
    return status


def start_continuous_listener(chunk_duration=4, fs=16000):
    """Start a daemon thread that continuously records short audio chunks and appends transcriptions to an in-memory buffer.

    Uses sounddevice + soundfile to capture audio and SpeechRecognition (recognize_google) for STT. Gracefully degrades on errors.
    """
    global _CONTEXT_DEQUE, _CONTEXT_LOCK, _LISTENER_THREAD, _LISTENER_RUNNING, _LISTENER_OK
    _LISTENER_OK = False
    if not SR_AVAILABLE:
        return False
    if _LISTENER_THREAD and _LISTENER_THREAD.is_alive():
        return True
    _CONTEXT_DEQUE = deque(maxlen=20)
    _CONTEXT_LOCK = threading.Lock()
    _LISTENER_RUNNING = True

    def _worker():
        try:
            import sounddevice as sd
            import soundfile as sf
            import speech_recognition as sr_local
            import tempfile, os
            r = sr_local.Recognizer()
            # mark listener OK after successful imports/init
            try:
                global _LISTENER_OK
                _LISTENER_OK = True
            except Exception:
                pass
        except Exception as e:
            # mark listener as not OK and exit
            return
        try:
            while _LISTENER_RUNNING:
                try:
                    data = sd.rec(int(chunk_duration * fs), samplerate=fs, channels=1, dtype='int16')
                    sd.wait()
                    tf = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
                    try:
                        sf.write(tf.name, data, fs)
                        source = sr_local.AudioFile(tf.name)
                        source.__enter__()
                        audio = r.record(source)
                        try:
                            text = r.recognize_google(audio)
                            text = text.strip()
                            if text:
                                with _CONTEXT_LOCK:
                                    _CONTEXT_DEQUE.append(text)
                                _safe_print(f"[STT] Heard: {text}")
                        except Exception as e:
                            pass
                        finally:
                            try:
                                source.__exit__(None, None, None)
                            except Exception:
                                pass
                    finally:
                        try:
                            os.unlink(tf.name)
                        except Exception:
                            pass
                except Exception as e:
                    pass
        finally:
            pass

    _LISTENER_THREAD = threading.Thread(target=_worker, daemon=True)
    _LISTENER_THREAD.start()
    # give a moment for thread to start
    time.sleep(0.1)
    # reflect actual thread aliveness in _LISTENER_OK
    try:
        _LISTENER_OK = bool(_LISTENER_THREAD and _LISTENER_THREAD.is_alive())
    except Exception:
        _LISTENER_OK = False
    return True


def stop_continuous_listener():
    global _LISTENER_RUNNING, _LISTENER_THREAD
    _LISTENER_RUNNING = False
    if _LISTENER_THREAD:
        try:
            _LISTENER_THREAD.join(timeout=2)
        except Exception:
            pass


def main():
    _safe_print(f"=== Starting Local Live Chat Simulator (Using {MODEL_NAME}) ===")
    _safe_print("Open up a game, video, or application on your screen.")
    _safe_print("Press Ctrl+C in this terminal to stop.")
    _safe_print("-" * 50)

    # Start continuous listener automatically when STT is available
    if SR_AVAILABLE:
        started = start_continuous_listener()
        if not started:
            _safe_print('[Info] Continuous listener failed to start; falling back to manual recording prompt')
    else:
        _safe_print('[Info] SpeechRecognition not available; manual recording disabled.')

    try:
        while True:
            # Use continuous STT context if available
            if SR_AVAILABLE:
                user_ctx = get_continuous_context()
            else:
                user_ctx = None

            # 1. Take a picture of what the user is doing
            img_path = capture_screen()

            # 2. Get the AI to act like a stream chat, supplying optional spoken context
            reactions = generate_chat_reactions(img_path, user_context=user_ctx)

            # 3. Safely delete the temporary screenshot
            if os.path.exists(img_path):
                os.remove(img_path)

            # 4. Stream the chat messages with slight, realistic delay offsets
            for reaction in reactions:
                if reaction:
                    user = random.choice(USERNAMES)
                    try:
                        _safe_print(f"[{user}]: {reaction}")
                    except Exception:
                        # Last-resort fallback
                        try:
                            sys.stdout.buffer.write((f"[{user}]: {reaction}\n").encode(sys.stdout.encoding or 'utf-8', 'replace'))
                        except Exception:
                            pass
                    # Stagger the messages so they feel like a live scrolling chat
                    time.sleep(random.uniform(0.4, 1.2))

            # 5. Wait a moment before evaluating the screen again
            time.sleep(4)

    except KeyboardInterrupt:
        print("\nStopping chat simulation. Goodbye!")

if __name__ == "__main__":
    main()