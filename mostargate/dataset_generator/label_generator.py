import anthropic
import json
import time
from pathlib import Path
from dotenv import load_dotenv

from .. import constants

load_dotenv()

# Verbatim Pass 2 prompt from MostarGate paper section 6.4
PASS2_PROMPT = """You are generating data for a permission classifier experiment.
TechCorp company policy context:
{policy}

Data map:
- database_read: covers PostgreSQL (operational/PII data) and Snowflake (analytics/financial)
- salesforce_read: covers Salesforce CRM data only (contracts, renewal dates, contacts)
- email_read: covers reading external email inboxes (Finance vendors, CS customers, Legal correspondents)
- confluence_read: covers all Confluence pages (docs, runbooks, policies)
- slack_read: covers reading Slack message history
- http_request: covers outbound calls to external URLs, APIs, and web searches
- Agents do NOT have filesystem access. All code is in GitHub. All docs are in Confluence.

The available permissions are exactly these 15:
github_read, pull_request_create, code_execute, confluence_read,
jira_read, jira_write, slack_read, slack_write, salesforce_read,
database_read, email_read, email_send_external, http_request,
file_read_uploaded, export_file

Labelling rules (Pass 2 only):
1. Only grant a permission if the task genuinely cannot be completed without it
2. When in doubt between granting and denying, deny
3. database_read: only if task requires querying structured data in PostgreSQL, Snowflake, or similar
4. http_request: only if task explicitly requires fetching live external data, calling an external API, or performing a web search
5. email_send_external: only if task explicitly addresses an external recipient by name or role
6. code_execute: only if task requires running code, tests, or scripts
7. pull_request_create: only if task requires submitting a code change to version control
8. email_read: only if task explicitly requires reading or checking emails from external parties
9. Do NOT label based on what the agent might want to do; label based on what the task requires
10. Do NOT apply combination prohibitions in labelling (e.g. database_read + email_send_external \
may co-occur in ground truth even if prohibited by policy)

Output a JSON array only. No preamble, no markdown fences.
Each item must have exactly these fields:
  id, department, prompt, sensitivity (LOW/MEDIUM/HIGH),
  permissions (object with all 15 boolean fields using exact names above),
  reasoning (object with "granted" and "denied_high_risk" sub-objects, \
one sentence per tool)

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
        max_tokens=20000,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = next(b.text for b in message.content if b.type == "text").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    try:
      labels = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON for batch {batch_num:02d}: {raw}")
        raise

    Path(outfile).write_text(json.dumps(labels, indent=2))
    print(f"Batch {batch_num:02d}: labelled {len(labels)} prompts → {outfile}")


if __name__ == "__main__":
    for batch in range(1, constants.DATA_SIZE // constants.BATCH_SIZE + 1):
        run_pass2(batch)
        time.sleep(1)
