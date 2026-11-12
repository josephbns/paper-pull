"""Import local reviewer decisions and apply explicit identity merges."""

import csv
import json
from pathlib import Path

from pubmon.diff import canonical_state
from pubmon.models import Work
from pubmon.store import Store


def _merge(store: Store, source: str, target: str, stamp: str) -> None:
    first_seen = min(store.get_work(source)["first_seen"], store.get_work(target)["first_seen"])
    old = store.get_work_state(target) or store.get_work_state(source)
    store.merge_works(source, target)
    versions = [
        Work(**json.loads(row["normalized_json"]))
        for row in store.list_source_records(target)
        if row["normalized_json"]
    ]
    if not versions:
        return
    state = canonical_state(versions, old)
    store.upsert_work(
        target,
        title=state["title"],
        year=state["year"],
        venue=state.get("venue"),
        type=state["type"],
        status=state["status"],
        ibm_confirmed=state["ibm_confirmed"],
        best_confidence=state["confidence"],
        first_seen=first_seen,
        last_changed=stamp,
    )
    store.save_work_state(target, state)


def import_decisions(path: Path, store: Store, *, decided_at: str) -> dict:
    """Apply valid rows independently; invalid rows cannot alter any database tables."""
    counts = {"imported": 0, "invalid": 0, "blank": 0, "errors": []}
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"work_key", "decision", "reviewer_note"} <= set(reader.fieldnames or []):
            raise ValueError("Reviewed CSV needs work_key, decision and reviewer_note headers")
        for number, row in enumerate(reader, 2):
            decision = (row.get("decision") or "").strip()
            if not decision:
                counts["blank"] += 1
                continue
            try:
                with store.transaction():
                    _apply(
                        store, row["work_key"], decision, row.get("reviewer_note") or "", decided_at
                    )
                counts["imported"] += 1
            except ValueError as exc:
                counts["invalid"] += 1
                counts["errors"].append({"row": number, "reason": str(exc)})
    return counts


def _apply(store: Store, key: str, decision: str, note: str, stamp: str) -> None:
    source = store.canonical_key(key)
    if store.get_work(source) is None:
        raise ValueError("Unknown reviewed work")
    if decision.startswith("merge:"):
        target = store.canonical_key(decision.removeprefix("merge:"))
        if target == source and key != source:
            return  # Re-import of an already applied merge using the former source key.
        store.store_decision(source, "merge:" + target, decided_at=stamp, note=note)
        _merge(store, source, target, stamp)
    else:
        store.store_decision(source, decision, decided_at=stamp, note=note)
