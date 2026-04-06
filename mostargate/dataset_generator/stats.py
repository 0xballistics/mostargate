import json
from collections import Counter
from pathlib import Path

from .. import constants

DATASET_FILE = Path("dataset/dataset.json")
STATS_FILE = Path("dataset/stats.txt")

TOOLS = list(constants.TOOLS.keys())
DEPTS = sorted(constants.DEPARTMENT_CEILINGS.keys())
TIERS = {1: "Default Deny", 2: "Grant With Justification", 3: "Default Permit"}


def pct(n: int, total: int) -> str:
    return f"{n / total * 100:.1f}%" if total else "—"


def grant_rate(records: list[dict], tool: str) -> tuple[int, int]:
    n = sum(1 for r in records if r.get("permissions", {}).get(tool))
    return n, len(records)


def build_stats(data: list[dict]) -> str:
    lines: list[str] = []
    n = len(data)

    by_dept: dict[str, list[dict]] = {d: [] for d in DEPTS}
    by_sens: dict[str, list[dict]] = {"LOW": [], "MEDIUM": [], "HIGH": []}
    for r in data:
        by_dept.setdefault(r["department"], []).append(r)
        by_sens.setdefault(r["sensitivity"], []).append(r)

    # ── Overview ──────────────────────────────────────────────────────────────
    lines.append("=" * 60)
    lines.append("DATASET STATS")
    lines.append("=" * 60)
    lines.append(f"File:    {DATASET_FILE}")
    lines.append(f"Records: {n}\n")

    # ── Department distribution ───────────────────────────────────────────────
    lines.append("── Department distribution ──")
    for dept in DEPTS:
        recs = by_dept.get(dept, [])
        lines.append(f"  {dept:<25} {len(recs):>4}  ({pct(len(recs), n)})")
    lines.append("")

    # ── Sensitivity distribution ──────────────────────────────────────────────
    lines.append("── Sensitivity distribution ──")
    for sens in ("LOW", "MEDIUM", "HIGH"):
        recs = by_sens.get(sens, [])
        lines.append(f"  {sens:<8} {len(recs):>4}  ({pct(len(recs), n)})")
    lines.append("")

    # ── Sensitivity × Department cross-tab ────────────────────────────────────
    lines.append("── Sensitivity × Department ──")
    header = f"  {'':25}" + "".join(f"  {s:<6}" for s in ("LOW", "MED", "HIGH"))
    lines.append(header)
    for dept in DEPTS:
        recs = by_dept.get(dept, [])
        counts = Counter(r["sensitivity"] for r in recs)
        row = f"  {dept:<25}" + "".join(
            f"  {counts.get(s, 0):<6}" for s in ("LOW", "MEDIUM", "HIGH")
        )
        lines.append(row)
    lines.append("")

    # ── Overall permission grant rates ────────────────────────────────────────
    lines.append("── Permission grant rates (overall) ──")
    lines.append(f"  {'Tool':<25} {'T':>2}  {'Granted':>7}  {'Rate':>6}")
    lines.append("  " + "-" * 44)
    for tool in TOOLS:
        tier = constants.TOOL_TIERS[tool]
        granted, total = grant_rate(data, tool)
        lines.append(f"  {tool:<25} {tier:>2}  {granted:>4}/{total:<4}  {pct(granted, total):>6}")
    avg_perms = sum(
        sum(1 for v in r.get("permissions", {}).values() if v) for r in data
    ) / n
    lines.append(f"\n  Average permissions per record: {avg_perms:.2f}")
    lines.append("")

    # ── Grant rates by department ─────────────────────────────────────────────
    lines.append("── Permission grant rates by department ──")
    for dept in DEPTS:
        recs = by_dept.get(dept, [])
        if not recs:
            continue
        ceiling = constants.DEPARTMENT_CEILINGS[dept]
        lines.append(f"\n  {dept} (n={len(recs)})")
        for tool in TOOLS:
            if tool not in ceiling:
                continue  # skip tools outside ceiling — always 0
            tier = constants.TOOL_TIERS[tool]
            granted, total = grant_rate(recs, tool)
            lines.append(f"    T{tier} {tool:<25} {granted:>3}/{total:<3}  ({pct(granted, total)})")
    lines.append("")

    # ── Grant rates by sensitivity ────────────────────────────────────────────
    lines.append("── Permission grant rates by sensitivity ──")
    for sens in ("LOW", "MEDIUM", "HIGH"):
        recs = by_sens.get(sens, [])
        if not recs:
            continue
        lines.append(f"\n  {sens} (n={len(recs)})")
        for tool in TOOLS:
            tier = constants.TOOL_TIERS[tool]
            granted, total = grant_rate(recs, tool)
            if granted == 0:
                continue  # skip zeros for readability
            lines.append(f"    T{tier} {tool:<25} {granted:>3}/{total:<3}  ({pct(granted, total)})")
    lines.append("")

    # ── Tier coverage ─────────────────────────────────────────────────────────
    lines.append("── Tier coverage ──")
    for tier_num, tier_name in TIERS.items():
        tier_tools = [t for t, v in constants.TOOL_TIERS.items() if v == tier_num]
        any_granted = sum(
            1 for r in data
            if any(r.get("permissions", {}).get(t) for t in tier_tools)
        )
        lines.append(f"  T{tier_num} {tier_name:<30} records with ≥1 grant: {any_granted}/{n} ({pct(any_granted, n)})")

    return "\n".join(lines)


def main() -> None:
    if not DATASET_FILE.exists():
        print(f"ERROR: {DATASET_FILE} not found. Run 'make merge' first.")
        raise SystemExit(1)

    data = json.loads(DATASET_FILE.read_text())
    report = build_stats(data)

    STATS_FILE.write_text(report)
    print(f"Stats written to {STATS_FILE}")


if __name__ == "__main__":
    main()
