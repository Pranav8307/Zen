import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from executor import get_trust_level  # noqa: E402


def level(code):
    return get_trust_level(code)[0]


# Code Zen should still treat as safe: normal assistant tasks.
@pytest.mark.parametrize("code", [
    "import os\nzen_output = str(os.listdir('.'))",
    "import webbrowser\nwebbrowser.open('https://example.com')\nzen_output = 'opened'",
    "import psutil\nzen_output = f'CPU {psutil.cpu_percent()}%'",
    "from ddgs import DDGS\nresults = DDGS().text('weather', max_results=5)\nzen_output = results[0]['body'][:200]",
    "import os\nos.makedirs('x', exist_ok=True)\nzen_output = 'made'",
    "with open('a.txt') as f:\n    zen_output = f.read()",
    "text = 'a-b'.replace('-', ' ')\nzen_output = text",
])
def test_normal_code_is_safe(code):
    assert level(code) == 1


@pytest.mark.parametrize("code,expected", [
    ("import shutil\nshutil.rmtree('x')", 4),
    ("import os\nos.remove('x')", 4),
    ("import shutil\nshutil.move('a', 'b')", 3),
    ("open('a.txt', 'w').write('x')", 3),
    ("from pathlib import Path\nPath('a').write_text('x')", 3),
    ("from pathlib import Path\nPath('a').unlink()", 4),
])
def test_risk_tiers(code, expected):
    assert level(code) == expected


# Bypasses that the text-pattern layer alone classified as "Safe".
@pytest.mark.parametrize("code", [
    "import subprocess as sp\nsp.run(['calc'])",
    "from subprocess import run as r\nr(['calc'])",
    "import os\nos.popen('whoami')",
    "import os\nos.system('calc')",
    "import os, ctypes\nzen_output = 'x'",
    "import os\nexec('print(1)')",
    "import os\ngetattr(os, 'system')('calc')",
    "from os import system as s\ns('calc')",
    "import shutil as sh\nsh.rmtree('x')",
])
def test_known_bypasses_are_no_longer_safe(code):
    assert level(code) >= 4


@pytest.mark.parametrize("code", [
    "import ctypes",
    "import socket",
    "eval('1+1')",
    "def broken(:",
])
def test_blocked(code):
    assert level(code) == 5
