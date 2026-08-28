# Integrations: gated by default, ungated by proof

The policy for external integrations across every cell the mill runs.
Decided 2026-08-27 by the owner; each cell carries the operating procedure in
its own `docs/integrations/README.md` (stamped from the cell template).

## Why integrations are different

Everything else the mill builds can be verified by the gate: the code, the
tests, and CI agree or they don't. An integration cannot — its correctness
lives on someone else's server, behind accounts an agent cannot open,
credentials an agent must not hold, and terms of service only a person can
accept. The record so far is unambiguous:

- **Actual Budget**: a confident, correct read of the wrong source (the
  frozen snapshot blob) shipped and looked exactly like success. The schema
  check worked as designed and the feature was still wrong.
- **Libby**: three rounds of hypothesis about a moved endpoint versus thirty
  seconds of watching the real client's network tab. Every field name in an
  undocumented payload is a guess.

Both failures share a shape: the part that breaks is precisely the part that
cannot be verified from a development machine. So the mill does not get to
decide an integration works — a human proof does.

## The default: gated

Two mechanisms, both mechanical (a convention an agent can drift past is not
a gate):

1. **The fence.** `services/integrations/` is listed in the cell's
   `watermill.yaml` fence, so a diff touching a provider module is a fence
   violation and the run is refused, regardless of what the bead said.
2. **Deferred beads.** Beads that require a live provider are created with
   `--defer` (any far date). Water Mill draws work from `bd ready`, and a
   deferred bead never appears there, so the mill cannot claim the work even
   if the fence would have caught the diff.

Skeleton beads — stub clients, mock fixtures, config seams, no credentials
and no network — may stay open. They build the socket, not the wire.

## Ungating a provider

The owner's rule: **if a human wires an integration and proves that it
works, that integration is ungated — because there is now a record of how to
wire it so that it is functional.** Concretely, one PR containing all three:

1. **Wired, by a human.** Accounts created, OAuth apps registered, ToS
   accepted, credentials placed (env vars or write-only config keys, listed
   in the cell's sensitive-keys set). An agent never performs this step and
   never sees the values.
2. **Proven live, on the target.** A real round-trip against the provider
   from the machine that will run it — not a unit test, not "the code is
   right". Record what was sent, what came back, and the date. This is the
   step Actual and Libby both showed cannot be skipped or simulated.
3. **The wiring record filed.** `docs/integrations/<provider>.md` in the
   cell, from the template: credentials location, config keys, endpoints,
   the proof, failure modes, what is still mocked, re-verification triggers.
   The record is the load-bearing artifact — it is what lets a mill agent
   later work on the integration from facts rather than plausible guesses.

The same PR narrows the fence (the format has no negations, so the
directory entry is replaced by one entry per still-gated module — and from
then on every **new** provider module must be added to the fence in the
change that creates it) and un-defers that provider's beads. After that, the
mill may build on the provider like any other code: the gate still runs, the
wiring record is the ground truth, and mock fixtures still back the tests —
the proof authorized the integration, it did not put credentials in CI.

## Re-gating

An ungated provider goes back on the fence — and its open beads back to
deferred — when the ground truth stops being true: a schema error from the
sync, a moved endpoint, an auth flow that stops working, or a provider API
version bump named in the record's re-verification triggers. A human
re-proves it and updates the record's `verified` date. A wiring record
describes the provider as it was on that date, not forever.

## What this policy deliberately does not allow

- Ungating on "the stub is well-tested" — tests against fixtures prove the
  socket, never the wire.
- Ungating a *category* ("all read-only providers") — proof is per provider,
  per cell, because the record is per provider, per cell.
- An agent performing the wiring or holding the credentials, even
  supervised. The human doing step 1 is what makes the liability and the
  ToS acceptance real.
