#!/usr/bin/env python3
"""Second opinion from OpenAI GPT-6 Astra for the Sexta-feira agent (ADR 0002).

Usage:
    uv run python infra/scripts/ask_astra.py "pergunta"            # prompt as argument
    cat docs/plans/M1.md | uv run python infra/scripts/ask_astra.py  # prompt from stdin
    uv run python infra/scripts/ask_astra.py --system "voce e revisor de risco" --file docs/RISK_ENGINE.md "revise"

Reads OPENAI_API_KEY (and optional OPENAI_MODEL, default gpt-6-astra) from the
environment or from the repository's local .env; never prints the key. The
answer is DATA for the agent to weigh — it never approves, executes or changes
anything by itself. Exit 2 when no key is configured, so callers can skip.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_MODEL = "gpt-6-astra"
ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); does not override existing env."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def read_prompt(args: argparse.Namespace) -> str:
    parts: list[str] = []
    if args.file:
        parts.append(
            f'<document path="{args.file}">\n{Path(args.file).read_text(encoding="utf-8")}\n</document>'
        )
    if args.prompt:
        parts.append(" ".join(args.prompt))
    elif not sys.stdin.isatty():
        parts.append(sys.stdin.read())
    prompt = "\n\n".join(p for p in parts if p.strip())
    if not prompt.strip():
        raise SystemExit("ask_astra: nothing to ask (pass a prompt argument, --file, or stdin)")
    return prompt


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask GPT-6 Astra for a second opinion.")
    parser.add_argument("prompt", nargs="*", help="the question; stdin is used when omitted")
    parser.add_argument("--file", help="attach a file's content as a quoted document")
    parser.add_argument(
        "--system",
        default=(
            "You are a senior reviewer giving a second opinion on PROJECT HUNTER, a multi-tenant crypto "
            "quant SaaS. Be concrete: name the file/line or the exact rule, give a failure scenario for "
            "every concern, and separate 'must fix' from 'nice to have'. Never claim something was "
            "executed or verified; you only read what you are given. Answer in the language of the question."
        ),
    )
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-tokens", type=int, default=4000)
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print(
            "ask_astra: OPENAI_API_KEY is not configured (add it to the local .env). Skipping.",
            file=sys.stderr,
        )
        return 2
    model = args.model or os.environ.get("OPENAI_MODEL", "").strip() or DEFAULT_MODEL
    prompt = read_prompt(args)

    from openai import OpenAI  # imported late so the missing-key path stays dependency-free

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        max_completion_tokens=args.max_tokens,
        messages=[
            {"role": "system", "content": args.system},
            {"role": "user", "content": prompt},
        ],
    )
    choice = response.choices[0]
    text = (choice.message.content or "").strip()
    usage = response.usage
    print(text)
    if usage is not None:
        print(
            f"\n[astra] model={model} prompt_tokens={usage.prompt_tokens} completion_tokens={usage.completion_tokens}",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
