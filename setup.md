# Zen Setup Guide (Windows)

## Step 1 — Install Python packages
Open terminal in this folder and run:
```
pip install -r requirements.txt
```

If pyaudio fails, run this first:
```
pip install pipwin
pipwin install pyaudio
```

## Step 2 — Add your API key
Open config.py and replace:
```
"groq_api_key": "YOUR_GROQ_API_KEY_HERE"
```
With your actual Groq API key.

## Step 3 — Run Zen
```
python main.py
```

## How to Use
- Press ENTER to speak
- Say anything — Zen will respond
- Say "switch to professional" — changes personality
- Say "switch to casual" — changes back
- Say "switch to male voice" or "switch to female voice"
- Say "bye Zen" or "exit" to quit

## Folder Structure
```
zen/
├── main.py          # Core app
├── config.py        # Your settings & API key
├── requirements.txt # Dependencies
└── SETUP.md         # This file
```