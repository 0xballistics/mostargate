"""
Classifier data plumbing.

Loads labelled records from JSON, builds a multi-label binary matrix in the
permission order defined by `constants.TOOLS`, and tokenises prompts for the
transformer encoder.
"""
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from .. import constants

PERMISSIONS: list[str] = list(constants.TOOLS.keys())


def load_records(path: str | Path) -> list[dict]:
    """Load a JSON list of labelled records (dataset/train.json or test.json)."""
    return json.loads(Path(path).read_text())


def build_label_matrix(records: Sequence[dict]) -> np.ndarray:
    """Multi-label binary matrix with shape (n_records, 15), float32.

    Column j corresponds to PERMISSIONS[j]. Float so it slots directly into
    BCEWithLogitsLoss without an explicit cast downstream.
    """
    matrix = np.zeros((len(records), len(PERMISSIONS)), dtype=np.float32)
    for i, record in enumerate(records):
        perms = record["permissions"]
        for j, name in enumerate(PERMISSIONS):
            # `.get` defaults missing keys to False — 3/500 train records are
            # missing one permission key each (LLM-generation artefact); the
            # semantic for a missing key is "not granted".
            if perms.get(name, False):
                matrix[i, j] = 1.0
    return matrix


def tokenize(records: Sequence[dict], tokenizer, max_len: int = 256) -> dict:
    """Tokenise prompts. Tokenizer is passed in, not constructed here.

    Default max_len = 256: empirical max prompt length across the 500 training
    records is 105 tokens (p95 = 85). 256 leaves comfortable headroom while
    cutting attention compute ~4× vs DeBERTa-v3's native 512 cap.

    Returns a dict with input_ids and attention_mask as lists. Dynamic padding
    is left to the HF data collator at training time — we don't pad here.
    """
    prompts = [r["prompt"] for r in records]
    enc = tokenizer(prompts, truncation=True, max_length=max_len)
    return {
        "input_ids": enc["input_ids"],
        "attention_mask": enc["attention_mask"],
    }
