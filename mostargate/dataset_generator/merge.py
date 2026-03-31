from asyncio import constants
import json
from pathlib import Path

from .. import constants
from collections import Counter

all_records = []

for batch in range(1, constants.DATA_SIZE // constants.BATCH_SIZE + 1):
    infile = f"dataset/pass2_batch_{batch:02d}.json"
    if not Path(infile).exists():
        print(f"Missing: {infile}")
        continue
    records = json.loads(Path(infile).read_text())
    all_records.extend(records)

Path("dataset/dataset.json").write_text(json.dumps(all_records, indent=2))

# Summary
dept_counts = Counter(r["department"] for r in all_records)
sensitivity_counts = Counter(r["sensitivity"] for r in all_records)

print(f"\nTotal records: {len(all_records)}")
print("\nBy department:")
for dept, count in sorted(dept_counts.items()):
    print(f"  {dept}: {count}")
print("\nBy sensitivity:")
for s, count in sorted(sensitivity_counts.items()):
    print(f"  {s}: {count}")