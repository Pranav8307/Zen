import json
import os
import threading
import time
from datetime import datetime, timedelta
import re
import winsound

REMINDERS_FILE = "zen_reminders.json"

# ── Load/Save ─────────────────────────────────────────────────────────────────
def load_reminders():
    if os.path.exists(REMINDERS_FILE):
        try:
            with open(REMINDERS_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_reminders(reminders):
    with open(REMINDERS_FILE, "w") as f:
        json.dump(reminders, f, indent=2)

# ── Parse reminder from natural language using AI ─────────────────────────────
def parse_reminder(client, model, user_input):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": f"""Extract reminder details from this text. Current time: {now}

Return ONLY a valid JSON object with these fields:
{{
  "task": "what to remind about",
  "time": "HH:MM",
  "date": "YYYY-MM-DD",
  "recur": "none/daily/weekly/monthly",
  "contact": "contact name if tied to a person or null",
  "type": "reminder/timer/alarm"
}}

For timers like "remind me in 10 minutes", calculate the exact time.
For "in X seconds", calculate exact time including seconds.
For "in X minutes", add X minutes to current time.
For recurring, set next occurrence.
If no date mentioned, assume today or tomorrow if time has passed.

Text: {user_input}

JSON:"""}],
            max_tokens=200
        )
        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        return json.loads(raw)
    except Exception as e:
        print(f"Reminder parse error: {e}")
        return None

# ── Add reminder ──────────────────────────────────────────────────────────────
def add_reminder(client, model, user_input):
    parsed = parse_reminder(client, model, user_input)
    if not parsed:
        return False, "Couldn't understand the reminder."

    reminder = {
        "id": int(time.time()),
        "task": parsed.get("task", "reminder"),
        "time": parsed.get("time", "09:00"),
        "date": parsed.get("date", datetime.now().strftime("%Y-%m-%d")),
        "recur": parsed.get("recur", "none"),
        "contact": parsed.get("contact"),
        "type": parsed.get("type", "reminder"),
        "done": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    reminders = load_reminders()
    reminders.append(reminder)
    save_reminders(reminders)

    # Build confirmation message
    recur_text = f" (repeats {reminder['recur']})" if reminder['recur'] != "none" else ""
    contact_text = f" for {reminder['contact']}" if reminder['contact'] else ""
    time_text = f"{reminder['date']} at {reminder['time']}"

    return True, f"Reminder set{contact_text}: {reminder['task']} on {time_text}{recur_text}."

# ── List reminders ────────────────────────────────────────────────────────────
def list_reminders():
    reminders = [r for r in load_reminders() if not r["done"] and not r.get("archived")]
    if not reminders:
        return "No active reminders."
    lines = []
    for i, r in enumerate(reminders, 1):
        contact = f" (for {r['contact']})" if r.get('contact') else ""
        recur = f" [{r['recur']}]" if r.get('recur') != 'none' else ""
        lines.append(f"{i}. {r['task']}{contact} — {r['date']} {r['time']}{recur}")
    return "\n".join(lines)

# ── Delete reminder ───────────────────────────────────────────────────────────
def delete_reminder(index):
    reminders = load_reminders()
    active = [r for r in reminders if not r["done"]]
    if 0 <= index < len(active):
        active[index]["done"] = True
        # Update in full list
        for r in reminders:
            if r["id"] == active[index]["id"]:
                r["done"] = True
        save_reminders(reminders)
        return True, f"Deleted reminder: {active[index]['task']}"
    return False, "Reminder not found."

# ── Windows popup notification ────────────────────────────────────────────────
def show_popup(title, message):
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="Zen",
            timeout=10
        )
    except:
        # Fallback to Windows toast via PowerShell
        try:
            import subprocess
            ps_script = f'''
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textNodes = $template.GetElementsByTagName("text")
$textNodes[0].AppendChild($template.CreateTextNode("{title}")) | Out-Null
$textNodes[1].AppendChild($template.CreateTextNode("{message}")) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Zen").Show($toast)
'''
            subprocess.run(["powershell", "-Command", ps_script], capture_output=True)
        except:
            pass

# ── Reminder checker — runs in background thread ──────────────────────────────
def start_reminder_checker(speak_func):
    def check_loop():
        while True:
            try:
                now = datetime.now()
                reminders = load_reminders()
                changed = False

                for r in reminders:
                    if r["done"]:
                        continue
                    try:
                        reminder_dt = datetime.strptime(f"{r['date']} {r['time']}", "%Y-%m-%d %H:%M")
                    except:
                        continue

                    # Trigger if within 1 minute window
                    diff = (now - reminder_dt).total_seconds()
                    if 0 <= diff <= 60:
                        contact_text = f" for {r['contact']}" if r.get('contact') else ""
                        msg = f"Reminder{contact_text}: {r['task']}"
                        
                        # Play a beep first so user knows it's a reminder
                        import winsound
                        winsound.Beep(1000, 500)  # 1000Hz for 0.5 seconds
                        
                        speak_func(msg)
                        show_popup("Zen Reminder", msg)

                        if r["recur"] == "none":
                            r["done"] = True
                            r["archived"] = True
                            r["fired_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        elif r["recur"] == "daily":
                            next_dt = reminder_dt + timedelta(days=1)
                            r["date"] = next_dt.strftime("%Y-%m-%d")
                        elif r["recur"] == "weekly":
                            next_dt = reminder_dt + timedelta(weeks=1)
                            r["date"] = next_dt.strftime("%Y-%m-%d")
                        elif r["recur"] == "monthly":
                            month = reminder_dt.month % 12 + 1
                            year = reminder_dt.year + (1 if month == 1 else 0)
                            r["date"] = reminder_dt.replace(year=year, month=month).strftime("%Y-%m-%d")

                        changed = True

                if changed:
                    save_reminders(reminders)

            except Exception as e:
                print(f"Reminder checker error: {e}")

            time.sleep(30)  # Check every 30 seconds

    thread = threading.Thread(target=check_loop, daemon=True)
    thread.start()
    return thread