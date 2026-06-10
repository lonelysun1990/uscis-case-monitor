"""Pure logic to parse case payloads and compute changes between runs."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChangeReport:
    receipt_number: str
    form_type: str
    form_name: str
    updated_at_timestamp: str
    changed: bool
    new_events: list[dict] = field(default_factory=list)
    new_notices: list[dict] = field(default_factory=list)


def _data(payload: dict) -> dict:
    return payload.get("data", {})


def get_updated_at(payload: dict) -> str:
    return _data(payload).get("updatedAtTimestamp", "")


def new_events(current: dict, previous: dict | None) -> list[dict]:
    cur = _data(current).get("events", [])
    if previous is None:
        return list(cur)
    prev_ids = {e.get("eventId") for e in _data(previous).get("events", [])}
    return [e for e in cur if e.get("eventId") not in prev_ids]


def new_notices(current: dict, previous: dict | None) -> list[dict]:
    cur = _data(current).get("notices", [])
    if previous is None:
        return list(cur)
    prev_ids = {n.get("letterId") for n in _data(previous).get("notices", [])}
    return [n for n in cur if n.get("letterId") not in prev_ids]


def summarize(current: dict, previous: dict | None) -> ChangeReport:
    """Build a ChangeReport. A first run (previous is None) is reported as
    unchanged so the caller can save a baseline without a false alert."""
    data = _data(current)
    cur_updated = get_updated_at(current)
    changed = previous is not None and cur_updated != get_updated_at(previous)
    return ChangeReport(
        receipt_number=data.get("receiptNumber", ""),
        form_type=data.get("formType", ""),
        form_name=data.get("formName", ""),
        updated_at_timestamp=cur_updated,
        changed=changed,
        new_events=new_events(current, previous) if changed else [],
        new_notices=new_notices(current, previous) if changed else [],
    )
