"""ChemCrow + Agnes AI（OpenAI 兼容）快速启动入口。

用法:
  .\\.venv\\Scripts\\python.exe run_chemcrow.py "What is the SMILES of aspirin?"
  .\\.venv\\Scripts\\python.exe run_chemcrow.py --interactive
"""

from __future__ import annotations

import argparse
import os
import sys

from dotenv import load_dotenv


def _configure_agnes_llm_compat() -> None:
    """让 ChemCrow 接受任意 chat 模型，并指向 Agnes Base URL。"""
    import langchain
    from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

    import chemcrow.agents.chemcrow as chemcrow_mod

    api_base = (
        os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or "https://apihub.agnes-ai.com/v1"
    ).rstrip("/")
    os.environ["OPENAI_API_BASE"] = api_base

    # 旧版 openai/langchain 用 tiktoken 估算长度；Agnes 模型名不存在于词表，映射到 gpt-4
    tiktoken_model = os.getenv("CHEMCROW_TIKTOKEN_MODEL", "gpt-4")

    def _make_llm(model, temp, api_key, streaming: bool = False):
        return langchain.chat_models.ChatOpenAI(
            temperature=temp,
            model_name=model,
            request_timeout=1000,
            streaming=streaming,
            callbacks=[StreamingStdOutCallbackHandler()] if streaming else [],
            openai_api_key=api_key,
            openai_api_base=api_base,
            tiktoken_model_name=tiktoken_model,
        )

    chemcrow_mod._make_llm = _make_llm


def build_agent():
    load_dotenv()

    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_key or openai_key.startswith("sk-your-"):
        print(
            "缺少 OPENAI_API_KEY。请在 .env 填入 Agnes API Key。",
            file=sys.stderr,
        )
        sys.exit(1)

    _configure_agnes_llm_compat()

    from chemcrow.agents import ChemCrow

    api_keys = {
        "OPENAI_API_KEY": openai_key,
        "RXN4CHEM_API_KEY": os.getenv("RXN4CHEM_API_KEY", ""),
        "SERP_API_KEY": os.getenv("SERP_API_KEY", ""),
        "CHEMSPACE_API_KEY": os.getenv("CHEMSPACE_API_KEY", ""),
        "SEMANTIC_SCHOLAR_API_KEY": os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""),
    }

    model = os.getenv("CHEMCROW_MODEL", "agnes-2.5-flash")
    tools_model = os.getenv("CHEMCROW_TOOLS_MODEL", "agnes-2.5-flash")
    temp = float(os.getenv("CHEMCROW_TEMP", "0.1"))
    max_iterations = int(os.getenv("CHEMCROW_MAX_ITERATIONS", "40"))
    api_base = os.getenv("OPENAI_API_BASE", "https://apihub.agnes-ai.com/v1")

    print(f"[ChemCrow] base={api_base}")
    print(f"[ChemCrow] model={model} tools_model={tools_model}")
    return ChemCrow(
        model=model,
        tools_model=tools_model,
        temp=temp,
        max_iterations=max_iterations,
        streaming=False,
        openai_api_key=openai_key,
        api_keys=api_keys,
        verbose=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ChemCrow with Agnes AI")
    parser.add_argument("prompt", nargs="?", help="一次性提问")
    parser.add_argument(
        "-i",
        "--interactive",
        action="store_true",
        help="交互模式（多次提问）",
    )
    args = parser.parse_args()

    agent = build_agent()

    if args.interactive or not args.prompt:
        print("进入交互模式，输入问题后回车；输入 exit / quit 退出。")
        while True:
            try:
                prompt = input("\nYou> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出。")
                break
            if not prompt:
                continue
            if prompt.lower() in {"exit", "quit", "q"}:
                print("已退出。")
                break
            answer = agent.run(prompt)
            print(f"\nChemCrow>\n{answer}")
        return

    answer = agent.run(args.prompt)
    print(f"\nChemCrow>\n{answer}")


if __name__ == "__main__":
    main()
