# Subscription and pricing model

The plan for charging clients whose software runs as Water Mill cells.
Drafted 2026-08-27, after cell 1b (ZIM Consulting) was specified. Numbers are
starting points for the nonprofit market, not settled decisions — the open
questions at the bottom are the owner's to answer.

## What is actually being sold

The business is not "software development by the hour" and not pure SaaS. It
is three distinct things, and the pricing should mirror them because they
have completely different cost structures:

1. **Discovery and build-out** (one-time). Turning a client's notes into
   specified beads, stamping the cell, wiring and proving each integration
   (`docs/policies/INTEGRATIONS.md`). This is almost entirely human time —
   the scarce input — plus a burst of mill construction. Front-loaded cost,
   so front-loaded price.
2. **Operations** (recurring). Hosting, backups and restore drills,
   monitoring, security updates, integration re-verification when a provider
   changes. Low marginal cost per cell, but real liability — this is what a
   subscription is *for*.
3. **Ongoing development** (recurring or metered). New features run through
   the mill. Marginal cost per feature is genuinely low (tokens + review
   time), which is the business's whole edge — the pricing should make that
   edge visible to the client instead of hiding it in an hourly rate.

### Cost floor per cell (know this before quoting)

| Cost | Estimate | Notes |
|------|----------|-------|
| Hosting | $10–50/mo | A VPS or small cloud instance per cell; a Pi-class box amortizes to almost nothing but has no SLA |
| Backups/monitoring | ~$5/mo | Off-site storage + uptime checks |
| Tokens per landed bead | ~$5–20 | Implement + adversarial review + land; varies with bead size |
| Human review/landing time | The dominant cost | Supervised batches, fence judgment calls, integration proofs |
| Billing software fees | 0.5–5% of revenue | See the comparison below |

A cell that is merely *kept alive* costs perhaps $30–60/mo hard cost plus a
little attention. Everything above that in the subscription is paying for
the liability (it breaks at 2 AM, it's yours) and the margin.

## Pricing models considered

**A. Pure subscription (flat SaaS tiers).** Simple to sell, predictable
revenue. But it buries the build-out cost: a client whose discovery and
integration wiring took three weeks pays the same first month as one who
took three days. Wrong for work this front-loaded.

**B. Time and materials.** Prices the human hours accurately and the mill's
edge not at all — the client pays less as the factory gets better, which is
backwards. Also the worst cash-flow shape: no recurring base.

**C. Setup fee + tiered subscription (recommended).** The setup fee prices
the human-heavy build-out; the subscription prices operations plus a defined
amount of ongoing development, metered in **change requests** (roughly: one
bead-sized, well-specified feature or fix). Change requests are the honest
unit here — they map one-to-one to what the mill actually does, they make
the cheap marginal cost a selling point ("your tier includes four changes a
month"), and they cap scope without an hourly-rate argument.

## Recommended structure

### One-time: build-out fee

| | Scope | Price |
|---|---|---|
| **Cell setup** | Discovery, bead specification, stamp from template, branding, deploy, first integrations proven | **$3,500–7,500** depending on integration count |
| **Per additional integration** | Wire + prove live + wiring record (the ungating procedure) | **$350–600 each** |

Integrations are priced individually on purpose: they are the human-labor
center of the build (accounts, OAuth apps, ToS, live proof), the client can
see exactly what each one costs, and deferring one defers its fee.

### Recurring: subscription tiers (per cell, per month)

| Tier | For | Includes | Price |
|------|-----|----------|-------|
| **Care** | A finished app that just needs to stay up | Hosting, nightly backups + restore drills, monitoring, security updates, integration re-verification | **$149/mo** |
| **Standard** | An app that keeps evolving modestly | Care + **4 change requests/mo** + priority fixes for anything broken | **$399/mo** |
| **Partner** | A client whose ops you are effectively running | Care + **12 change requests/mo** + new-integration wiring at half rate + quarterly roadmap session | **$899/mo** |

- Change requests don't roll over more than one month (prevents banked
  backlogs landing all at once).
- Extra change requests: **$75–100 each** on any tier.
- Annual prepay: **2 months free** (~17%). Nonprofits with grant cycles
  often *prefer* an annual invoice they can put on a grant budget — offer it
  prominently.
- Nonprofit pricing is the list price. Don't advertise a "nonprofit
  discount" off an inflated number; this market compares notes.

### Pilot pricing (ZIM / cell 1b)

First client, and the calibration case for the whole model: charge **Care
tier + a discounted build-out** (e.g. $2,000) in exchange for a testimonial,
a case study, and tolerance for process wrinkles. Track actual hours and
tokens against it — this is where the numbers above get corrected.

## Billing automation

What should be automated from day one: hosted checkout/payment page,
recurring invoicing, **ACH debit** (nonprofits pay by ACH and check far more
than by card, and card fees on a $399 subscription are real money), failed-
payment retries (dunning), receipts, and revenue reporting. What should
*not* be automated yet: metered per-change-request billing — count change
requests by hand on the monthly invoice until the volume justifies wiring
usage-based billing.

### Options

| Software | Fees (verify before committing) | Fit |
|----------|-------------------------------|-----|
| **Stripe Billing** (recommended) | ~2.9% + 30¢ card; **ACH 0.8% capped at $5**; Billing fee ~0.5–0.8% on recurring | The default for a reason: hosted checkout + customer portal, dunning, tax via Stripe Tax, invoicing, and a real API — subscription status could surface in each cell's admin dashboard later (that would itself be a gated integration with a wiring record) |
| **Paddle** | ~5% + 50¢ | Merchant of record — they handle sales tax/VAT and are the seller. Simplest compliance story, highest fee. Overkill while every client is US-domestic |
| **Lemon Squeezy** | ~5% + 50¢ | Also MoR, simpler than Paddle, now Stripe-owned. Same trade as Paddle |
| **Zoho Billing** | Flat ~$0–59/mo + gateway fees | Cheap flat pricing, good invoicing; clunkier checkout. Reasonable if invoice-first |
| **Chargebee / Recurly** | Free to ~$0 up to a revenue cap, then % or $250+/mo | Subscription-management layers on top of a gateway. Built for pricing-model complexity this business doesn't have yet |
| **QuickBooks recurring invoices + bill.com** | QBO subscription + ~1% ACH | Worth naming because ZIM already lives in this stack — but it's invoicing, not subscription management: no self-serve checkout, no dunning logic |

**Recommendation: Stripe Billing, invoice-first.** Phase it:

1. **Now (manual-ish):** Stripe invoices sent monthly/annually, ACH debit
   enabled, autopay on. Ten minutes of setup per client, fees near the
   floor, dunning handled.
2. **At ~3–5 cells:** Stripe Products/Prices for the three tiers, hosted
   checkout links, customer portal for card/ACH updates. Still no code.
3. **When it earns it:** wire Stripe's API into a cell or an internal
   dashboard (subscription status, usage) — through the integration
   ungating procedure like any other provider.

Fee reality check at recommended prices: Standard tier at $399/mo by ACH
costs ~$3.19 + Billing fee ≈ **under 2%**. The same by card ≈ **3.5%+**.
Steer clients to ACH; it is also what they prefer.

## Open questions for the owner

- **Positioning:** is the subscription sold as "managed software" (ops
  language) or "your tech team" (retainer language)? Same numbers, very
  different sales conversation.
- **Change-request definition:** the tiers depend on a crisp definition a
  client can't argue with. Proposal: "one well-specified feature or fix that
  passes review and lands in one PR" — but decide before the first dispute,
  not during it.
- **SLA:** Care implies *some* response-time promise. What is it, and is
  there a paid faster one?
- **Who owns the repo/IP:** cell repos currently live under the owner's
  GitHub. Client ownership vs. license affects what leaving costs them —
  and what the subscription is worth.
- **Price floor test:** would you rather lose the deal than run a cell at
  $99/mo? If yes, Care at $149 is right. If no, add a $99 "hosting only, no
  humans included" tier and mean it.
