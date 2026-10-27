# Zen setup (Windows)

## 1. Install packages

```
pip install -r requirements.txt
```

If `pyaudio` fails:

```
pip install pipwin
pipwin install pyaudio
```

## 2. Add your API key

```
copy config.example.py config.py
```

Open `config.py` and replace `YOUR_GROQ_API_KEY_HERE` with your Groq key. `config.py` is gitignored.

## 3. Run

```
python main.py
```

## 4. Tests (optional)

```
pip install pytest
pytest tests
```

The tests cover the code-safety classifier only; they do not need a microphone or an API key.

## Using Zen

- Choose voice or chat mode at startup. In voice mode, press ENTER to speak.
- "switch to professional" / "switch to casual" changes personality.
- "switch to male voice" / "switch to female voice" changes the voice.
- "bye Zen" or "exit" quits.

## Files

```
main.py            app loop, speech in/out, command routing, confirmation
executor.py        code generation, safety classification, isolated execution, code cache
validator.py       AST-based safety analysis used by executor.py
memory.py          saved facts and preferences (zen_memory.json)
reminders.py       reminders (zen_reminders.json)
config.example.py  template for config.py
tests/             classifier tests
```
