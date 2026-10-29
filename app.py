import os
from fastapi import FastAPI, HTTPException
from google import genai

app = FastAPI()
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
FILES = ['state.py', 'tools.py', 'agents.py', 'nodes.py', 'graph.py', 'main.py']


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
