import os
import time
import random
import pyautogui
import ollama

# Define the local vision model you downloaded via Ollama
# 'moondream' is fast and lightweight. You can also use 'llava'.
MODEL_NAME = 'moondream' 

# A list of simulated usernames to make the chat look authentic
USERNAMES = [
    "GamerX_99", "PandaExpress", "SpeedRunner", "KappaLord", "PixelArtist", 
    "NoobMaster", "W00t_Twitch", "StreamSniper", "GlitchCat", "PogChamp_1", 
    "VibeCheck", "Slayer_Z", "ChromaKey", "MutedMic", "AFK_Brain"
]

def capture_screen():
    """Takes a screenshot of the main display and saves it temporarily."""
    screenshot = pyautogui.screenshot()
    screenshot_path = "temp_screen.png"
    screenshot.save(screenshot_path)
    return screenshot_path

def generate_chat_reactions(image_path):
    """Sends the screenshot to the local model and requests chat reactions."""
    prompt = (
        "You are an active live streaming chat audience (like Twitch or YouTube Live) watching a stream. "
        "Look closely at this screenshot of the screen. Generate 3 to 5 distinct, short chat reactions "
        "based strictly on what is happening on the screen right now. Use typical internet slang, "
        "capitalization, and gaming emotes (like POG, LUL, Kappa, W, L, gg, bro what?, let's goooo) where appropriate. "
        "Format the output strictly as a list of plain lines, one reaction per line. Do not include usernames or numbers."
    )

    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [image_path]
            }]
        )
        
        # Split the text into individual lines and clean them up
        raw_lines = response['message']['content'].strip().split('\n')
        reactions = [line.strip('- *12345. ') for line in raw_lines if line.strip()]
        return reactions
    except Exception as e:
        print(f"\n[System Error]: Failed to contact Ollama. Is it running? Error: {e}")
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
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nStopping chat simulation. Goodbye!")

if __name__ == "__main__":
    main()