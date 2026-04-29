import re
import os
import sys
import json
import traceback
import multiprocessing
from datetime import datetime

BLACKLIST = [
    "diskpart",
    "del /f /s", "rd /s /q", "eval(", "__import__(",
]

LEVEL_4_PATTERNS = [
    "os.remove", "os.unlink", "subprocess.Popen", "send2trash",
    "shutil.rmtree", "rmtree",  "subprocess.run", "subprocess.call", "os.system",
]

LEVEL_3_PATTERNS = [
    "os.rename", "shutil.move", "shutil.copy",
    r"open\(.*['\"]w['\"]", "os.replace",
]

ALLOWED_IMPORTS = [
    "import os", "import sys", "import re", "import time",
    "import datetime", "import subprocess", "import webbrowser",
    "import pyautogui", "import psutil", "import shutil",
    "import glob", "import pathlib", "import json",
    "import send2trash", "from send2trash",
    "from datetime", "from pathlib", "from PIL",
    "import PIL", "import mss", "import screen_brightness_control",
    "import platform",
    "from ddgs", "import ddgs",
    "import requests", "import zipfile",
]

def get_trust_level(code):
    code_lower = code.lower()
    for pattern in BLACKLIST:
        if pattern.lower() in code_lower:
            return 5, f"Blocked: dangerous operation '{pattern}'"
    import_lines = [l.strip() for l in code.split('\n')
                    if l.strip().startswith('import') or l.strip().startswith('from')]
    for line in import_lines:
        if not any(line.startswith(a) for a in ALLOWED_IMPORTS):
            return 5, f"Blocked: disallowed import '{line}'"
    for pattern in LEVEL_4_PATTERNS:
        if re.search(pattern, code):
            return 4, "This will run a system command or delete something."
    for pattern in LEVEL_3_PATTERNS:
        if re.search(pattern, code):
            return 3, "This will modify or move existing files."
    return 1, "Safe"

def _run_code(code, result_queue):
    try:
        exec_globals = {"__builtins__": __builtins__, "os": os, "sys": sys}
        exec(code, exec_globals)
        zen_output = exec_globals.get("zen_output", None)
        result_queue.put(("success", zen_output))
    except Exception as e:
        result_queue.put(("error", traceback.format_exc()))

def classify_intent(client, model, user_input):
    """Determine if command is a Zen internal command or a system task"""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"""Classify this command into one of these categories:
1. "system" - needs Python code to do something on the computer OR needs real-time info like weather, news, prices, sports scores
2. "internal" - about Zen's own data (reminders, memory, contacts, settings, archives)
3. "conversation" - general chat, opinions, explanations, things that don't need current data

Return ONLY one word: system, internal, or conversation

Command: {user_input}

Category:"""}],
            max_tokens=10
        )
        result = response.choices[0].message.content.strip().lower()
        if result not in ["system", "internal", "conversation"]:
            return "system"
        return result
    except:
        return "system"

def needs_location_clarification(client, model, user_input):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"""Does this command create or save a file, AND the file type has NO obvious default save location?

Default locations already known:
- screenshots/ss -> Pictures/Screenshots
- documents/text files -> Documents  
- downloads -> Downloads
- music -> Music
- videos -> Videos
- desktop files -> Desktop

Answer NO if the command mentions any of these file types or locations.
Answer NO if the command is about deleting, opening, or running something.
Answer YES only if the command saves something with truly unknown location.

Command: {user_input}

Answer yes or no:"""}],
            max_tokens=5
        )
        result = response.choices[0].message.content.strip().lower()
        return "yes" in result
    except:
        return False

def execute_code(code, timeout=15):
    result_queue = multiprocessing.Queue()
    process = multiprocessing.Process(target=_run_code, args=(code, result_queue))
    process.start()
    process.join(timeout=timeout)
    if process.is_alive():
        process.terminate()
        process.join()
        return "error", "Code timed out."
    if not result_queue.empty():
        return result_queue.get()
    return "error", "No result returned."

def generate_code(client, model, task, system_schema):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"""You are a Python code generator for a Windows AI assistant.
Write Python code to accomplish: {task}

System context:
{system_schema}

Rules:
- Raw Python code only, no markdown, no backticks, no explanations
- No input() calls
- Use only: os, sys, subprocess, webbrowser, pyautogui, psutil, shutil, glob, pathlib, PIL, mss, time, datetime, re, json
- Self-contained, runs completely on its own
- Never use if __name__ == "__main__" blocks
- Never define a main() function — just write the code directly
- You MUST always set zen_output = "..." at the very end with a summary of results
- This is mandatory, never skip it

Python code:"""}],
            max_tokens=500
        )
        code = response.choices[0].message.content.strip()
        return code.replace("```python", "").replace("```", "").strip()
    except:
        return None

CACHE_FILE = "zen_code_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_to_cache(task_key, code):
    cache = load_cache()
    cache[task_key.lower()] = {"code": code, "saved": datetime.now().strftime("%Y-%m-%d %H:%M")}
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def get_from_cache(task_key):
    return load_cache().get(task_key.lower(), {}).get("code")

def get_system_schema(memory=None):
    import platform
    username = os.getenv('USERNAME')
    onedrive_desktop = f"C:/Users/{username}/OneDrive/Desktop"
    regular_desktop = f"C:/Users/{username}/Desktop"
    desktop = onedrive_desktop if os.path.exists(onedrive_desktop) else regular_desktop

    location = "Ludhiana, India"
    if memory and memory.get("user", {}).get("location"):
        location = memory["user"]["location"]

    try:
        import pyautogui
        screen = pyautogui.size()
    except:
        screen = "unknown"

    return f"""OS: {platform.system()} {platform.release()}
Python: {sys.version.split()[0]}
Screen: {screen}
Username: {username}
User location: {location}
Default locations:
  Desktop: {desktop}
  Documents: C:/Users/{username}/Documents
  Downloads: C:/Users/{username}/Downloads
  Pictures: C:/Users/{username}/OneDrive/Pictures
  Screenshots: C:/Users/{username}/OneDrive/Pictures/Screenshots
  Music: C:/Users/{username}/Music
  Videos: C:/Users/{username}/Videos
Libraries: os, sys, subprocess, webbrowser, pyautogui, psutil, ddgs, shutil, glob, pathlib, PIL, mss, time, datetime, re, json, send2trash, zipfile, requests
Rules:
  - Never use os.path.join starting with 'C:' — always use os.path.expanduser('~') for user paths
  - Always use os.path.normpath() on final paths
  - Never use if __name__ == "__main__" blocks
  - Never define a main() function, write code directly
  - Always use os.path.join() for paths, never mix / and \\ separators
  - For deleting always use send2trash.send2trash(os.path.normpath(path))
  - For screenshots save to Screenshots folder by default
  - For web searches, after getting results summarize using this pattern:
    summary = results[0]['body'][:200] if results else "No results found"
    zen_output = summary
  - Never set zen_output to the full raw result, always slice to 200 chars max and make it conversational
  - For web searches: from ddgs import DDGS; results = DDGS().text("query", max_results=5)
  - For weather: search "weather in {{user location}} today"
  - For any real-time info use DDGS search first
  - Never use print() for results, only set zen_output
  - For file search use glob.glob() with recursive=True
  - For zipping use zipfile.ZipFile()
  - After getting search results, store the summary in a variable called 'zen_output' so Zen can speak it
  - Example: zen_output = f"Weather in {{location}}: {{results[0]['body']}}"
  - Always set zen_output to a human readable summary string
  - Always set zen_output at the end of your code with a human readable summary of what happened or what was found
  - For search results: summarize into 1-2 clean conversational sentences, never raw text
  - For file operations: zen_output = "Created folder ZenTest on desktop" or "Found 3 PDF files in Documents"
  - For system info: zen_output = "Battery is at 80% and charging"
  - For weather: zen_output = "Tomorrow in Chandigarh will be partly cloudy, high 25°C"
  - For anything: zen_output must always be set, always conversational, always short and human readable"""