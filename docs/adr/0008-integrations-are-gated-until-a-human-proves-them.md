---
status: accepted
---
# External integrations are gated by default and ungated only by human proof

Decided by the owner on 2026-08-27. Every integration module is a fence path and beads needing a live provider are created deferred; a provider is ungated only after a person wires it, proves it live on the target and files a wiring record, with the fence narrowed in the same PR. The part that breaks (an undocumented payload, the wrong data source) is exactly the part a development machine cannot verify: Actual Budget shipped a correct read of the wrong source, and Libby cost three rounds of guessing. Source: `docs/policies/INTEGRATIONS.md`, memory note `integration-ungating-policy`. Re-gate on any schema, endpoint or auth change until re-proven.
