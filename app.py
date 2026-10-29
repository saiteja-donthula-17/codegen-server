import os
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse
from google import genai

app = FastAPI()
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
FILES = ['state.py', 'tools.py', 'agents.py', 'nodes.py', 'graph.py', 'main.py']
DATA = ['data/purchase_orders.csv', 'data/payment_ledger.csv', 'data/procurement_meetings.json']


@app.get('/run', response_class=PlainTextResponse)
def run(token: str, request: Request):
    """Returns client.py ready to pipe into python3."""
    if token != os.getenv('APP_TOKEN'):
        raise HTTPException(401, 'wrong token')
    base = os.getenv('RENDER_EXTERNAL_URL') or str(request.base_url).rstrip('/')
    script = (Path(__file__).parent / 'client.py').read_text()
    script = script.replace('__URL__', f'{base}/generate?token={token}')
    return script.replace('__NAMES__', repr(['pytest/tests.py'] + FILES + DATA))


@app.post('/generate')
def generate(sent: dict[str, str], token: str):
    if token != os.getenv('APP_TOKEN'):
        raise HTTPException(401, 'wrong token')

    given = ''
    for name, content in sent.items():
        given += f'FILE: {name}\n{content}\n'

    prompt = f"""Write {FILES} so all tests pass. If current code and errors are given, fix them.
Simple code, no ``` marks. Start each file with a line: FILE: name.py

{given}"""

    text = client.models.generate_content(model=os.getenv('GEMINI_MODEL'), contents=prompt).text

    result = {}
    for chunk in text.split('FILE: ')[1:]:
        name, code = chunk.split('\n', 1)
        if name.strip() in FILES:
            result[name.strip()] = code
    return result
