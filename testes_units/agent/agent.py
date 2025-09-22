import os
from dotenv import load_dotenv
from langchain.chat_models import AzureChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from .prompt_templates import PROMPT_HEADER

load_dotenv()  # read .env at repo root

AZ_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZ_KEY = os.getenv("AZURE_OPENAI_KEY")
AZ_DEPLOY = os.getenv("AZURE_OPENAI_DEPLOYMENT")

if not (AZ_ENDPOINT and AZ_KEY and AZ_DEPLOY):
    raise RuntimeError("Configure AZURE_OPENAI_* env vars or .env file")

# LangChain/AzureChatOpenAI configuration
llm = AzureChatOpenAI(
    deployment_name=AZ_DEPLOY,
    openai_api_base=AZ_ENDPOINT,
    openai_api_key=AZ_KEY,
    temperature=0.0,
    max_tokens=1000,
    request_timeout=120
)

def generate_tests_for_file(src_path: str, out_dir: str = "."):
    """Read source file, call LLM to generate pytest module content,
    validate simple checks and write to out_dir/test_<module>.py"""

    src_path = os.path.abspath(src_path)
    module_name = os.path.splitext(os.path.basename(src_path))[0]
    with open(src_path, "r", encoding="utf-8") as f:
        source = f.read()

    prompt = PROMPT_HEADER.format(src_path=src_path, source=source)
    sys_msg = SystemMessage(content="You are an expert Python developer and pytest author.")
    user_msg = HumanMessage(content=prompt)

    resp = llm([sys_msg, user_msg])
    content = resp.content.strip()

    # Basic sanity checks on LLM response
    if not content.startswith("import pytest"):
        raise ValueError("LLM output did not start with 'import pytest' — aborting")

    # ensure contains at least one test_ function
    if "def test_" not in content:
        raise ValueError("No test functions detected in LLM output")

    out_fname = os.path.join(out_dir, f"test_{module_name}.py")
    os.makedirs(out_dir, exist_ok=True)
    with open(out_fname, "w", encoding="utf-8") as outf:
        outf.write(content + "\n")

    return out_fname
