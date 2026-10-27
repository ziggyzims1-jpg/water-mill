#!/usr/bin/env python3
"""Union-merge one .beads/issues.jsonl into another, by issue id.

Used by the beads-sync workflow: a cloud session can only push its own
claude/* branch, so bead changes made there travel as issues.jsonl commits on
that branch and this merges them into main.

Rules: ids only on the incoming side are added; ids on both sides keep the
record with the later `updated_at` (a tie keeps the base record); nothing is
ever deleted; a line that is not a JSON object with a string `id` refuses the
whole merge. Idempotent: merging the same input twice changes nothing. A
missing BASE is empty, not an error: on the first sync after `bd init` ran on a
claude/* branch, main has no issues.jsonl yet, and the merge creates it.

    beads_merge.py BASE.jsonl INCOMING.jsonl [-o OUT.jsonl]

Prints the merged ids that changed to stderr; exit 0 whether or not anything
changed (the caller diffs), exit 2 on a malformed line.
"""
import argparse
import json
import os
import sys


class MalformedLine(ValueError):
    pass


def parse(text, label):
    """Return [(id, raw_line, record)] in file order; refuse bad lines."""
    out = []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except ValueError as e:
            raise MalformedLine(f"{label}:{n}: not valid JSON ({e})") from e
        if not isinstance(rec, dict) or not isinstance(rec.get("id"), str) or not rec["id"]:
            raise MalformedLine(f"{label}:{n}: not an object with a string id")
        out.append((rec["id"], line, rec))
    return out


def merge(base_text, incoming_text):
    """Return (merged_text, changed_ids)."""
    base = parse(base_text, "base")
    incoming = parse(incoming_text, "incoming")
    lines = {}
    recs = {}
    order = []
    for rid, line, rec in base:
        if rid not in recs:
            order.append(rid)
        lines[rid], recs[rid] = line, rec
    changed = []
    for rid, line, rec in incoming:
        if rid not in recs:
            order.append(rid)
            lines[rid], recs[rid] = line, rec
            changed.append(rid)
        elif str(rec.get("updated_at") or "") > str(recs[rid].get("updated_at") or ""):
            lines[rid], recs[rid] = line, rec
            changed.append(rid)
    text = "".join(lines[r] + "\n" for r in order)
    return text, changed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base")
    ap.add_argument("incoming")
    ap.add_argument("-o", "--out", help="write here (default: overwrite BASE)")
    args = ap.parse_args(argv)
    try:
        with open(args.base, encoding="utf-8") as f:
            base_text = f.read()
    except FileNotFoundError:
        base_text = ""
    with open(args.incoming, encoding="utf-8") as f:
        incoming_text = f.read()
    try:
        text, changed = merge(base_text, incoming_text)
    except MalformedLine as e:
        print(f"beads_merge: refused: {e}", file=sys.stderr)
        return 2
    out = args.out or args.base
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print("beads_merge: changed ids: " + (" ".join(changed) or "(none)"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
