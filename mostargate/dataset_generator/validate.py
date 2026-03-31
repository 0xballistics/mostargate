import json
from pathlib import Path
from collections import Counter

TOOLS = [
    "file_read_standard", "file_read_sensitive", "file_read_uploaded",
    "write_file", "code_search", "code_execute", "pull_request_create",
    "internal_search", "database_query", "ticket_create",
    "send_message", "send_email_external", "http_request",
]

VALID_DEPTS = {
    "Engineering", "Customer Success", "Data and Analytics",
    "Security", "Finance", "Legal and Compliance",
}

data = json.loads(Path("dataset.json").read_text())
errors = []
warnings = []

for r in data:
    rid = r.get("id", "UNKNOWN")

    # Required fields
    for field in ("id", "department", "prompt", "sensitivity", "permissions"):
        if field not in r:
            errors.append(f"{rid}: missing field '{field}'")

    # All 13 tools present
    perms = r.get("permissions", {})
    for tool in TOOLS:
        if tool not in perms:
            errors.append(f"{rid}: missing tool '{tool}'")

    # Valid sensitivity
    if r.get("sensitivity") not in ("LOW", "MEDIUM", "HIGH"):
        errors.append(f"{rid}: invalid sensitivity '{r.get('sensitivity')}'")

    # Valid department
    if r.get("department") not in VALID_DEPTS:
        errors.append(f"{rid}: unknown department '{r.get('department')}'")

    # Sanity: finance/legal shouldn't have code_execute
    dept = r.get("department", "")
    if dept in ("Finance", "Legal and Compliance"):
        if perms.get("code_execute"):
            warnings.append(f"{rid}: {dept} granted code_execute — check")

    # Sanity: engineering shouldn't have send_email_external often
    if dept == "Engineering" and perms.get("send_email_external"):
        warnings.append(f"{rid}: Engineering granted send_email_external — check")

print(f"Records:  {len(data)}")
print(f"Errors:   {len(errors)}")
print(f"Warnings: {len(warnings)}")

if errors:
    print("\nERRORS:")
    for e in errors[:20]:
        print(f"  {e}")

if warnings:
    print("\nWARNINGS (review manually):")
    for w in warnings[:20]:
        print(f"  {w}")

# Distribution check
dept_counts = Counter(r.get("department") for r in data)
print("\nDepartment distribution:")
for dept in sorted(VALID_DEPTS):
    expected = {"Engineering": 125, "Customer Success": 100,
                "Data and Analytics": 75, "Security": 75,
                "Finance": 75, "Legal and Compliance": 50}[dept]
    actual = dept_counts.get(dept, 0)
    status = "✓" if actual == expected else "✗"
    print(f"  {status} {dept}: {actual} (expected {expected})")