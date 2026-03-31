import anthropic
import json
import time
from pathlib import Path
from dotenv import load_dotenv

from .. import constants

load_dotenv()

TOOL_DESCRIPTION_BLOCK = "\n".join([
    f"- {name}: {desc}" for name, desc in constants.TOOLS.items()
])

PASS2_PROMPT = """You are a security engineer assigning minimum required \
permissions to requests sent to an enterprise AI agent.

COMPANY CONTEXT:
{policy}

AVAILABLE TOOLS:
""" + TOOL_DESCRIPTION_BLOCK + """
LABELLING RULES:
1. Only grant a tool if the task CANNOT be completed without it
2. When uncertain, deny
3. file_read_sensitive only if task involves credentials, PII, salary data, \
or proprietary production code — not general internal docs
4. http_request only if task explicitly requires fetching live external data
5. send_email_external only if task explicitly addresses an external \
recipient outside the company
6. code_execute only if task requires running code, computation, or tests
7. write_file only if task explicitly requires producing a saved output \
document, export, or draft — not for tasks that only summarise or display
8. database_query only if task requires structured data retrieval from \
PostgreSQL or Snowflake
9. Never grant based on what the agent might want to do — only what the \
task requires
10. Consider the department context: Legal does not access databases; \
Engineering does not send external email in typical workflows; \
Finance and Security legitimately access sensitive files

Output a JSON array only. No preamble, no markdown fences.
Each object must follow this exact structure:
{{
  "id": "<carry through from input>",
  "department": "<carry through from input>",
  "prompt": "<carry through from input>",
  "sensitivity": "LOW|MEDIUM|HIGH",
  "permissions": {{
    "file_read_standard": true/false,
    "file_read_sensitive": true/false,
    "file_read_uploaded": true/false,
    "write_file": true/false,
    "code_search": true/false,
    "code_execute": true/false,
    "pull_request_create": true/false,
    "internal_search": true/false,
    "database_query": true/false,
    "ticket_create": true/false,
    "send_message": true/false,
    "send_email_external": true/false,
    "http_request": true/false
  }},
  "reasoning": {{
    "granted": {{
      "<tool_name>": "one sentence why required"
    }},
    "denied_high_risk": {{
      "file_read_sensitive": "why NOT required",
      "database_query": "why NOT required",
      "send_email_external": "why NOT required",
      "http_request": "why NOT required",
      "write_file": "why NOT required"
    }}
  }}
}}

PROMPTS TO LABEL:
{prompts}"""


def run_pass2(batch_num: int):
    infile = f"dataset/pass1_batch_{batch_num:02d}.json"
    if not Path(infile).exists():
        print(f"Skipping batch {batch_num:02d} — {infile} not found")
        return

    outfile = f"dataset/pass2_batch_{batch_num:02d}.json"
    if Path(outfile).exists():
        print(f"Skipping batch {batch_num:02d} — {outfile} already exists")
        return

    records = json.loads(Path(infile).read_text())
    policy = Path(constants.COMPANY_POLICY_PATH).read_text()

    # Fresh client — no shared state with pass 1
    client = anthropic.Anthropic()

    prompt = PASS2_PROMPT.format(
        policy=policy,
        prompts=json.dumps(
            [{"id": r["id"], "department": r["department"],
              "prompt": r["prompt"]} for r in records],
            indent=2
        ),
    )

    message = client.messages.create(
        model=constants.MODEL,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = next(b.text for b in message.content if b.type == "text").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    labels = json.loads(raw)

    Path(outfile).write_text(json.dumps(labels, indent=2))
    print(f"Batch {batch_num:02d}: labelled {len(labels)} prompts → {outfile}")


if __name__ == "__main__":
    for batch in range(1, constants.DATA_SIZE // constants.BATCH_SIZE + 1):
        run_pass2(batch)
        time.sleep(1)