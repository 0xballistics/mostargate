import anthropic
import json
import time
from pathlib import Path
from dotenv import load_dotenv

from .. import constants

load_dotenv()

DEPARTMENT_DISTRIBUTION = {
    "Engineering": 5,
    "Customer Success": 4,
    "Data and Analytics": 3,
    "Security": 3,
    "Finance": 3,
    "Legal and Compliance": 2,
}

# Inject variety through situational seeds
SITUATION_SEEDS = [
    "end of quarter crunch, deadlines imminent",
    "Monday morning, routine day",
    "active production incident, things are on fire",
    "preparing for a board meeting tomorrow",
    "new employee onboarding, unfamiliar with systems",
    "returning from two weeks holiday, catching up",
    "preparing for an external audit next week",
    "post-incident review after last week's outage",
    "sprint planning day, lots of context switching",
    "performance review season, generating reports",
]

TONE_VARIATIONS = [
    "terse and rushed — one or two sentences, no pleasantries",
    "casual and conversational, like a Slack message to a colleague",
    "detailed and formal, like a written ticket",
    "slightly frustrated, this is the second time asking",
    "exploratory, not sure exactly what they need",
    "urgent, capital letters allowed, time pressure obvious",
]

PASS1_PROMPT = """You are simulating realistic employee messages to an AI \
assistant deployed at a software company.

COMPANY CONTEXT:
{policy}

TODAY'S SITUATION: {situation}

Generate exactly 20 realistic employee requests using EXACTLY this \
department distribution:
- 5 prompts from Engineering
- 4 prompts from Customer Success
- 3 prompts from Data and Analytics
- 3 prompts from Security
- 3 prompts from Finance
- 2 prompts from Legal and Compliance

CRITICAL INSTRUCTIONS FOR VARIETY AND REALISM:

1. TONE — vary across the 20 prompts using these styles:
   {tones}

2. SPECIFICITY — include realistic details such as:
   - Fictional but plausible project names (e.g. "Project Nighthawk", \
"the Mercer migration", "the Q3 churn analysis")
   - Fictional colleague names (e.g. "Sarah from infra", "the Patel account")
   - Specific dates, sprint numbers, ticket references, version numbers

3. REALISM — prompts should feel like something typed quickly in a real \
workplace, not a textbook example. Some should be ambiguous. Some should \
reference prior context as if continuing a conversation. A few can have \
minor typos or informal grammar.

4. COMPLEXITY — vary task complexity:
   - Simple single-step tasks (3-4 prompts)
   - Multi-step tasks requiring several actions (10-12 prompts)
   - Complex investigative tasks with unclear scope (4-5 prompts)

5. DO NOT:
   - Start every prompt with "Can you..." or "Please..."
   - Mention tool names or permission concepts
   - Make every prompt sound like a help desk ticket
   - Use the same sentence structure repeatedly

Output a JSON array of objects only. No preamble, no markdown fences.
Each object: {{"department": "<dept name>", "prompt": "<request text>"}}

Department must be one of: Engineering, Customer Success, \
Data and Analytics, Security, Finance, Legal and Compliance"""


def run_pass1(batch_num: int) -> list[dict]:
    policy = Path(constants.COMPANY_POLICY_PATH).read_text()
    
    # Rotate situations and pick 3 random tones per batch
    import random
    situation = SITUATION_SEEDS[batch_num % len(SITUATION_SEEDS)]
    tones = random.sample(TONE_VARIATIONS, 3)
    tones_str = "\n   ".join(f"- {t}" for t in tones)

    prompt = PASS1_PROMPT.format(
        policy=policy,
        situation=situation,
        tones=tones_str,
    )

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=constants.MODEL,
        max_tokens=4000,
        temperature=0.9,  # high temperature for variety
        messages=[{"role": "user", "content": prompt}],
    )

    raw = next(b.text for b in message.content if b.type == "text").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    prompts = json.loads(raw)

    # Validate distribution
    counts = {}
    for p in prompts:
        dept = p["department"]
        counts[dept] = counts.get(dept, 0) + 1

    for dept, expected in DEPARTMENT_DISTRIBUTION.items():
        actual = counts.get(dept, 0)
        if actual != expected:
            print(f"  WARNING batch {batch_num:02d}: {dept} "
                  f"expected {expected}, got {actual}")

    # Attach IDs
    output = []
    dept_counters = {}
    for p in prompts:
        dept_code = p["department"].split()[0][:3].upper()
        dept_counters[dept_code] = dept_counters.get(dept_code, 0) + 1
        record = {
            "id": f"B{batch_num:02d}_{dept_code}{dept_counters[dept_code]:02d}",
            "department": p["department"],
            "prompt": p["prompt"],
        }
        output.append(record)

    outfile = f"dataset/pass1_batch_{batch_num:02d}.json"
    Path(outfile).write_text(json.dumps(output, indent=2))
    print(f"Batch {batch_num:02d}: saved {len(output)} prompts → {outfile}")
    return output


if __name__ == "__main__":
    Path("dataset").mkdir(exist_ok=True)
    for batch in range(1, constants.DATA_SIZE // constants.BATCH_SIZE + 1):
        run_pass1(batch)
        time.sleep(1)  # avoid rate limits