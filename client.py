# Served by /run and executed on the user's machine: curl -fsSL ".../run?token=..." | python3
import sys
import json
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
    req = urllib.request.Request(URL, data=json.dumps(send).encode(), headers={'Content-Type': 'application/json'})
    try:
        result = json.load(urllib.request.urlopen(req, timeout=600))
    except urllib.error.HTTPError as e:
        print('server error', e.code, '- run the command again in a minute')
        break
    for name, code in result.items():
        Path(name).write_text(code)
        print('wrote', name)
else:
    run_tests()
