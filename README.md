# Zen

A voice and chat assistant for Windows that can do things on your computer. You say or type a request in plain English; an LLM (Groq) writes a short Python script for it; Zen checks the script for safety, asks you to confirm if it is risky, runs it in a separate process with a timeout, and reads back the result.

I built it to see what it takes to let an LLM run code on a real machine without trusting it blindly. Most of the project is the safety and control layer, not the LLM call.

**Platform:** Windows only (paths, `pycaw`, `winsound`-style features). **Not a sandbox**: see "Security".

---

## How it works

```
speech / text  ->  fix typos  ->  classify intent (system / internal / conversation)
                                             |
                        conversation  ->  chat reply
                        system        ->  cached code? use it : LLM generates Python
                                             |
                                    safety check (patterns + AST)
                                             |
              level 1 safe -> run | level 3 modifies files -> confirm | level 4 system/delete -> confirm
              level 5 blocked -> refuse
                                             |
              run in a separate process, 15 s timeout  ->  zen_output spoken back
```

### Safety layers

1. **Import allowlist:** 26 allowed import prefixes (`os`, `shutil`, `pathlib`, `requests`, ...). Anything else is blocked.
2. **Pattern rules:** 19 text patterns: 5 hard-blocked (`eval(`, `__import__(`, `diskpart`, ...), 9 that run system commands or delete (level 4), and 5 that modify files (level 3).
3. **AST analysis (`validator.py`):** parses the generated code and checks what is actually imported and called after resolving aliases (`import subprocess as sp`, `from os import system as s`). It blocks `eval`/`exec`/`compile`, asks for confirmation on `getattr` and on any `subprocess`, `os.system`, `os.popen`, `unlink`, `rmtree`, and treats file writes (`open(..., "w")`, `write_text`) as level 3. The higher level from layers 2 and 3 wins.
4. **Confirmation:** levels 3 and 4 need a spoken or typed "yes" (whole-word match).
5. **Process isolation:** code runs in a `multiprocessing` child process. A 15-second timeout terminates hung or runaway scripts, and a crash cannot take down the main app.

### Code cache

Generated code is cached per command text in `zen_code_cache.json` after it runs successfully. A repeated command skips the code-generation call. Cached code goes through the same safety check before it runs. Typo correction and intent classification still call the LLM each time.

---

## Setup

See `setup.md`. In short: `pip install -r requirements.txt`, copy `config.example.py` to `config.py` and add your Groq API key, then `python main.py`.

---

## Security

Zen reduces risk; it does not remove it.

- The child process runs with **your user's permissions**. There is no container, no file-system restriction, no network restriction.
- Pattern and AST checks are heuristics. They catch the mistakes and attacks I tested for (aliased imports, `os.popen`, `import os, ctypes`, `exec`, `getattr(os, "system")`), but a determined attacker may find another way.
- The LLM can also write code that is "safe" yet wrong (for example, deleting the wrong file in an allowed way). That is why risky actions ask for confirmation.
- Do not point Zen at untrusted input.

For anything beyond personal use, run generated code in a container or OS sandbox (restricted file system, no network, resource limits).

---

## Tests

```
pip install pytest
pytest tests
```

`tests/test_validator.py` checks that ordinary requests stay safe, that risky operations land in the right tier, that known bypasses are no longer classified as safe, and that disallowed imports are blocked.

---

## Known limitations

- Windows only; some paths (OneDrive folders) are hardcoded in the system prompt.
- Speech recognition needs a microphone and internet access.
- The classifier is a rule set; there is no whitelist of exact allowed operations.
- No end-to-end tests of the voice loop or the LLM calls.
- Cache is keyed by the exact command text, so rephrased commands miss it.

## Next steps

Run generated code in a container with no network; replace substring checks with a policy engine; add a dry-run preview and undo for file operations; add tests that mock the LLM.
