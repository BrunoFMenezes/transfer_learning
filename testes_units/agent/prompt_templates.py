PROMPT_HEADER = """        You are an automated test generator for Python functions. Generate a single pure Python file content that is a pytest test module.

Requirements:
- The file must start with exactly: import pytest
- Use only valid python code (no surrounding markdown or explanation).
- Create tests for the provided source. For each public function in the source produce:
  - at least one 'success' test: def test_<func>_success(): ...
  - at least one 'failure' test: def test_<func>_failure(): ...
- Use clear, deterministic asserts (avoid random data).
- When creating inputs, prefer small fixed examples and include edge-case for failure (e.g., invalid type, zero-division, ValueError).
- Name the file content such that it can be written to test_<module>.py.
- Keep tests self-contained: import the module under test using its module name (e.g., import examples.math_ops as mod).
- Do not import or call any network resources.
- Output ONLY the Python file content.

Source file path: {src_path}
Source code:
"""\n{source}\n"""
"""
