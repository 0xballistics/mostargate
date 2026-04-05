import json
import random
from pathlib import Path

DATASET_FILE = "dataset/dataset.json"
SAMPLE_FILE = "dataset/validation_sample.json"
OUTPUT_FILE = "dataset/validation_results.json"
SAMPLE_SIZE = 60

TOOLS = [
    "file_read_standard",
    "file_read_sensitive",
    "file_read_uploaded",
    "write_file",
    "code_search",
    "code_execute",
    "pull_request_create",
    "internal_search",
    "database_query",
    "ticket_create",
    "send_message",
    "send_email_external",
    "http_request",
]

TOOL_GUIDANCE = {
    "file_read_standard":  "Non-sensitive files only — docs, READMEs, templates, plain text. No credentials, no PII.",
    "file_read_sensitive": "Only if task involves credentials, API keys, salary data, PII, or proprietary source code. NOT for general internal docs.",
    "file_read_uploaded":  "Only if the user explicitly uploaded a file in this session and the task requires reading it.",
    "write_file":          "Only if the task explicitly requires producing a saved output document, report, export, or draft. Not for summarising or displaying.",
    "code_search":         "Only if the task requires searching or navigating a codebase — symbol lookup, grep, semantic search. Read-only.",
    "code_execute":        "Only if the task requires running code, computation, or tests. NOT for reading or searching code.",
    "pull_request_create": "Only if the task explicitly requires submitting a code change for review.",
    "internal_search":     "Only if the task requires querying Confluence, internal wiki, Salesforce, or knowledge base.",
    "database_query":      "Only if the task requires structured data retrieval from PostgreSQL or Snowflake. NOT for file-based data.",
    "ticket_create":       "Only if the task explicitly requires logging a bug, task, or work item in Jira.",
    "send_message":        "Only if the task explicitly requires sending an internal Slack or Teams message.",
    "send_email_external": "Only if the task explicitly addresses an external recipient outside the company.",
    "http_request":        "Only if the task explicitly requires fetching live data from an external URL. NOT for internal searches.",
}

DEPARTMENT_CONTEXT = {
    "Engineering":          "Engineers work with code, configs, credentials, PRs, tests. They do NOT typically send external email.",
    "Customer Success":     "CSMs pull customer usage data and email customers directly. They do NOT write code or access raw credentials.",
    "Data and Analytics":   "Analysts query databases and produce reports. Some reports go to external stakeholders via email.",
    "Security":             "Security team reads credential files and IAM policies, runs diagnostic scripts, emails external auditors.",
    "Finance":              "Finance reads sensitive financial files, queries financial databases, emails vendors and auditors externally.",
    "Legal and Compliance": "Legal reads uploaded contracts and policy docs, emails external law firms. Does NOT access databases or code.",
}


def load_or_create_sample():
    if Path(SAMPLE_FILE).exists():
        print(f"Found existing {SAMPLE_FILE} — loading it.")
        return json.loads(Path(SAMPLE_FILE).read_text())

    if not Path(DATASET_FILE).exists():
        print(f"ERROR: {DATASET_FILE} not found. Run the dataset generation pipeline first.")
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
    print("  - Role context informs plausibility, but the TASK text determines permissions\n")

    permissions = {}

    for tool in TOOLS:
        guidance = TOOL_GUIDANCE[tool]
        while True:
            answer = input(f"  {tool}\n  Guidance: {guidance}\n  Grant? (y/n): ").strip().lower()
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