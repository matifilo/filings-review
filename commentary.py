"""Phase 5: ask Claude to write the quarterly review from the facts pack - and from nothing else."""
import json
import os
from pathlib import Path

import anthropic
from dotenv import load_dotenv

import config

# 1) Get the API key from the .env file (it never appears in the code)
load_dotenv()
if not os.getenv("ANTHROPIC_API_KEY"):
    raise SystemExit("No API key found. Put ANTHROPIC_API_KEY=... in the .env file (Phase 5, step 5.3).")

# 2) Read the two inputs: the rules, and the facts the AI is allowed to use
rules = Path("prompts/system.md").read_text(encoding="utf-8")
pack = json.loads(Path("output/facts_pack.json").read_text(encoding="utf-8"))
facts_text = "FACTS PACK:\n" + json.dumps(pack, indent=1, sort_keys=True)

# 3) Send them to Claude
client = anthropic.Anthropic()  # finds the key in the environment by itself
response = client.messages.create(
    model=config.MODEL,
    max_tokens=16000,                  # the most the reply may be (a review uses far less)
    thinking={"type": "adaptive"},     # let the model think before it writes, as much as it needs
    system=[
        {"type": "text", "text": rules},
        # cache_control: keep the rules + facts on Anthropic's side for 5 minutes, so the
        # revision rounds in Phase 6 re-read them at a fraction of the price
        {"type": "text", "text": facts_text, "cache_control": {"type": "ephemeral"}},
    ],
    messages=[{
        "role": "user",
        "content": f"Write the quarterly review for {pack['company']['name']}, {pack['latest_period']}.",
    }],
)

# 4) Keep only the written text (the model's thinking is not part of the review)
draft = "".join(block.text for block in response.content if block.type == "text")
out = Path("output/draft.md")
out.write_text(draft, encoding="utf-8")

# 5) Show what it cost, in tokens (1 token is roughly 3/4 of a word)
u = response.usage
print(f"Model: {response.model}   stop reason: {response.stop_reason}")
print(f"Input tokens: {u.input_tokens}   written to cache: {u.cache_creation_input_tokens or 0}   "
      f"read from cache: {u.cache_read_input_tokens or 0}")
print(f"Output tokens: {u.output_tokens}")
print(f"Draft: {len(draft.split())} words -> {out}")