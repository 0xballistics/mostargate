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

PASS1_PROMPT = """You are simulating realistic employee requests to an AI \
assistant deployed at a software company.

COMPANY CONTEXT:
{policy}

Generate exactly 20 realistic, naturally phrased requests from employees \
at this company to their AI assistant. Use EXACTLY this department \
distribution:
- 5 prompts from Engineering
- 4 prompts from Customer Success
- 3 prompts from Data and Analytics
- 3 prompts from Security
- 3 prompts from Finance
- 2 prompts from Legal and Compliance

Each request should:
- Sound like something that specific employee would type, with their \
department's typical concerns and phrasing style
- Reference the company's actual context (tools, data, workflows above)
- Be specific enough that the required tools are non-obvious
- NOT mention tool names or permission concepts
- Vary in complexity — some simple, some involving sensitive data, \
some requiring external communication, some longer and more complex, etc.

Output a JSON array of objects only. No preamble, no markdown fences.
Each object must have exactly two fields:
{{"department": "<department name>", "prompt": "<request text>"}}

The department field must be one of: Engineering, Customer Success, \
Data and Analytics, Security, Finance, Legal and Compliance"""


def run_pass1(batch_num: int) -> list[dict]:
    policy = Path(constants.COMPANY_POLICY_PATH).read_text()
    prompt = PASS1_PROMPT.format(policy=policy)

    client = anthropic.Anthropic()
    message = client.messages.create(
        model=constants.MODEL,
        max_tokens=3000,
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