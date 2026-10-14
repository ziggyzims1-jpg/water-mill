#!/usr/bin/env python3
# managed by water-mill (canon/project/scripts/beads_merge.py); edit it there, then run `watermill sync`
"""Union-merge one .beads/issues.jsonl into another, by issue id.

Used by the beads-sync workflow: a cloud session can only push its own
claude/* branch, so bead changes made there travel as issues.jsonl commits on
that branch and this merges them into main.

Rules: ids only on the incoming side are added; ids on both sides keep the
record with the later `updated_at` (a tie keeps the base record); nothing is
ever deleted; a line that is not a JSON object with a string `id` refuses the
whole merge. Idempotent: merging the same input twice changes nothing.

    beads_merge.py BASE.jsonl INCOMING.jsonl [-o OUT.jsonl]

Prints the merged ids that changed to stderr; exit 0 whether or not anything
changed (the caller diffs), exit 2 on a malformed line.
"""
import argparse
import json
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
    with open(args.base, encoding="utf-8") as f:
        base_text = f.read()
    with open(args.incoming, encoding="utf-8") as f:
        incoming_text = f.read()
    try:
        text, changed = merge(base_text, incoming_text)
    except MalformedLine as e:
        print(f"beads_merge: refused: {e}", file=sys.stderr)
        return 2
    with open(args.out or args.base, "w", encoding="utf-8") as f:
        f.write(text)
    print("beads_merge: changed ids: " + (" ".join(changed) or "(none)"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
