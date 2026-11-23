"""Phase 6: write -> check -> revise, until the checker passes (at most 3 rounds).

Only a draft that passes every check becomes output/review.md.
Every round is recorded in output/validation_log.json.
"""
import json
from datetime import datetime
from pathlib import Path

import commentary
import validate

MAX_ROUNDS = 3

pack = commentary.load_pack()
system = commentary.build_system(pack)
messages = [{"role": "user", "content": commentary.first_request(pack)}]
log = []

for round_no in range(1, MAX_ROUNDS + 1):
    # 1) Claude writes (round 1) or rewrites (rounds 2-3) the review
    draft, usage = commentary.ask_claude(system, messages)

    # 2) The checker reads it
    errors = validate.check(draft, pack)
    if usage["stop_reason"] != "end_turn":
        errors.append(f"The reply did not finish normally (stop reason: {usage['stop_reason']}).")

    # 3) Record the round: what was written, what was wrong, what it cost
    log.append({"round": round_no, "time": datetime.now().isoformat(timespec="seconds"),
                "passed": not errors, "errors": errors, "tokens": usage, "draft": draft})
    print(f"Round {round_no}: {len(errors)} problem(s)   tokens in {usage['input']}, "
          f"cache read {usage['cache_read']}, cache write {usage['cache_write']}, out {usage['output']}")
    for e in errors:
        print("   -", e)
    if not errors:
        break

    # 4) Send the exact problems back and ask for a corrected version
    messages.append({"role": "assistant", "content": draft})
    messages.append({"role": "user", "content":
                     "A program checked your review against the facts pack and found these problems:\n- "
                     + "\n- ".join(errors)
                     + "\n\nRewrite the whole review and fix every problem. Keep everything that was "
                       "correct. Follow all the rules. Return only the review."})

# 5) Save the evidence, and publish the review only if it passed
Path("output/draft.md").write_text(draft, encoding="utf-8")
Path("output/validation_log.json").write_text(json.dumps(log, indent=1), encoding="utf-8")
approved = Path("output/review.md")
if errors:
    approved.unlink(missing_ok=True)  # never leave an older approved review lying around
    raise SystemExit(f"FAILED after {MAX_ROUNDS} rounds. Nothing approved. "
                     "Read output/validation_log.json and fix the prompt or the data.")
approved.write_text(draft, encoding="utf-8")
print(f"PASSED in round {round_no} -> {approved}")