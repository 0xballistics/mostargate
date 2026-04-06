import json
import random
from collections import defaultdict
from pathlib import Path

from .. import constants

DATASET_FILE = "dataset/dataset.json"
TRAIN_FILE = "dataset/train.json"
TEST_FILE = "dataset/test.json"

TEST_RATIO = 100 / constants.DATA_SIZE  # 100 test records from 600 total


def split():
    if not Path(DATASET_FILE).exists():
        print(f"ERROR: {DATASET_FILE} not found. Run the generation pipeline first.")
        exit(1)

    data = json.loads(Path(DATASET_FILE).read_text())

    # Group by department for stratified split
    by_dept = defaultdict(list)
    for r in data:
        by_dept[r["department"]].append(r)

    train, test = [], []
    for dept, records in by_dept.items():
        random.shuffle(records)
        n_test = round(len(records) * TEST_RATIO)
        test.extend(records[:n_test])
        train.extend(records[n_test:])

    Path(TRAIN_FILE).write_text(json.dumps(train, indent=2))
    Path(TEST_FILE).write_text(json.dumps(test, indent=2))

    print(f"Total:    {len(data)}")
    print(f"Train:    {len(train)} → {TRAIN_FILE}")
    print(f"Test:     {len(test)} → {TEST_FILE}")
    print("\nPer department:")
    for dept in sorted(by_dept):
        n = len(by_dept[dept])
        n_test = round(n * TEST_RATIO)
        print(f"  {dept}: {n - n_test} train / {n_test} test")


if __name__ == "__main__":
    split()
