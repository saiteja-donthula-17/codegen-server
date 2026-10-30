# Served by /run and executed on the user's machine:
#   curl -fsSL ".../run?token=..." | python3                                  (server's keys and model)
#   curl -fsSL ".../run?token=..." | GEMINI_MODEL=gemini-3.6-flash python3   (pick the model)
import os
import sys
import json
import getpass
import threading
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
# notes that show the project's conventions (e.g. load_dotenv in agents.py); never the real .env with secrets
DOCS = [p for n in ['README.md', '.env.example', 'requirements.txt'] for p in [n, '../' + n] if Path(p).exists()]

# the key stays on this machine until it is sent as a header, never in the URL; no key = the server's keys
KEY = os.getenv('GEMINI_API_KEY')
if not KEY:
    try:
        KEY = getpass.getpass("Gemini API key (Enter = use the server's keys): ").strip()  # reads the terminal
    except EOFError:  # no terminal to ask on
        pass
MODEL = os.getenv('GEMINI_MODEL')  # none = the server's default
print('key:', 'yours' if KEY else "the server's", '| model:', MODEL or "the server's default")

# tests run like run.sh: the project must read its own .env, so the key typed for this script is left out
TEST_ENV = {k: v for k, v in os.environ.items() if k not in ('GEMINI_API_KEY', 'GEMINI_MODEL')}
# problems in the project's .env that no code change can fix
ENV_PROBLEMS = {
    'API_KEY_INVALID': "GEMINI_API_KEY in your project's .env is not valid - put your current key there",
    'no longer available': "GEMINI_MODEL in your project's .env is closed to your key - use gemini-3.5-flash-lite",
}


def read(path, limit=None):
    """Text of a file, or None if it is missing or binary."""
    try:
        return Path(path).read_text(encoding='utf-8')[:limit]
    except (OSError, UnicodeDecodeError):
        return None


def run_tests():
    r = subprocess.run([sys.executable, '-m', 'pytest', TESTS, '-q', '--tb=short'],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL, env=TEST_ENV)
    out = r.stdout + r.stderr
    print('tests:', (out.strip().splitlines() or ['no output'])[-1])
    return r.returncode == 0, out


def post(req):
    """Server reply, with a line every 30s so a slow model doesn't look stuck."""
    done = threading.Event()

    def tick():
        waited = 0
        while not done.wait(30):
            waited += 30
            print(f'  still waiting for {MODEL or "Gemini"}... {waited}s', flush=True)

    threading.Thread(target=tick, daemon=True).start()
    try:
        return json.load(urllib.request.urlopen(req, timeout=600))
    finally:
        done.set()


send = {}
for n in [TESTS] + FILES:
    send[n] = read(n)
for p in DATA:
    send[str(p)] = read(p, 3000)  # data is only a sample so Gemini sees paths and fields
for p in DOCS:
    send[p] = read(p, 20000)
send = {n: text for n, text in send.items() if text is not None}
print('tests file:', TESTS, '| data files:', sum(str(p) in send for p in DATA))

broken = ''  # syntax errors in Gemini's last reply, sent back so it can fix them
for round in range(1, 4):  # stops early as soon as all tests pass
    ok, errors = run_tests()
    if ok:
        break
    problems = [msg for marker, msg in ENV_PROBLEMS.items() if marker in errors]
    if problems:
        sys.exit('\n'.join(problems))
    print(f'round {round}/3: asking {MODEL or "Gemini"} to fix the failing tests...')
    for n in FILES:
        if read(n) is not None:
            send[n] = read(n)
    send['errors'] = broken + errors[-8000:]
    headers = {'Content-Type': 'application/json', 'X-Python': '.'.join(map(str, sys.version_info[:2]))}
    if KEY:
        headers['X-Api-Key'] = KEY
    if MODEL:
        headers['X-Model'] = MODEL
    req = urllib.request.Request(URL, data=json.dumps(send).encode(), headers=headers)
    try:
        result = post(req)
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
    if not result:
        print('  no usable files in the reply this round')
    broken = ''
    for name, code in result.items():
        try:
            compile(code, name, 'exec')  # with this machine's Python, the one that runs the tests
        except SyntaxError as e:  # keep the working file; a broken one would fail every test
            print(f'  skipped {name} - syntax error on line {e.lineno}: {e.msg}')
            broken += (f'Your last {name} was not used: SyntaxError on line {e.lineno}: {e.msg}: '
                       f'{(e.text or "").strip()} (this machine runs Python {sys.version.split()[0]})\n')
            continue
        Path(name).write_text(code, encoding='utf-8')
        print('  wrote', name)
else:
    ok, _ = run_tests()
print('DONE - all tests pass' if ok else 'NOT DONE - some tests still fail, run the command again')
