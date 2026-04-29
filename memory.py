import json
import os
from datetime import datetime

MEMORY_FILE = "zen_memory.json"

# ── Default memory structure ──────────────────────────────────────────────────
DEFAULT_MEMORY = {
    "user": {
        "name": None,
        "age": None,
        "location": None,
        "occupation": None,
        "other": {}
    },
    "preferences": {
        "voice": "female",
        "mode": "voice",
        "personality": "casual",
        "other": {}
    },
    "contacts": {},        # name -> phone/relation
    "frequent_apps": {},   # app_name -> open_count
    "important_notes": [], # list of important things discussed
    "past_tasks": [],      # last 20 tasks performed
    "last_updated": None
}

# ── Load memory ───────────────────────────────────────────────────────────────
def load_memory():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                data = json.load(f)
                # Merge with defaults to handle missing keys
                for key in DEFAULT_MEMORY:
                    if key not in data:
                        data[key] = DEFAULT_MEMORY[key]
                return data
        except:
            return DEFAULT_MEMORY.copy()
    return DEFAULT_MEMORY.copy()

# ── Save memory ───────────────────────────────────────────────────────────────
def save_memory(memory):
    memory["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)

# ── Update preference ─────────────────────────────────────────────────────────
def update_preference(memory, key, value):
    memory["preferences"][key] = value
    save_memory(memory)

# ── Log task ──────────────────────────────────────────────────────────────────
def log_task(memory, task):
    memory["past_tasks"].append({
        "task": task,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    # Keep only last 20
    if len(memory["past_tasks"]) > 20:
        memory["past_tasks"] = memory["past_tasks"][-20:]
    save_memory(memory)

# ── Log app usage ─────────────────────────────────────────────────────────────
def log_app(memory, app_name):
    memory["frequent_apps"][app_name] = memory["frequent_apps"].get(app_name, 0) + 1
    save_memory(memory)

# ── Save important note ───────────────────────────────────────────────────────
def save_note(memory, note):
    memory["important_notes"].append({
        "note": note,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    save_memory(memory)

# ── Extract and save facts from conversation using AI ────────────────────────
def extract_and_save_facts(memory, client, model, user_input, ai_response):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": f"""You are a fact extractor. Extract ANY important personal facts about the user from this conversation worth remembering long-term.
You MUST respond with ONLY a valid JSON object. No explanation, no markdown, no backticks.
If nothing found, respond with exactly: {{}}

Use these fields if they match, otherwise create your own descriptive key:
- user_name, user_age, user_location, user_occupation, user_education
- contact_name + contact_info (for people mentioned)
- important_note (for anything else important)
- Any other key-value pair that seems worth remembering

Examples of things worth saving:
- "I have a dog named Max" -> {{"pet": "dog named Max"}}
- "I'm allergic to peanuts" -> {{"allergy": "peanuts"}}  
- "My project deadline is Friday" -> {{"important_note": "project deadline Friday"}}
- "I prefer dark mode" -> {{"preference": "dark mode"}}

User said: {user_input}
Zen replied: {ai_response}

JSON:"""
            }],
            max_tokens=200
        )
        raw = response.choices[0].message.content.strip()

        # Clean any accidental markdown
        raw = raw.replace("```json", "").replace("```", "").strip()

        if not raw or raw == "{}":
            return

        facts = json.loads(raw)

        # Save known fields
        if facts.get("user_name"): memory["user"]["name"] = facts["user_name"]
        if facts.get("user_age"): memory["user"]["age"] = facts["user_age"]
        if facts.get("user_location"): memory["user"]["location"] = facts["user_location"]
        if facts.get("user_occupation"): memory["user"]["occupation"] = facts["user_occupation"]
        if facts.get("contact_name") and facts.get("contact_info"):
            memory["contacts"][facts["contact_name"]] = facts["contact_info"]
        if facts.get("important_note"):
            save_note(memory, facts["important_note"])

        # Save ANY other unknown fields into user.other
        known_keys = {"user_name", "user_age", "user_location", "user_occupation", "contact_name", "contact_info", "important_note"}
        for key, value in facts.items():
            if key not in known_keys and value:
                memory["user"]["other"][key] = value

        save_memory(memory)

    except json.JSONDecodeError as e:
        print(f"Memory JSON error: {e}")
    except Exception as e:
        print(f"Memory extraction error: {e}")

# ── Build memory context for AI prompt ───────────────────────────────────────
def build_memory_context(memory):
    parts = []

    if memory["user"]["name"]:
        parts.append(f"User's name is {memory['user']['name']}.")
    if memory["user"]["age"]:
        parts.append(f"User is {memory['user']['age']} years old.")
    if memory["user"]["location"]:
        parts.append(f"User is from {memory['user']['location']}.")
    if memory["user"]["occupation"]:
        parts.append(f"User works as {memory['user']['occupation']}.")
    if memory["user"]["other"]:
        for k, v in memory["user"]["other"].items():
            parts.append(f"{k}: {v}.")
    if memory["contacts"]:
        contacts_str = ", ".join([f"{k} ({v})" for k, v in memory["contacts"].items()])
        parts.append(f"Known contacts: {contacts_str}.")
    if memory["important_notes"]:
        recent_notes = memory["important_notes"][-3:]
        for n in recent_notes:
            parts.append(f"Important note: {n['note']}.")
    if memory["frequent_apps"]:
        top_apps = sorted(memory["frequent_apps"].items(), key=lambda x: x[1], reverse=True)[:3]
        apps_str = ", ".join([a[0] for a in top_apps])
        parts.append(f"User frequently uses: {apps_str}.")

    if not parts:
        return ""

    return "What you know about the user:\n" + "\n".join(parts)