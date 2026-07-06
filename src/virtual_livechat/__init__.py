import os
import time
import random
import pyautogui
import ollama
import re
import json
import shutil
import subprocess

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

def generate_chat_reactions(image_path):
    """Sends the screenshot to the local model and requests chat reactions."""
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

    # Embed image via markdown (many local LLM tooling accepts markdown image tags)
    prompt = base_prompt + f"Screenshot: ![screenshot]({image_path})\n\n" 

    try:
        # Try to call ollama.chat similarly to previous usage; keep messages param if supported
        try:
            response = ollama.chat(
                model=MODEL_NAME,
                messages=[{
                    'role': 'user',
                    'content': prompt
                }]
            )
        except Exception:
            # fallback to older signature that accepts prompt
            response = ollama.chat(model=MODEL_NAME, prompt=prompt)

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

        # Attempt to extract the REACTIONS section if the model followed the required format
        reactions = []
        react_idx = None
        for i, v in enumerate(clean):
            if v.strip().upper().startswith('REACTIONS'):
                react_idx = i
                break
        if react_idx is not None:
            for v in clean[react_idx+1:]:
                # stop if next header or empty
                if not v or v.strip().endswith(':'):
                    break
                reactions.append(v)
            if reactions:
                return reactions

        # Fallback: remove header tokens and return remaining lines
        filtered = [x for x in clean if x.strip().upper() not in ('FACTS:', 'REACTIONS:')]
        if filtered:
            return filtered

        # Basic sanity: ensure lines aren't gibberish (very short or non-alphanumeric majority)
        if not clean:
            print("\n[Debug] Ollama returned no parseable text. Raw response:")
            print(content_text)
            return []

        return clean

    except Exception as e:
        print(f"\n[System Error]: Failed to contact Ollama or parse response. Error: {e}")
        return []

def main():
    print(f"=== Starting Local Live Chat Simulator (Using {MODEL_NAME}) ===")
    print("Open up a game, video, or application on your screen.")
    print("Press Ctrl+C in this terminal to stop.")
    print("-" * 50)

    try:
        while True:
            # 1. Take a picture of what the user is doing
            img_path = capture_screen()

            # 2. Get the AI to act like a stream chat
            reactions = generate_chat_reactions(img_path)

            # 3. Safely delete the temporary screenshot
            if os.path.exists(img_path):
                os.remove(img_path)

            # 4. Stream the chat messages with slight, realistic delay offsets
            for reaction in reactions:
                if reaction:
                    user = random.choice(USERNAMES)
                    print(f"[{user}]: {reaction}")
                    # Stagger the messages so they feel like a live scrolling chat
                    time.sleep(random.uniform(0.4, 1.2))

            # 5. Wait a moment before evaluating the screen again
            time.sleep(4)

    except KeyboardInterrupt:
        print("\nStopping chat simulation. Goodbye!")

if __name__ == "__main__":
    main()