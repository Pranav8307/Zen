import speech_recognition as sr
import pyttsx3
from groq import Groq
from config import ZEN_CONFIG
import subprocess
import webbrowser
import os
import sys
import pyautogui
import time
import re
import threading
import psutil
from datetime import datetime
from memory import save_note, load_memory, save_memory, update_preference, log_app, extract_and_save_facts, build_memory_context
from executor import generate_code, needs_location_clarification, classify_intent, execute_code, get_trust_level, get_system_schema, get_from_cache, save_to_cache
from reminders import add_reminder, load_reminders, list_reminders, delete_reminder, start_reminder_checker

# ── Init ──────────────────────────────────────────────────────────────────────
client = Groq(api_key=ZEN_CONFIG["groq_api_key"])
memory = load_memory()
recognizer = sr.Recognizer()
conversation_history = []

# ── App Registry ──────────────────────────────────────────────────────────────
APP_REGISTRY = {
    "whatsapp":       {"type": "store",  "uri": "whatsapp:"},
    "spotify":        {"type": "store",  "uri": "spotify:"},
    "netflix":        {"type": "store",  "uri": "netflix:"},
    "notepad":        {"type": "system", "cmd": "notepad.exe"},
    "calculator":     {"type": "system", "cmd": "calc.exe"},
    "explorer":       {"type": "system", "cmd": "explorer.exe"},
    "file explorer":  {"type": "system", "cmd": "explorer.exe"},
    "task manager":   {"type": "system", "cmd": "taskmgr.exe"},
    "settings":       {"type": "system", "cmd": "start ms-settings:"},
    "edge":           {"type": "system", "cmd": "msedge.exe"},
    "edge browser":   {"type": "system", "cmd": "msedge.exe"},
    "browser":        {"type": "web",    "url": "https://google.com"},
    "chrome":         {"type": "web",    "url": "https://google.com"},
    "chrome browser": {"type": "web",    "url": "https://google.com"},
    "google":         {"type": "web",    "url": "https://google.com"},
    "youtube":        {"type": "web",    "url": "https://youtube.com"},
    "gmail":          {"type": "web",    "url": "https://mail.google.com"},
    "maps":           {"type": "web",    "url": "https://maps.google.com"},
    "github":         {"type": "web",    "url": "https://github.com"},
    "instagram":      {"type": "web",    "url": "https://instagram.com"},
    "twitter":        {"type": "web",    "url": "https://twitter.com"},
}

# ── Speak ─────────────────────────────────────────────────────────────────────
def speak(text):
    os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'
    print(f"\nZen: {text}\n")
    try:
        import asyncio
        import edge_tts
        import tempfile
        import pygame

        voice = "en-IN-NeerjaNeural" if ZEN_CONFIG["voice"] == "female" else "en-IN-PrabhatNeural"

        async def _gen():
            communicate = edge_tts.Communicate(text, voice)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                tmp_path = f.name
            await communicate.save(tmp_path)
            return tmp_path

        # Windows-safe asyncio handling
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        tmp_path = loop.run_until_complete(_gen())
        loop.close()

        pygame.mixer.init()
        pygame.mixer.music.load(tmp_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()

        os.remove(tmp_path)

    except Exception as e:
        print(f"Voice error: {e}")
        # Fallback to pyttsx3 if edge_tts fails
        try:
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            engine.setProperty('voice', voices[1].id if ZEN_CONFIG["voice"] == "female" and len(voices) > 1 else voices[0].id)
            engine.setProperty('rate', 175)
            engine.say(text)
            engine.runAndWait()
            engine.stop()
        except:
            pass

# ── Listen ────────────────────────────────────────────────────────────────────
def listen():
    with sr.Microphone() as source:
        print("Listening... (speak now)")
        recognizer.adjust_for_ambient_noise(source, duration=0.5)
        try:
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=30)
            text = recognizer.recognize_google(audio)
            print(f"You: {text}")
            return text
        except sr.WaitTimeoutError:
            return None
        except sr.UnknownValueError:
            speak("Sorry, I didn't catch that.")
            return None
        except sr.RequestError:
            speak("Speech service unavailable.")
            return None

# ── Chat Input ────────────────────────────────────────────────────────────────
def chat_input():
    try:
        user_input = input("You (type): ").strip()
        return user_input if user_input else None
    except EOFError:
        return None

# ── Confirmation ──────────────────────────────────────────────────────────────
def get_confirmation(prompt):
    mode = ZEN_CONFIG.get("mode", "voice")
    speak(prompt)
    if mode == "voice":
        response = listen()
        return response and any(w in response.lower() for w in ["yes", "yeah", "sure", "okay", "do it", "confirm"])
    else:
        answer = input("(yes/no): ").strip().lower()
        return answer in ["yes", "y", "yeah", "sure"]

# ── Universal Launcher ────────────────────────────────────────────────────────
def launch_app(name):
    app = APP_REGISTRY.get(name.lower())
    if not app:
        return False
    if app["type"] == "store":
        os.system(f"start {app['uri']}")
    elif app["type"] == "system":
        subprocess.Popen(app["cmd"])
    elif app["type"] == "web":
        webbrowser.open(app["url"])
    return True

# ── Contact / Message helpers ─────────────────────────────────────────────────
def clean_contact(raw):
    return re.sub(r'[^a-zA-Z0-9 ]', '', raw).strip()

def clean_message(raw, contact):
    try:
        response = client.chat.completions.create(
            model=ZEN_CONFIG["model"],
            messages=[{"role": "user", "content": f"Extract and clean the message to send to {contact}. Remove formatting artifacts like ->, =>. Keep Hinglish, abbreviations. Fix spelling. Return ONLY the message.\n\nRaw: {raw}"}],
            max_tokens=150
        )
        return response.choices[0].message.content.strip()
    except:
        return raw

def send_whatsapp_message(contact, raw_message):
    try:
        contact = clean_contact(contact)
        message = clean_message(raw_message, contact)
        print(f"\nSending to {contact}: {message}\n")
        os.system("start whatsapp:")
        speak(f"Sending message to {contact}.")
        time.sleep(3)
        pyautogui.hotkey('ctrl', 'f')
        time.sleep(1)
        pyautogui.typewrite(contact, interval=0.05)
        time.sleep(2)
        pyautogui.press('enter')
        time.sleep(1)
        pyautogui.typewrite(message, interval=0.05)
        time.sleep(0.5)
        pyautogui.press('enter')
        speak(f"Message sent to {contact}.")
    except Exception as e:
        speak("Something went wrong sending the message.")
        print(f"Error: {e}")

# ── System Info ───────────────────────────────────────────────────────────────
def get_system_info(u):
    if any(w in u for w in ["what time", "current time", "time is it"]):
        speak(f"The time is {datetime.now().strftime('%I:%M %p')}.")
        return True
    if any(w in u for w in ["what date", "today's date", "what day"]):
        speak(f"Today is {datetime.now().strftime('%A, %B %d %Y')}.")
        return True
    if "time" in u and not any(w in u for w in ["remind", "timer", "schedule"]):
        speak(f"The time is {datetime.now().strftime('%I:%M %p')}.")
        return True
    if any(w in u for w in ["battery", "charge"]):
        b = psutil.sensors_battery()
        if b:
            speak(f"Battery is at {int(b.percent)} percent {'and charging' if b.power_plugged else 'and not charging'}.")
        return True
    if any(w in u for w in ["cpu", "processor"]):
        speak(f"CPU usage is {psutil.cpu_percent(interval=1)} percent.")
        return True
    if "ram" in u or ("memory" in u and "show" not in u):
        r = psutil.virtual_memory()
        speak(f"RAM usage is {round(r.used/1024**3,1)} GB out of {round(r.total/1024**3,1)} GB.")
        return True
    return False

# ── Volume ────────────────────────────────────────────────────────────────────
def get_volume_interface():
    from pycaw.pycaw import AudioUtilities
    return AudioUtilities.GetSpeakers().EndpointVolume

def handle_volume(u):
    if not any(w in u for w in ["volume", "louder", "quieter", "mute", "unmute"]):
        return False
    try:
        vol = get_volume_interface()
        current = round(vol.GetMasterVolumeLevelScalar() * 100)
        numbers = re.findall(r'\d+', u)
        amount = int(numbers[0]) if numbers else 10
        if any(w in u for w in ["max", "maximum", "full"]):
            vol.SetMasterVolumeLevelScalar(1.0, None); speak("Volume set to maximum."); return True
        if "unmute" in u:
            vol.SetMute(0, None); speak("Unmuted."); return True
        if "mute" in u:
            vol.SetMute(1, None); speak("Muted."); return True
        if any(w in u for w in ["increase", "up", "louder", "raise"]):
            new = min(100, current + amount)
            vol.SetMasterVolumeLevelScalar(new / 100, None); speak(f"Volume increased to {new} percent."); return True
        if any(w in u for w in ["decrease", "down", "quieter", "lower", "reduce"]):
            new = max(0, current - amount)
            vol.SetMasterVolumeLevelScalar(new / 100, None); speak(f"Volume decreased to {new} percent."); return True
        if any(w in u for w in ["set volume to", "volume to"]):
            new = max(0, min(100, amount))
            vol.SetMasterVolumeLevelScalar(new / 100, None); speak(f"Volume set to {new} percent."); return True
        speak(f"Current volume is {current} percent."); return True
    except Exception as e:
        speak("Couldn't control volume."); print(f"Volume error: {e}"); return True

# ── Brightness ────────────────────────────────────────────────────────────────
def handle_brightness(u):
    if not any(w in u for w in ["brightness", "brighter", "dimmer", "dim"]):
        return False
    try:
        import screen_brightness_control as sbc
        current = sbc.get_brightness()[0]
        numbers = re.findall(r'\d+', u)
        amount = int(numbers[0]) if numbers else 20
        if any(w in u for w in ["max", "maximum", "full"]):
            sbc.set_brightness(100); speak("Brightness set to maximum."); return True
        if any(w in u for w in ["min", "minimum"]):
            sbc.set_brightness(10); speak("Brightness set to minimum."); return True
        if any(w in u for w in ["set brightness to", "brightness to"]):
            sbc.set_brightness(max(10, min(100, amount))); speak(f"Brightness set to {amount} percent."); return True
        if any(w in u for w in ["increase", "up", "brighter", "raise"]):
            new = min(100, current + amount); sbc.set_brightness(new); speak(f"Brightness increased to {new} percent."); return True
        if any(w in u for w in ["decrease", "down", "dimmer", "dim", "lower", "reduce"]):
            new = max(10, current - amount); sbc.set_brightness(new); speak(f"Brightness decreased to {new} percent."); return True
        speak(f"Current brightness is {current} percent."); return True
    except Exception as e:
        speak("Couldn't control brightness."); print(f"Brightness error: {e}"); return True

# ── Power ─────────────────────────────────────────────────────────────────────
def handle_power(u):
    if "shut down" in u or "shutdown" in u or "turn off" in u:
        speak("Shutting down in 10 seconds."); time.sleep(10); os.system("shutdown /s /t 0"); return True
    if "restart" in u or "reboot" in u:
        speak("Restarting in 10 seconds."); time.sleep(10); os.system("shutdown /r /t 0"); return True
    if "sleep" in u or "hibernate" in u:
        speak("Going to sleep."); time.sleep(2); os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0"); return True
    if "lock" in u:
        speak("Locking screen."); os.system("rundll32.exe user32.dll,LockWorkStation"); return True
    if "cancel" in u:
        os.system("shutdown /a"); speak("Shutdown cancelled."); return True
    return False

# ── AI Brain ──────────────────────────────────────────────────────────────────
def get_ai_response(user_input):
    personality = ZEN_CONFIG["personality"]
    memory_context = build_memory_context(memory)
    system_prompts = {
        "casual": f"You are Zen, a casual and friendly AI assistant. Be helpful, warm, and concise. Keep responses short.\nToday's date is {datetime.now().strftime('%B %d, %Y')}.\n\n{memory_context}",
        "professional": f"You are Zen, a professional AI assistant. Be precise and efficient.\nToday's date is {datetime.now().strftime('%B %d, %Y')}.\n\n{memory_context}"
    }
    conversation_history.append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model=ZEN_CONFIG["model"],
        messages=[{"role": "system", "content": system_prompts[personality]}, *conversation_history],
        max_tokens=300
    )
    reply = response.choices[0].message.content
    conversation_history.append({"role": "assistant", "content": reply})
    if len(conversation_history) > 20:
        conversation_history.pop(0); conversation_history.pop(0)
    threading.Thread(target=extract_and_save_facts, args=(memory, client, ZEN_CONFIG["model"], user_input, reply), daemon=True).start()
    return reply

# ── Dynamic Command Handler ───────────────────────────────────────────────────
def handle_dynamic_command(user_input):
    # Fix typos first
    try:
        correction_response = client.chat.completions.create(
            model=ZEN_CONFIG["model"],
            messages=[{"role": "user", "content": f"""Fix typos or speech recognition errors in this command for a Windows AI assistant.
Common abbreviations: ss=screenshot, vol=volume, bri=brightness.
Return ONLY the corrected command, nothing else.

Command: {user_input}

Corrected:"""
}],
            max_tokens=50
        )
        corrected = correction_response.choices[0].message.content.strip()
        if corrected and corrected != user_input:
            print(f"Corrected: '{user_input}' → '{corrected}'")
            user_input = corrected
    except:
        pass

    cache_key = user_input.lower().strip()
    intent = classify_intent(client, ZEN_CONFIG["model"], user_input)

    if intent == "conversation":
        speak(get_ai_response(user_input))
        return

    if intent == "internal":
        speak("I'm not sure how to handle that internally yet.")
        return

    # Check location only if not cached
    cached = get_from_cache(cache_key)
    if not cached:
        if needs_location_clarification(client, ZEN_CONFIG["model"], user_input):
            speak("Where do you want to save it? Say desktop, documents, downloads, or a specific path.")
            location = listen() if ZEN_CONFIG.get("mode") == "voice" else input("Location: ").strip()
            if location:
                user_input = f"{user_input} — save to {location}"
                cache_key = user_input.lower().strip()
                cached = get_from_cache(cache_key)

    if cached:
        speak("On it.")
    else:
        speak("Let me figure that out.")

    code = cached if cached else generate_code(client, ZEN_CONFIG["model"], user_input, get_system_schema(memory))

    if not code:
        speak("I couldn't figure out how to do that.")
        return

    level, reason = get_trust_level(code)

    if level == 5:
        speak("I can't do that, it's not safe.")
        return

    if level == 4:
        try:
            summary = client.chat.completions.create(
                model=ZEN_CONFIG["model"],
                messages=[{"role": "user", "content": f"One sentence: what exactly will this Python code do? Be specific about filenames.\nCode:\n{code}"}],
                max_tokens=50
            ).choices[0].message.content.strip()
        except:
            summary = "run a system operation"
        if not get_confirmation(f"Zen will: {summary}. Say yes to confirm."):
            speak("Cancelled."); return

    if level == 3:
        if not get_confirmation("This will modify files. Say yes to confirm."):
            speak("Cancelled."); return

    status, data = execute_code(code)
    if status == "success":
        if data:
            speak(data)
        else:
            speak("Done.")
        if not cached:
            save_to_cache(cache_key, code)
    else:
        speak("Something went wrong.")
        print(f"Error: {data}")

# ── Commands ──────────────────────────────────────────────────────────────────
def handle_commands(user_input):
    u = user_input.lower()

    # Personality
    if "switch to professional" in u:
        ZEN_CONFIG["personality"] = "professional"; speak("Switched to professional mode."); return True
    if "switch to casual" in u:
        ZEN_CONFIG["personality"] = "casual"; speak("Switched to casual mode!"); return True

    # Mode
    if any(p in u for p in ["switch to chat", "chat mode", "chat mod", "type mode"]):
        ZEN_CONFIG["mode"] = "chat"; speak("Chat mode on."); return True
    if any(p in u for p in ["switch to voice", "voice mode", "voice mod", "speak mode"]):
        ZEN_CONFIG["mode"] = "voice"; speak("Voice mode on."); return True

    # Voice gender
    if "male voice" in u:
        ZEN_CONFIG["voice"] = "male"; speak("Voice changed to male."); return True
    if "female voice" in u:
        ZEN_CONFIG["voice"] = "female"; speak("Voice changed to female."); return True

    # System info
    if get_system_info(u): return True

    # Volume / Brightness / Power
    if handle_volume(u): return True
    if handle_brightness(u): return True
    if any(w in u for w in ["shut down", "shutdown", "restart", "reboot", "sleep", "hibernate", "lock"]):
        if handle_power(u): return True

    # WhatsApp
    if "message to" in u:
        after = user_input[u.index("message to") + len("message to"):].strip()
        parts = after.split()
        contact = clean_contact(parts[0]) if parts else ""
        raw_message = " ".join(parts[1:]) if len(parts) > 1 else "Hey!"
        if contact:
            send_whatsapp_message(contact, raw_message)
        else:
            speak("Who do you want to message?")
        return True

    # Apps
    if u.startswith("open "):
        app_name = u.replace("open ", "").split(" and ")[0].strip()
        if launch_app(app_name):
            log_app(memory, app_name)
            speak(f"Opening {app_name}.")
        else:
            speak(f"I don't know how to open {app_name} yet.")
        return True

    if "reopen tabs" in u or "restore tabs" in u or "previous tabs" in u:
        pyautogui.hotkey('ctrl', 'shift', 't'); speak("Reopening closed tabs."); return True

    # Memory
    if u.startswith("remember "):
        save_note(memory, user_input[9:].strip()); speak("Got it, I'll remember that."); return True
    if "what do you know about me" in u or "what do you remember" in u:
        ctx = build_memory_context(memory)
        speak(ctx.replace("What you know about the user:\n", "Here's what I know about you. ") if ctx else "I don't know much yet.")
        return True
    if "show memory" in u or "show notes" in u:
        if memory["important_notes"]:
            print("\nNotes:\n" + "\n".join([f"- {n['note']} ({n['time']})" for n in memory["important_notes"]]) + "\n")
            speak(f"You have {len(memory['important_notes'])} saved notes. Check the terminal.")
        else:
            speak("No saved notes yet.")
        return True
    if "show contacts" in u:
        if memory["contacts"]:
            print("\nContacts:\n" + "\n".join([f"- {k}: {v}" for k, v in memory["contacts"].items()]) + "\n")
            speak(f"You have {len(memory['contacts'])} contacts. Check the terminal.")
        else:
            speak("No saved contacts yet.")
        return True
    if "delete note" in u or "remove note" in u:
        numbers = re.findall(r'\d+', u)
        if numbers:
            idx = int(numbers[0]) - 1
            if 0 <= idx < len(memory["important_notes"]):
                removed = memory["important_notes"].pop(idx)
                save_memory(memory)
                speak(f"Deleted note: {removed['note']}")
            else:
                speak("Note number not found.")
        else:
            speak("Which note number? Say show notes first.")
        return True
    if "delete contact" in u or "remove contact" in u:
        name = u.replace("delete contact", "").replace("remove contact", "").strip().split()[0] if u.replace("delete contact", "").strip() else ""
        if name and name in memory["contacts"]:
            del memory["contacts"][name]; save_memory(memory); speak(f"Removed {name} from contacts.")
        else:
            speak("Contact not found.")
        return True
    if "forget everything" in u or "clear memory" in u:
        from memory import DEFAULT_MEMORY
        import copy
        memory.update(copy.deepcopy(DEFAULT_MEMORY)); save_memory(memory); speak("Memory cleared."); return True

    # Reminders — order matters: show/delete BEFORE add
    if any(p in u for p in ["show archive", "archived reminders", "past reminders", "completed reminders"]):
        archived = [r for r in load_reminders() if r.get("archived")]
        if archived:
            print("\nArchived:\n" + "\n".join([f"{i+1}. {r['task']} — {r.get('fired_at', r['date'])}" for i, r in enumerate(archived)]) + "\n")
            speak(f"You have {len(archived)} archived reminders. Check terminal.")
        else:
            speak("No archived reminders yet.")
        return True
    if any(w in u for w in ["show reminders", "list reminders", "my reminders", "what are my reminders"]):
        result = list_reminders()
        print(f"\n{result}\n")
        speak(result if "\n" not in result else f"You have active reminders. Check the terminal.")
        return True
    if "delete reminder" in u or "cancel reminder" in u or "remove reminder" in u:
        numbers = re.findall(r'\d+', u)
        if numbers:
            success, msg = delete_reminder(int(numbers[0]) - 1); speak(msg)
        else:
            speak("Which reminder number? Say show reminders first.")
        return True
    if any(p in u for p in ["remind me", "set a reminder", "set reminder", "set alarm", "create reminder", "add reminder"]):
        success, msg = add_reminder(client, ZEN_CONFIG["model"], user_input); speak(msg); return True

    # Exit
    exit_phrases = ["goodbye", "bye zen", "bye bye", "see you later", "quit zen", "exit zen", "close zen"]
    if any(p in u for p in exit_phrases) or u.strip() in ["bye", "exit", "quit"]:
        speak("Goodbye!"); sys.exit(0)

    # Dynamic — fallback for everything else
    handle_dynamic_command(user_input)
    return True

# ── Startup ───────────────────────────────────────────────────────────────────
def select_startup_mode():
    print("=" * 50)
    print("        ZEN — Your AI Assistant")
    print("=" * 50)
    print("\nHow do you want to interact?")
    print("  [1] Voice mode (default)")
    print("  [2] Chat mode (type)\n")
    choice = input("Enter 1 or 2 (or press Enter for voice): ").strip()
    ZEN_CONFIG["mode"] = "chat" if choice == "2" else "voice"
    update_preference(memory, "mode", ZEN_CONFIG["mode"])
    print(f"\n{'Chat' if choice == '2' else 'Voice'} mode selected.")
    print("=" * 50 + "\n")

# ── Main Loop ─────────────────────────────────────────────────────────────────
def main():
    select_startup_mode()
    start_reminder_checker(speak)
    speak("Hey, I'm Zen. How can I help you?")
    while True:
        try:
            mode = ZEN_CONFIG.get("mode", "voice")
            print(f"[ Mode: {mode.upper()} | Personality: {ZEN_CONFIG['personality'].upper()} | Voice: {ZEN_CONFIG['voice'].upper()} ]")
            user_input = (listen() if input("[ Press ENTER to speak ]") is not None else None) if mode == "voice" else chat_input()
            if not user_input:
                continue
            handle_commands(user_input)
        except KeyboardInterrupt:
            speak("Goodbye!")
            break

if __name__ == "__main__":
    main()