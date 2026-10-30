import os
import re
import time
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse
from google import genai
from google.genai import errors

app = FastAPI()
FILES = ['state.py', 'tools.py', 'agents.py', 'nodes.py', 'graph.py', 'main.py']


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
    # each user brings their own Gemini key and model; the server's env values are only a fallback
    key = x_api_key or os.getenv('GEMINI_API_KEY')
    model = x_model or os.getenv('GEMINI_MODEL') or 'gemini-3.5-flash-lite'
    if not key:
        raise HTTPException(400, 'no Gemini API key - set GEMINI_API_KEY before running')
    client = genai.Client(api_key=key)

    given = ''
    for name, content in sent.items():
        given += f'FILE: {name}\n{content}\n'

    prompt = f"""Write {FILES} so all tests pass. If current code and errors are given, fix them.
Simple code, no ``` marks. Start each file with a line: FILE: name.py
The code runs on Python {x_python}: inside an f-string never reuse its own quote character.

{given}"""

    # the client compiles each file with its own Python before writing it
    return split_files(ask_gemini(client, model, prompt))


def ask_gemini(client, model, prompt):
    """Gemini's reply, retrying when it is briefly overloaded (503) or rate limited (429)."""
    for attempt in range(3):
        try:
            reply = client.models.generate_content(model=model, contents=prompt)
            if reply.candidates and reply.candidates[0].finish_reason == 'MAX_TOKENS':
                print('gemini reply hit the output limit of', model)
            if reply.text:
                return reply.text
        except errors.ClientError as e:
            if e.code != 429:  # bad key, unknown model - retrying won't help
                raise HTTPException(e.code, f'Gemini: {e.message}')
            print('gemini rate limited:', e.message)
        except Exception as e:
            print('gemini failed:', e)
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
