import json
from datetime import datetime
from pathlib import Path
from collections import Counter

from .. import constants

TOOLS = list(constants.TOOLS.keys())
VALID_DEPTS = set(constants.DEPARTMENT_CEILINGS.keys())

DATASET_FILE = Path("dataset/dataset.json")
LOG_FILE = Path("dataset/validation.log")

# Expected counts: 30 batches × per-batch allocation (5/4/3/3/3/2)
EXPECTED_DEPT_COUNTS = {
    "Engineering":          5 * (constants.DATA_SIZE // constants.BATCH_SIZE),
    "Customer Success":     4 * (constants.DATA_SIZE // constants.BATCH_SIZE),
    "Data and Analytics":   3 * (constants.DATA_SIZE // constants.BATCH_SIZE),
    "Security":             3 * (constants.DATA_SIZE // constants.BATCH_SIZE),
    "Finance":              3 * (constants.DATA_SIZE // constants.BATCH_SIZE),
    "Legal and Compliance": 2 * (constants.DATA_SIZE // constants.BATCH_SIZE),
}


def validate(data: list[dict]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for r in data:
        rid = r.get("id", "UNKNOWN")

        # Required fields
        for field in ("id", "department", "prompt", "sensitivity", "permissions"):
            if field not in r:
                errors.append(f"{rid}: missing field '{field}'")

        # All 15 tools present as keys
        perms = r.get("permissions", {})
        for tool in TOOLS:
            if tool not in perms:
                errors.append(f"{rid}: missing tool '{tool}'")

        # Valid sensitivity
        if r.get("sensitivity") not in ("LOW", "MEDIUM", "HIGH"):
            errors.append(f"{rid}: invalid sensitivity '{r.get('sensitivity')}'")

        # Valid department
        dept = r.get("department", "")
        if dept not in VALID_DEPTS:
            errors.append(f"{rid}: unknown department '{dept}'")
            continue

        # Permissions don't exceed department ceiling
        ceiling = constants.DEPARTMENT_CEILINGS[dept]
        for tool, granted in perms.items():
            if granted and tool not in ceiling:
                warnings.append(f"{rid}: {dept} granted '{tool}' — outside department ceiling")

        # Combination prohibition: database_read + email_send_external
        if perms.get("database_read") and perms.get("email_send_external"):
            if dept in ("Engineering", "Legal and Compliance"):
                warnings.append(f"{rid}: {dept} has database_read + email_send_external — policy-prohibited combo")

        # Sanity: Legal
        if dept == "Legal and Compliance":
            if perms.get("database_read"):
                warnings.append(f"{rid}: Legal granted database_read — check")
            if perms.get("github_read"):
                warnings.append(f"{rid}: Legal granted github_read — outside ceiling")

        # Sanity: Finance
        if dept == "Finance":
            if perms.get("github_read") or perms.get("code_execute"):
                warnings.append(f"{rid}: Finance granted github_read/code_execute — outside ceiling")

    return errors, warnings


def build_report(data: list[dict], errors: list[str], warnings: list[str]) -> str:
    dept_counts = Counter(r.get("department") for r in data)
    lines: list[str] = []

    lines.append(f"Validation run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Dataset:  {DATASET_FILE}")
    lines.append(f"Records:  {len(data)}")
    lines.append(f"Errors:   {len(errors)}")
    lines.append(f"Warnings: {len(warnings)}")

    lines.append("\n--- ERRORS ---")
    lines.extend(f"  {e}" for e in errors) if errors else lines.append("  None")

    lines.append("\n--- WARNINGS ---")
    lines.extend(f"  {w}" for w in warnings) if warnings else lines.append("  None")

    lines.append("\n--- DEPARTMENT DISTRIBUTION ---")
    for dept in sorted(VALID_DEPTS):
        expected = EXPECTED_DEPT_COUNTS[dept]
        actual = dept_counts.get(dept, 0)
        status = "OK" if actual == expected else "MISMATCH"
        lines.append(f"  [{status}] {dept}: {actual} (expected {expected})")

    lines.append("\n--- PERMISSION GRANT RATES ---")
    for tool in TOOLS:
        tier = constants.TOOL_TIERS[tool]
        count = sum(1 for r in data if r.get("permissions", {}).get(tool))
        rate = count / len(data) * 100 if data else 0
        lines.append(f"  T{tier} {tool}: {count}/{len(data)} ({rate:.1f}%)")

    return "\n".join(lines)


def main() -> None:
    if not DATASET_FILE.exists():
        print(f"ERROR: {DATASET_FILE} not found. Run 'make merge' first.")
        raise SystemExit(1)

    data = json.loads(DATASET_FILE.read_text())
    errors, warnings = validate(data)
    report = build_report(data, errors, warnings)

    LOG_FILE.write_text(report)

    print(f"Records:  {len(data)}")
    print(f"Errors:   {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    print(f"\nFull report written to {LOG_FILE}")


if __name__ == "__main__":
    main()
