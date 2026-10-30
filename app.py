import os
import re
import time
import random
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from google import genai
from google.genai import errors

app = FastAPI()
FILES = ['state.py', 'tools.py', 'agents.py', 'nodes.py', 'graph.py', 'main.py']
# shared keys for users who don't bring their own: GEMINI_API_KEYS=key1,key2,... on Render
SERVER_KEYS = [k.strip() for k in (os.getenv('GEMINI_API_KEYS') or os.getenv('GEMINI_API_KEY') or '').split(',')
               if k.strip()]


@app.get('/run', response_class=PlainTextResponse)
def run(token: str, request: Request):
    """Returns client.py ready to pipe into python3."""
    if token != os.getenv('APP_TOKEN'):
        raise HTTPException(401, 'wrong token')
    base = os.getenv('RENDER_EXTERNAL_URL') or str(request.base_url).rstrip('/')
    script = (Path(__file__).parent / 'client.py').read_text()
    script = script.replace('__URL__', f'{base}/generate?token={token}')
    return script.replace('__FILES__', repr(FILES))


@app.post('/generate')
def generate(sent: dict[str, str], token: str, x_api_key: str = Header(None), x_model: str = Header(None),
             x_python: str = Header('3.11')):
    if token != os.getenv('APP_TOKEN'):
        raise HTTPException(401, 'wrong token')
    # a user's own key is used alone; otherwise the server's keys, in random order to spread the quota
    keys = [x_api_key] if x_api_key else random.sample(SERVER_KEYS, len(SERVER_KEYS))
    model = x_model or os.getenv('GEMINI_MODEL') or 'gemini-3.5-flash-lite'
    if not keys:
        raise HTTPException(400, 'no Gemini API key - set GEMINI_API_KEY before running')

    given = ''
    for name, content in sent.items():
        given += f'FILE: {name}\n{content}\n'

    prompt = f"""Write {FILES} so all tests pass. If current code and errors are given, fix them.
Simple code, no ``` marks. Start each file with a line: FILE: name.py
The code runs on Python {x_python}: inside an f-string never reuse its own quote character.
Follow README.md and .env.example if given, e.g. read settings from .env with python-dotenv.

{given}"""

    # the client compiles each file with its own Python before writing it
    return split_files(ask_gemini(keys, model, prompt))


def ask_gemini(keys, model, prompt):
    """Gemini's reply. Each key is tried in turn; rate limits (429) and overloads (503) get a pause and a retry."""
    for attempt in range(3):
        failed, wait = None, False
        for i, key in enumerate(keys, 1):
            try:
                reply = genai.Client(api_key=key).models.generate_content(model=model, contents=prompt)
                if reply.candidates and reply.candidates[0].finish_reason == 'MAX_TOKENS':
                    print('gemini reply hit the output limit of', model)
                if reply.text:
                    return reply.text
            except errors.ClientError as e:  # bad key, used-up quota, model closed to this key: try the next key
                print(f'key {i}/{len(keys)} failed: {e.code} {e.message}', flush=True)
                failed, wait = e, wait or e.code == 429
            except Exception as e:
                print('gemini failed:', e, flush=True)
                wait = True
        if failed and not wait:  # every key was refused and a pause won't change that
            raise HTTPException(failed.code, f'Gemini: {failed.message}')
        if attempt < 2:
            time.sleep(10)
    raise HTTPException(503, 'Gemini busy or rate limited, run again in a minute')


def split_files(text):
    """{name: code} from a reply made of "FILE: name.py" sections."""
    # [^\w\n] not \W: \W also matches newlines, so the header ate a closing "}" or opening '"""' next to it
    parts = re.split(r'^[^\w\n]*FILE:[^\w\n]*(\S+?)[^\w\n]*$', text, flags=re.M)  # [before, name, code, ...]
    files = {}
    for name, code in zip(parts[1::2], parts[2::2]):
        lines = code.strip().splitlines()
        if lines and lines[0].startswith('```'):  # Gemini adds fences despite the prompt
            lines = lines[1:]
        if lines and lines[-1].startswith('```'):
            lines = lines[:-1]
        if name in FILES and lines:  # an empty block must not wipe the user's file
            files[name] = '\n'.join(lines) + '\n'
    return files
