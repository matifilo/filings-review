"""Run the whole pipeline with one command.

    .venv\\Scripts\\python run.py                  download fresh SEC data, then every step
    .venv\\Scripts\\python run.py --no-download    reuse the newest saved snapshot (no SEC request)

It stops at the first step that fails, so a broken step never feeds the next one.
"""
import subprocess
import sys
import time

STEPS = [
    ("download.py", "Download the SEC company facts snapshot"),
    ("load.py", "Load the chosen line items into SQLite and build the SQL views"),
    ("facts.py", "Build the facts pack and the data flags"),
    ("review.py", "Claude writes the review, the checker approves it (uses the API)"),
    ("report.py", "Lay out the report and print the PDF"),
]

skip = {"download.py"} if "--no-download" in sys.argv else set()
started = time.time()
for number, (script, what) in enumerate(STEPS, 1):
    print(f"\n[{number}/{len(STEPS)}] {what}" + (": skipped" if script in skip else f"  ({script})"),
          flush=True)  # print the heading now, before the step's own output
    if script in skip:
        continue
    result = subprocess.run([sys.executable, script])  # sys.executable = the same Python that runs this file
    if result.returncode != 0:
        raise SystemExit(f"\nStopped: {script} failed, so nothing after it was run.")
print(f"\nDone in {time.time() - started:.0f} seconds. Open output\\report.pdf")