# Served by /run and executed on the user's machine: curl -fsSL ".../run?token=..." | python3
import sys
import json
import subprocess
import urllib.request
from pathlib import Path

URL = '__URL__'
NAMES = __NAMES__


def run_tests():
    r = subprocess.run([sys.executable, '-m', 'pytest', 'pytest/tests.py', '-q', '--tb=short'],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    out = r.stdout + r.stderr
    print('tests:', (out.strip().splitlines() or ['no output'])[-1])
    return r.returncode == 0, out


for round in range(3):
    ok, errors = run_tests()
    if ok:
        break
    send = {n: Path(n).read_text() for n in NAMES if Path(n).exists()}
    send['errors'] = errors[-8000:]
    req = urllib.request.Request(URL, data=json.dumps(send).encode(), headers={'Content-Type': 'application/json'})
    for name, code in json.load(urllib.request.urlopen(req, timeout=600)).items():
        Path(name).write_text(code)
        print('wrote', name)
else:
    run_tests()
