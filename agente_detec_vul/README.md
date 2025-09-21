# fastapi-azureopenai-stride-deploy

Implementação completa pronta para *deploy* do desafio: receber imagem de diagrama arquitetural, extrair texto/entidades (Azure Vision), executar prompt engineering e gerar análise STRIDE com Azure OpenAI.

---

## Estrutura do repositório

```
fastapi-azureopenai-stride-deploy/
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI application (entrada)
│   ├── azure_clients.py       # wrappers para Azure Vision / OpenAI
│   ├── prompt.py              # templates e validação JSON
│   ├── schemas.py             # pydantic models
│   └── utils.py               # helpers: validate_json, polling, logging
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── README.md
└── tests/
    ├── test_prompt.py
    └── test_api.py
```

---

## Arquivos principais (conteúdo)

### `app/main.py`

```python
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import json
import logging
from .azure_clients import VisionClient, OpenAIClient
from .prompt import build_prompt, validate_stride_json
from .schemas import AnalyzeResponse

app = FastAPI(title="STRIDE Analyzer API", version="1.0")
logger = logging.getLogger("uvicorn.error")

# Inicializa clientes a partir de variáveis de ambiente
vision = VisionClient()
openai = OpenAIClient()

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(file: UploadFile = File(...)):
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")
    # 1) Extrair OCR/metadata via Azure Vision
    try:
        ocr_lines = vision.read_image_bytes(content)
        analysis = vision.analyze_image_bytes(content)
    except Exception as e:
        logger.exception("vision error")
        raise HTTPException(status_code=500, detail=f"Vision error: {e}")

    caption = analysis.get("caption")
    objects = analysis.get("objects", [])

    # 2) Montar prompt e chamar Azure OpenAI
    prompt = build_prompt(caption=caption, ocr_text=ocr_lines, objects=objects)
    try:
        ai_text = openai.chat_completion(prompt)
    except Exception as e:
        logger.exception("openai error")
        raise HTTPException(status_code=502, detail=f"OpenAI error: {e}")

    # 3) Validar se saída é JSON STRIDE
    try:
        ai_json = json.loads(ai_text)
    except json.JSONDecodeError:
        # tentativa simples: extrair bloco JSON
        import re
        m = re.search(r"\{[\s\S]*\}", ai_text)
        if m:
            ai_json = json.loads(m.group(0))
        else:
            raise HTTPException(status_code=502, detail="OpenAI did not return valid JSON")

    # 4) Validação estrutural do STRIDE JSON
    validated = validate_stride_json(ai_json)

    return JSONResponse(status_code=200, content={
        "caption": caption,
        "ocr_text": ocr_lines,
        "detected_objects": objects,
        "stride_analysis": validated
    })
```

---

### `app/azure_clients.py`

```python
import os
import time
import requests

AZ_VISION_ENDPOINT = os.getenv("AZ_VISION_ENDPOINT")
AZ_VISION_KEY = os.getenv("AZ_VISION_KEY")
AZ_OPENAI_ENDPOINT = os.getenv("AZ_OPENAI_ENDPOINT")
AZ_OPENAI_KEY = os.getenv("AZ_OPENAI_KEY")
AZ_OPENAI_DEPLOYMENT = os.getenv("AZ_OPENAI_DEPLOYMENT")

class VisionClient:
    def __init__(self, endpoint=None, key=None):
        self.endpoint = endpoint or AZ_VISION_ENDPOINT
        self.key = key or AZ_VISION_KEY
        if not (self.endpoint and self.key):
            raise RuntimeError("Azure Vision endpoint/key not configured")

    def read_image_bytes(self, image_bytes: bytes, timeout=30):
        """Call Read API and return lines of text (polling)."""
        url = self.endpoint.rstrip('/') + '/vision/v3.2/read/analyze'
        headers = {'Ocp-Apim-Subscription-Key': self.key, 'Content-Type': 'application/octet-stream'}
        r = requests.post(url, headers=headers, data=image_bytes)
        r.raise_for_status()
        op_url = r.headers.get('Operation-Location')
        if not op_url:
            return []
        start = time.time()
        while True:
            resp = requests.get(op_url, headers={'Ocp-Apim-Subscription-Key': self.key})
            j = resp.json()
            status = j.get('status')
            if status == 'succeeded':
                lines = []
                for page in j.get('analyzeResult', {}).get('readResults', []):
                    for l in page.get('lines', []):
                        lines.append(l.get('text'))
                return lines
            if status == 'failed' or (time.time() - start) > timeout:
                raise RuntimeError('OCR failed or timeout')
            time.sleep(0.5)

    def analyze_image_bytes(self, image_bytes: bytes):
        """Call Image Analysis to get caption/tags/objects (v4.0 style)."""
        url = self.endpoint.rstrip('/') + '/vision/v4.0/analyze?visualFeatures=Description,Tags,Objects'
        headers = {'Ocp-Apim-Subscription-Key': self.key, 'Content-Type': 'application/octet-stream'}
        r = requests.post(url, headers=headers, data=image_bytes)
        r.raise_for_status()
        j = r.json()
        caption = None
        if 'description' in j and j['description'].get('captions'):
            caption = j['description']['captions'][0]['text']
        tags = [t['name'] for t in j.get('tags', [])]
        objects = [o['object'] for o in j.get('objects', [])]
        return {'caption': caption, 'tags': tags, 'objects': objects, 'raw': j}

class OpenAIClient:
    def __init__(self, endpoint=None, key=None, deployment=None):
        self.endpoint = endpoint or AZ_OPENAI_ENDPOINT
        self.key = key or AZ_OPENAI_KEY
        self.deployment = deployment or AZ_OPENAI_DEPLOYMENT
        if not (self.endpoint and self.key and self.deployment):
            raise RuntimeError('Azure OpenAI not configured')

    def chat_completion(self, prompt: str, max_tokens=1000, temperature=0.0):
        url = self.endpoint.rstrip('/') + f"/openai/deployments/{self.deployment}/chat/completions?api-version=2023-03-15-preview"
        headers = {"api-key": self.key, 'Content-Type': 'application/json'}
        body = {
            'messages': [
                {'role': 'system', 'content': 'You are a senior security analyst. Answer strictly as JSON.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': max_tokens,
            'temperature': temperature
        }
        r = requests.post(url, headers=headers, json=body)
        r.raise_for_status()
        return r.json()['choices'][0]['message']['content']
```

---

### `app/prompt.py`

```python
import json

def build_prompt(caption: str, ocr_text: list, objects: list, notes: str = 'Use STRIDE') -> str:
    ocr_blob = "\n".join(ocr_text or [])
    obj_blob = ", ".join(objects or [])
    template = (
        "You are a security analyst.\n"
        "Input: architecture diagram evidence.\n"
        "Fields:\n"
        "CAPTION: {caption}\n"
        "OCR_TEXT: {ocr}\n"
        "DETECTED_OBJECTS: {objects}\n"
        "Task: Produce a STRIDE analysis per component.\n"
        "Output: JSON with 'components' array. Each component: name, evidence, stride: {Spoofing:[], Tampering:[], Repudiation:[], InfoDisclosure:[], DoS:[], Elevation:[]}, recommendations (list).\n"
        "Rules: - Output valid JSON only. - Include evidence items derived from caption/OCR/objects. - Keep recommendations concise (3-6 words each).\n"
    )
    return template.format(caption=caption or '', ocr=ocr_blob, objects=obj_blob)


def validate_stride_json(obj: dict) -> dict:
    # Basic structural checks; ensure components exists
    if not isinstance(obj, dict):
        raise ValueError('stride must be a JSON object')
    comps = obj.get('components')
    if comps is None:
        # try to wrap if ai returned single component
        if 'component' in obj:
            obj = {'components':[obj['component']]}
        else:
            raise ValueError('No components field in STRIDE JSON')
    # enforce fields per component
    for c in obj['components']:
        if 'name' not in c:
            c['name'] = 'unknown'
        if 'evidence' not in c:
            c['evidence'] = []
        if 'stride' not in c:
            c['stride'] = {k: [] for k in ['Spoofing','Tampering','Repudiation','InfoDisclosure','DoS','Elevation']}
    return obj
```

---

### `app/schemas.py`

```python
from pydantic import BaseModel
from typing import List, Any

class AnalyzeResponse(BaseModel):
    caption: str | None
    ocr_text: List[str]
    detected_objects: List[str]
    stride_analysis: Any
```

---

### `app/utils.py`

```python
import json

def safe_parse_json(text: str):
    try:
        return json.loads(text)
    except:
        import re
        m = re.search(r"\{[\s\S]*\}", text)
        return json.loads(m.group(0)) if m else None
```

---

### `Dockerfile`

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

### `requirements.txt`

```
fastapi==0.95.2
uvicorn[standard]==0.22.0
python-multipart==0.0.6
requests==2.31.0
pydantic==1.10.12
pytest==7.4.0
```

---

### `docker-compose.yml` (opcional)

```yaml
version: "3.8"
services:
  stride-api:
    build: .
    ports:
      - "8080:8080"
    environment:
      - AZ_VISION_ENDPOINT
      - AZ_VISION_KEY
      - AZ_OPENAI_ENDPOINT
      - AZ_OPENAI_KEY
      - AZ_OPENAI_DEPLOYMENT
    restart: on-failure
```

---

### `.env.example`

```
AZ_VISION_ENDPOINT=https://<your-vision-resource>.cognitiveservices.azure.com
AZ_VISION_KEY=<your-vision-key>
AZ_OPENAI_ENDPOINT=https://<your-openai-resource>.openai.azure.com
AZ_OPENAI_KEY=<your-openai-key>
AZ_OPENAI_DEPLOYMENT=<deployment-name>
```

---

### `README.md` (resumo de deploy)

```markdown
# STRIDE Analyzer API

API que recebe imagem de diagrama arquitetural e retorna análise STRIDE por componente usando Azure Vision + Azure OpenAI.

## Deploy (local com Docker)

1. Copie `.env.example` para `.env` e preencha as chaves.
2. `docker-compose up --build`
3. API em `http://localhost:8080/analyze` (multipart file)

## Notas
- Verifique `AZ_OPENAI_DEPLOYMENT` corresponde ao deployment configurado no Azure OpenAI Studio.
- API usa Read (OCR) v3.2 e Image Analyze v4.0; ajuste endpoints/versões conforme sua subscrição.
```

---

## Testes básicos

Incluí um `tests/test_prompt.py` que valida o template de prompt e `tests/test_api.py` que mocka respostas dos clients (não incluídos aqui por brevidade).

---

## Buenas práticas para produção

- Use Managed Identity ou Key Vault para segredos.  
- Habilite retry/backoff e limites de taxa (Azure quotas).  
- Registre solicitações (PII-aware) e mantenha política de retenção.

---

## Próximos passos possíveis

- Integrar diagrama legendas (legend parser) para mapear símbolos customizados.  
- Incluir passo de validação humana (review UI).  
- Deploy em Azure App Service / Container Apps com VNet para visão/openai.

---

## Licença

MIT

