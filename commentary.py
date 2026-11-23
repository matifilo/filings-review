"""The conversation with Claude (Phase 5, turned into reusable functions in Phase 6).

review.py uses these functions. You can still run this file alone to get one unchecked draft:
    .venv\\Scripts\\python commentary.py
"""
import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

import config

load_dotenv()  # reads ANTHROPIC_API_KEY from the .env file


def load_pack():
    """The facts the AI is allowed to use."""
    return json.loads(Path("output/facts_pack.json").read_text(encoding="utf-8"))


def build_system(pack):
    """The background the model always works from: the rules, then the facts (cached)."""
    rules = Path("prompts/system.md").read_text(encoding="utf-8")
    facts_text = "FACTS PACK:\n" + json.dumps(pack, indent=1, sort_keys=True)
    return [
        {"type": "text", "text": rules},
        {"type": "text", "text": facts_text, "cache_control": {"type": "ephemeral"}},
    ]


def first_request(pack):
    return f"Write the quarterly review for {pack['company']['name']}, {pack['latest_period']}."


def ask_claude(system, messages):
    """Send the conversation so far; return the written text and the token counts."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("No API key found. Put ANTHROPIC_API_KEY=... in the .env file (Phase 5, step 5.3).")
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=config.MODEL,
        max_tokens=16000,
        thinking={"type": "adaptive"},
        system=system,
        messages=messages,
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    u = response.usage
    usage = {
        "input": u.input_tokens,
        "cache_write": u.cache_creation_input_tokens or 0,
        "cache_read": u.cache_read_input_tokens or 0,
        "output": u.output_tokens,
        "stop_reason": response.stop_reason,
    }
    return text, usage


# Runs only when you start this file directly, not when review.py imports it
if __name__ == "__main__":
    pack = load_pack()
    draft, usage = ask_claude(build_system(pack), [{"role": "user", "content": first_request(pack)}])
    out = Path("output/draft.md")
    out.write_text(draft, encoding="utf-8")
    print(f"Tokens: {usage}")
    print(f"Draft: {len(draft.split())} words -> {out}")