"""AST-based safety analysis for LLM-generated Python code.

This complements the string/pattern checks in executor.py. Pattern matching on
text is easy to bypass (aliased imports, `os.popen`, `import os, ctypes`,
`getattr`, `exec`). Here the code is parsed into a syntax tree, so we inspect
what is actually imported and called, after resolving import aliases.

Levels (same meaning as executor.get_trust_level):
    1 safe | 3 modifies files | 4 runs system commands / deletes | 5 blocked

This is still NOT a sandbox: it reduces risk, but code that passes can still run
with the user's full permissions. Real isolation needs a container or OS sandbox.
"""
import ast

# Root modules the generated code may import (mirrors executor.ALLOWED_IMPORTS).
ALLOWED_MODULES = {
    "os", "sys", "re", "time", "datetime", "subprocess", "webbrowser",
    "pyautogui", "psutil", "shutil", "glob", "pathlib", "json", "send2trash",
    "PIL", "mss", "screen_brightness_control", "platform", "ddgs",
    "requests", "zipfile",
}

BLOCKED_CALLS = {"eval", "exec", "compile", "__import__"}

# getattr/setattr allow dynamic access to anything (e.g. getattr(os, "system")),
# so they require confirmation rather than being allowed silently.
CONFIRM_CALLS = {"getattr", "setattr", "delattr", "globals", "locals", "vars"}

LEVEL_4_DOTTED_PREFIXES = ("subprocess.", "send2trash.")
LEVEL_4_DOTTED = {
    "os.remove", "os.unlink", "os.rmdir", "os.removedirs", "os.system", "os.popen",
    "os.kill", "os.killpg", "shutil.rmtree",
}
LEVEL_4_OS_PREFIXES = ("os.exec", "os.spawn")
LEVEL_3_DOTTED = {
    "os.rename", "os.replace", "shutil.move", "shutil.copy", "shutil.copy2",
    "shutil.copyfile", "shutil.copytree",
}
# Method names that are risky regardless of the object (e.g. Path(...).unlink()).
LEVEL_4_METHODS = {"unlink", "rmdir", "kill", "terminate"}
LEVEL_3_METHODS = {"write_text", "write_bytes", "rename"}

WRITE_MODES = ("w", "a", "x", "+")


def _dotted(node, aliases):
    """Resolve a call target to a dotted name, following import aliases."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(aliases.get(node.id, node.id))
        return ".".join(reversed(parts))
    return None  # base is a call/subscript, so only the method name is known


def _write_mode(call):
    mode = None
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        mode = call.args[1].value
    for kw in call.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and any(m in mode for m in WRITE_MODES)


def analyze(code):
    """Return (level, reason) for the given source code."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return 5, f"Blocked: code does not parse ({e.msg})"

    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root not in ALLOWED_MODULES:
                    return 5, f"Blocked: disallowed import '{a.name}'"
                aliases[a.asname or root] = a.name if a.asname else root
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level or root not in ALLOWED_MODULES:
                return 5, f"Blocked: disallowed import 'from {node.module or '.'}'"
            for a in node.names:
                aliases[a.asname or a.name] = f"{node.module}.{a.name}"

    level, reason = 1, "Safe"

    def bump(new_level, new_reason):
        nonlocal level, reason
        if new_level > level:
            level, reason = new_level, new_reason

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func, aliases)
        method = node.func.attr if isinstance(node.func, ast.Attribute) else None
        simple = node.func.id if isinstance(node.func, ast.Name) else None

        if simple in BLOCKED_CALLS or name in BLOCKED_CALLS:
            return 5, f"Blocked: call to '{simple or name}'"
        if simple in CONFIRM_CALLS:
            bump(4, f"Dynamic access via '{simple}' needs confirmation.")
        if name:
            if (name in LEVEL_4_DOTTED or name.startswith(LEVEL_4_DOTTED_PREFIXES)
                    or name.startswith(LEVEL_4_OS_PREFIXES)):
                bump(4, "This will run a system command or delete something.")
            elif name in LEVEL_3_DOTTED:
                bump(3, "This will modify or move existing files.")
        if method in LEVEL_4_METHODS:
            bump(4, "This will delete or terminate something.")
        elif method in LEVEL_3_METHODS:
            bump(3, "This will modify or move existing files.")
        if (simple == "open" or name == "io.open") and _write_mode(node):
            bump(3, "This will modify or move existing files.")
    return level, reason
