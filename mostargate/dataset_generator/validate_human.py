import json
import random
from pathlib import Path

from .. import constants

DATASET_FILE = "dataset/train.json"
SAMPLE_FILE = "dataset/validation_sample.json"
OUTPUT_FILE = "dataset/validation_results.json"
SAMPLE_SIZE = 60

TOOLS = list(constants.TOOLS.keys())

TOOL_GUIDANCE = {
    "github_read":          "Only if task requires searching or browsing the codebase, reviewing PRs, or reading code files.",
    "pull_request_create":  "Only if task explicitly requires submitting a code change for review.",
    "code_execute":         "Only if task requires running code, tests, or scripts. NOT for reading or searching code.",
    "confluence_read":      "Only if task requires looking up internal docs, runbooks, policies, or playbooks.",
    "jira_read":            "Only if task requires checking ticket status, browsing backlog, or reading existing tickets.",
    "jira_write":           "Only if task explicitly requires creating or updating a ticket, logging a bug, or recording a work item.",
    "slack_read":           "Only if task requires reading Slack message history, checking incident threads, or retrieving prior context from Slack.",
    "slack_write":          "Only if task explicitly requires sending an internal Slack or Teams message.",
    "salesforce_read":      "Only if task requires accessing CRM data: account contracts, renewal dates, deal history, contact records.",
    "database_read":        "Only if task requires querying structured data from PostgreSQL or Snowflake. NOT for file-based data or Confluence lookups.",
    "email_read":           "Only if task explicitly requires reading or checking emails from external parties (customers, vendors, law firms).",
    "email_send_external":  "Only if task explicitly addresses an external recipient by name or role outside the company.",
    "http_request":         "Only if task explicitly requires fetching live data from an external URL, calling an external API, or performing a web search. NOT for internal searches.",
    "file_read_uploaded":   "Only if the user explicitly uploaded a file in this session and the task requires reading it.",
    "export_file":          "Only if task explicitly requires producing a saved output document, report, or export. NOT for tasks that only summarise or display.",
}

DEPARTMENT_CONTEXT = {
    "Engineering":          "Engineers work with code (GitHub), configs, PRs, tests, and databases. They do NOT typically send external email.",
    "Customer Success":     "CSMs pull customer usage data and email customers directly. They use Salesforce for account data. They do NOT write code or access credentials.",
    "Data and Analytics":   "Analysts query databases and produce reports. Some reports go to external stakeholders via email. They do NOT write code.",
    "Security":             "Security reads credential files, IAM policies, runs diagnostic scripts, emails external auditors. Has both database and code_execute access.",
    "Finance":              "Finance reads sensitive financial files, queries databases, emails vendors and auditors externally. Does NOT access code or GitHub.",
    "Legal and Compliance": "Legal reviews uploaded contracts and policy docs, emails external law firms. Does NOT access databases or code.",
}


def load_or_create_sample():
    if Path(SAMPLE_FILE).exists():
        print(f"Found existing {SAMPLE_FILE} — loading it.")
        return json.loads(Path(SAMPLE_FILE).read_text())

    if not Path(DATASET_FILE).exists():
        print(f"ERROR: {DATASET_FILE} not found. Run 'make split' first.")
        exit(1)

    data = json.loads(Path(DATASET_FILE).read_text())
    sample = random.sample(data, min(SAMPLE_SIZE, len(data)))
    Path(SAMPLE_FILE).write_text(json.dumps(sample, indent=2))
    print(f"Created {SAMPLE_FILE} with {len(sample)} records.")
    return sample


def load_results():
    if Path(OUTPUT_FILE).exists():
        return json.loads(Path(OUTPUT_FILE).read_text())
    return {}


def save_results(results):
    Path(OUTPUT_FILE).write_text(json.dumps(results, indent=2))


def already_validated(record_id, results):
    return record_id in results


def ask_permissions(record, index, total):
    rid = record["id"]
    dept = record["department"]
    prompt = record["prompt"]
    ceiling = constants.DEPARTMENT_CEILINGS.get(dept, set())

    print("\n" + "=" * 70)
    print(f"  Record {index}/{total}  |  ID: {rid}  |  Department: {dept}")
    print("=" * 70)

    dept_note = DEPARTMENT_CONTEXT.get(dept, "")
    if dept_note:
        print(f"\n  DEPARTMENT CONTEXT: {dept_note}")

    print(f"\n  TASK:\n  \"{prompt}\"\n")
    print("  LABELLING RULES:")
    print("  - Only grant a tool if the task CANNOT be completed without it")
    print("  - When uncertain, deny")
    print("  - Role context informs plausibility but the TASK TEXT determines permissions\n")

    permissions = {}

    for tool in TOOLS:
        # Skip tools outside the department ceiling — they're always false
        if tool not in ceiling:
            permissions[tool] = False
            continue

        tier = constants.TOOL_TIERS[tool]
        guidance = TOOL_GUIDANCE[tool]
        while True:
            answer = input(f"  [T{tier}] {tool}\n  Guidance: {guidance}\n  Grant? (y/n): ").strip().lower()
            if answer in ("y", "n", "yes", "no"):
                permissions[tool] = answer in ("y", "yes")
                break
            print("  Please enter y or n.")
        print()

    sensitivity = ""
    while sensitivity not in ("low", "medium", "high"):
        sensitivity = input("  Sensitivity tier (low / medium / high): ").strip().lower()

    return {
        "id": rid,
        "department": dept,
        "prompt": prompt,
        "human_sensitivity": sensitivity.upper(),
        "human_permissions": permissions,
    }


def main():
    sample = load_or_create_sample()
    results = load_results()

    total = len(sample)
    remaining = [r for r in sample if not already_validated(r["id"], results)]

    if not remaining:
        print(f"\nAll {total} records already validated. Results in {OUTPUT_FILE}.")
        return

    done = total - len(remaining)
    print(f"\nProgress: {done}/{total} done. {len(remaining)} remaining.")
    print("Press Ctrl+C at any time — progress is saved after each record.\n")

    try:
        for i, record in enumerate(remaining, start=done + 1):
            result = ask_permissions(record, i, total)
            results[result["id"]] = result
            save_results(results)
            print(f"  ✓ Saved. ({i}/{total} complete)\n")

    except KeyboardInterrupt:
        print(f"\n\nInterrupted. Progress saved — {len(results)}/{total} complete.")
        return

    print(f"\nDone. All {total} records validated. Results in {OUTPUT_FILE}.")

    # Summary
    from collections import Counter
    dept_counts = Counter(v["department"] for v in results.values())
    print("\nBy department:")
    for dept, count in sorted(dept_counts.items()):
        print(f"  {dept}: {count}")


if __name__ == "__main__":
    main()
