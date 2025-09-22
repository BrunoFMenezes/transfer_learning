# Py Test Generator (LangChain + Azure OpenAI)

## Objetivo
Agente que gera automaticamente testes pytest a partir de um arquivo Python.

## Estrutura
- agent/: código do agente
- examples/: exemplos de funções a serem testadas
- .env.example: variáveis de ambiente

## Instalação
1. Copie `.env.example` -> `.env` e preencha as chaves do Azure OpenAI.
2. `python -m pip install -r requirements.txt`

## Uso
```python
from agent.agent import generate_tests_for_file
generate_tests_for_file('examples/math_ops.py', out_dir='tests')
generate_tests_for_file('examples/strings.py', out_dir='tests')
```

## Executar testes
```bash
pytest tests -q
```

## Observações
- Temperatura do LLM configurada para 0.0 para determinismo.
- Validações mínimas no output (começa com `import pytest` e contém `def test_`).
