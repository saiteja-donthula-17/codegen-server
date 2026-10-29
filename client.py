# Served by /run and executed on the user's machine:
#   curl -fsSL ".../run?token=..." | GEMINI_API_KEY=your-key GEMINI_MODEL=gemini-2.5-flash python3
import os
import sys
import json
import getpass
import subprocess
import urllib.request
from pathlib import Path

URL = '__URL__'
FILES = __FILES__

# find tests.py and the data folder whether they sit here or one level up
TESTS = next((p for p in ['pytest/tests.py', '../pytest/tests.py', 'tests.py', '../tests.py'] if Path(p).exists()),
             'pytest/tests.py')
DATA = [p for d in ['data', '../data'] for p in sorted(Path(d).rglob('*'))
        if p.is_file() and not p.name.startswith('.')][:40]
if not Path(TESTS).exists():
    sys.exit('tests.py not found - run this from the project folder (next to pytest/ or one level below it)')

# the key stays on this machine until it is sent as a header, never in the URL
KEY = os.getenv('GEMINI_API_KEY')
if not KEY:
    try:
        KEY = getpass.getpass('Gemini API key: ').strip()  # getpass reads the terminal, not the pipe
    except EOFError:  # no terminal to ask on
        pass
if not KEY:
    sys.exit('no Gemini API key - get one at https://aistudio.google.com/apikey')
MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
print('model:', MODEL)


def read(path, limit=None):
    """Text of a file, or None if it is missing or binary."""
    try:
        return Path(path).read_text(encoding='utf-8')[:limit]
    except (OSError, UnicodeDecodeError):
        return None


def run_tests():
    r = subprocess.run([sys.executable, '-m', 'pytest', TESTS, '-q', '--tb=short'],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    out = r.stdout + r.stderr
    print('tests:', (out.strip().splitlines() or ['no output'])[-1])
    return r.returncode == 0, out


send = {}
for n in [TESTS] + FILES:
    send[n] = read(n)
for p in DATA:
    send[str(p)] = read(p, 3000)  # data is only a sample so Gemini sees paths and fields
send = {n: text for n, text in send.items() if text is not None}
print('tests file:', TESTS, '| data files:', sum(str(p) in send for p in DATA))

for round in range(3):
    ok, errors = run_tests()
    if ok:
        break
    for n in FILES:
        if read(n) is not None:
            send[n] = read(n)
    send['errors'] = errors[-8000:]
    headers = {'Content-Type': 'application/json', 'X-Api-Key': KEY, 'X-Model': MODEL}
    req = urllib.request.Request(URL, data=json.dumps(send).encode(), headers=headers)
    try:
        result = json.load(urllib.request.urlopen(req, timeout=600))
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read())['detail']
        except (ValueError, KeyError, TypeError):  # e.g. Render's HTML page while the server wakes up
            detail = 'run the command again in a minute'
        print('server error', e.code, '-', detail)
        break
    except (urllib.error.URLError, TimeoutError) as e:  # no network, DNS, or the server took too long
        print('could not reach server -', e, '- run the command again in a minute')
        break
    for name, code in result.items():
        Path(name).write_text(code, encoding='utf-8')
        print('wrote', name)
else:
    run_tests()
