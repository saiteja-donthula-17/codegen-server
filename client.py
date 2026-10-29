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
DATA = [str(p) for d in ['data', '../data'] for p in sorted(Path(d).glob('*.*')) if p.suffix in ('.csv', '.json')]
print('tests file:', TESTS, '| data files:', len(DATA))


def run_tests():
    r = subprocess.run([sys.executable, '-m', 'pytest', TESTS, '-q', '--tb=short'],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    out = r.stdout + r.stderr
    print('tests:', (out.strip().splitlines() or ['no output'])[-1])
    return r.returncode == 0, out


for round in range(3):
    ok, errors = run_tests()
    if ok:
        break
    send = {n: Path(n).read_text() for n in [TESTS] + FILES + DATA if Path(n).exists()}
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
