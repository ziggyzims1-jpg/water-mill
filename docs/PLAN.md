# The Software Factory: Business and Build Plan

**Version:** 2.1
**Date:** 2026-08-26
**Changes from v2.0:** Reconciled against what has actually been built. Named
Water Mill as the loop runner and fence engine (§10.9, §11 Stage 3, §13);
marked actual roadmap position and the items delivered early or skipped (§13);
set a Phase 5 date, which §13.2 required and v2.0 did not contain (§13.2);
recorded that none of the seven metrics are instrumented (§14); corrected the
count in §12.
**Changes from v1.0:** Added regulatory landscape (§5), deployment tiers and split-plane architecture (§6), revised unit economics for two-tier pricing (§8), split-plane reference architecture (§10.7), fleet-management metrics (§14), version-skew and data-boundary risks (§15), Appendix D trust-boundary statement.

**Model:** Privately-held agentic software factory producing bespoke automation tooling as a managed subscription product.
**Proving ground:** Life tracker web application.

> **Note:** Nothing in this document is legal advice. Every regulatory and contractual item requires review by qualified counsel before it becomes an obligation.

> **Where things actually are: [STATUS.md](STATUS.md).** This document is the
> plan; that one is the position. **Actual position as of 2026-08-26: Phase 1
> complete, Phase 2 not started, zero nights run.** When the two disagree,
> STATUS.md is right — and the rule is that a change to the position and the
> change to this plan land together, or the plan quietly becomes fiction.

---

## Table of Contents

1. [Business Definition](#1-business-definition)
2. [The Structural Trap and Its Escape](#2-the-structural-trap-and-its-escape)
3. [Two Production Lines](#3-two-production-lines)
4. [The Verification Thesis](#4-the-verification-thesis)
5. [Regulatory Landscape](#5-regulatory-landscape)
6. [Deployment Tiers and the Split Plane](#6-deployment-tiers-and-the-split-plane)
7. [Product Ladder](#7-product-ladder)
8. [Unit Economics](#8-unit-economics)
9. [The Attention Ceiling](#9-the-attention-ceiling)
10. [Factory Architecture](#10-factory-architecture)
11. [The Seeding Machine](#11-the-seeding-machine)
12. [Role of the Life Tracker](#12-role-of-the-life-tracker)
13. [Roadmap](#13-roadmap)
14. [Metrics](#14-metrics)
15. [Risk Register](#15-risk-register)
16. [Kill Criteria](#16-kill-criteria)
17. [Open Decisions](#17-open-decisions)
18. [Appendix A: Fence Registry Starter](#appendix-a-fence-registry-starter)
19. [Appendix B: Contract Clause Checklist](#appendix-b-contract-clause-checklist)
20. [Appendix C: Rung-0 Audit Instrument](#appendix-c-rung-0-audit-instrument)
21. [Appendix D: Trust Boundary Statement Template](#appendix-d-trust-boundary-statement-template)
22. [Sources](#sources)

---

## 1. Business Definition

### 1.1 What the business is

A privately-held agentic software factory that produces **bespoke automation tooling delivered as a managed subscription**. The factory is capital equipment: never sold, never licensed, never demoed.

Each customer engagement has two economic halves:

| Half | Type | Produces |
|---|---|---|
| **Build** | One-time, fee-bearing | A working tool specific to that customer's workflow |
| **Operate** | Recurring subscription | Maintenance, adaptation, support, hosting, inference |

### 1.2 What the business is not

| Model | Why this isn't it |
|---|---|
| Agency | Agencies hand over and walk away. Here, maintenance is the product. |
| SaaS | SaaS ships one artifact to everyone. Here, each cell is customer-specific. |
| Harness vendor | The factory is not for sale. Selling it invites the transplant problem (§2.3). |

The category is **managed bespoke tooling**. Historically this has poor economics. It is viable now for one reason: the marginal cost of *maintaining* software has collapsed, and maintenance is the highest-verifiability work class that exists (§4).

### 1.3 Deployment tiers

The product ships in two tiers. Tier assignment happens at Rung 0, never mid-build. Full treatment in §6.

| | **Managed** | **Sovereign** |
|---|---|---|
| Cell runtime | Operator platform | Customer VPC / subscription / project |
| Record content | Processed by operator | **Never crosses operator trust boundary** |
| Inference | Operator's provider relationship, absorbed | Customer's cloud model service, customer-billed |
| Seeding cost | Baseline | ~2x baseline |
| Target buyer | Unregulated, low data sensitivity | Regulated, data-residency constrained |
| Margin shape | Higher, consumption absorbed | Higher service fee, lower consumption exposure |

### 1.4 Positioning

Customer-facing framing:

> "You don't hire us, and you don't buy software. You subscribe to a tool that doesn't exist yet. We build it, run it, and keep it working."

For Sovereign-tier prospects, lead with the trust boundary rather than the certification:

> "Record content never crosses our trust boundary. We receive metadata, hashes, and counters. A compromise of our platform yields no customer data."

When asked to license or purchase the factory:

> "We don't license the production line. Holding it is how we keep your price where it is."

### 1.5 Comparative economics

| Dimension | Agency | SaaS | This model |
|---|---|---|---|
| Revenue shape | Lumpy, project-based | Recurring | Build fee + recurring |
| Marginal cost | High (labor) | Near-zero | Low but real (inference) |
| Customer fit | Exact | Generic | Exact |
| Maintenance burden | Customer's | Yours, one codebase | **Yours, N codebases** |
| Scaling limit | Headcount | Sales capacity | **Operator attention** |

The bolded row is the entire risk of the business. §2, §3, and §6.6 exist to neutralize it.

---

## 2. The Structural Trap and Its Escape

### 2.1 The trap

The **services-to-product treadmill**. Mechanism:

1. Build bespoke deliverable #1, sell it.
2. Build #2, which shares ~20% of #1.
3. Build #3, which shares ~15%.
4. By customer #10, you maintain ten divergent codebases.

Result: revenue resembles SaaS, cost structure resembles a consultancy, margin is flat, and the operator cannot take a vacation. Agentic tooling does **not** fix this by itself — it makes each individual maintenance task cheap while leaving *coordination* cost untouched, and coordination is what consumes the operator.

### 2.2 The escape: bespoke surface, shared substrate

```
        ┌─────────────────────────────────────────────┐
        │  SUBSTRATE  (one codebase, operator-owned)  │
        │                                             │
        │  auth · scheduling · connector framework    │
        │  job queue · observability · secrets mgmt   │
        │  audit log · retry/backoff · rate limiting  │
        │  budget governor · billing · fence engine   │
        │  data-boundary scrubber · tenant routing    │
        └─────────────────────────────────────────────┘
                            ▲
                            │ inherited by
        ┌───────────┬───────┴───────┬───────────┐
        │  Cell A   │    Cell B     │  Cell C   │  ← thin, declarative
        │ config +  │   config +    │ config +  │
        │ bounded   │   bounded     │ bounded   │
        │ logic     │   logic       │ logic     │
        └───────────┴───────────────┴───────────┘
```

**Cell:** what a customer buys — their workflow, their integrations, their rules, their interface. A cell must be *thin*: configuration plus a bounded amount of custom logic.

**Substrate:** everything hard, shared, and dangerous. One codebase. Fixed once, inherited by all.

### 2.3 The Rule of Two

> **The second time any two cells need the same capability, that capability moves down into the substrate.**

Not the third time. The second. This must be enforced mechanically — see the `substrate coverage` metric in §14.

Related principle from Yegge's field reports: agentic harnesses are inherently bespoke and grow around a specific domain like ivy on a wall, resistant to transplant. This plan accepts that claim for the *harness* and routes around it by never selling the harness. But the claim reasserts itself operationally: **every new customer is a new wall, and the ivy still has to grow.** The seeding machine (§11) exists to make that growth fast and cheap.

### 2.4 Consequences

- **Contract requirement:** the MSA must grant unrestricted rights to reuse patterns, components, and learnings across customers, while the customer owns their data and business logic. Without this clause, the Rule of Two is a breach of contract. See Appendix B.
- **Sales requirement:** refuse work that will not sit on the substrate. Either decline, or price as a one-time build at a significant premium with **no maintenance obligation attached**.

---

## 3. Two Production Lines

Building and maintaining are different production problems requiring different machinery, models, autonomy levels, and economics.

| Dimension | Build Line | Maintenance Line |
|---|---|---|
| Trigger | New customer signed | Continuous: upstream API change, CVE, customer request, alert |
| Work shape | Novel, ambiguous, high-context | Repetitive, bounded, well-specified |
| Verification available | Weak initially (no tests exist yet) | **Strong** (regression suite exists) |
| Autonomy achievable | Low — operator heavily involved | **High — must approach full autonomy** |
| Model tier | Expensive for design/review | Cheap for nearly everything |
| Duration | 2–6 weeks, then complete | Indefinite |
| Load scales with | New sales (controllable) | **Total cells under management (monotone increasing)** |

### 3.1 Why maintenance is the priority

- At **2 human-hours/cell/month**: ceiling of roughly 40 cells, burnout around 25.
- At **6 human-minutes/cell/month**: ceiling in the hundreds.

Maintenance is also where agents are strongest: a shipped cell with a regression suite is Tier-1 work (§4). The tests exist, behavior is defined, changes are small and provable.

**Directive: design and prove the maintenance line before there is anything to maintain.** Build it against the life tracker. If it cannot autonomously keep one application healthy for 30 consecutive days, it cannot keep twenty cells healthy.

### 3.2 Standing maintenance roles

Unattended agents woken by schedulers. Operating principle: **schedulers watch, models act.**

| Role | Function | Autonomy |
|---|---|---|
| **Watchtower** | Detects upstream API/schema drift across all cells | Files beads autonomously |
| **Medic** | CVE and dependency patching | Auto-PR, merges on green |
| **Auditor** | Nightly invariant and data-integrity check per cell | Read-only; files P0 on mismatch |
| **Falsifier** | Adversarial review — sole instruction is to find how a change is wrong | Blocks merge on finding |
| **Boundary Falsifier** | Adversarial search for record content in outbound telemetry (§6.4) | Blocks release on finding |
| **Herald** | Monthly per-customer activity report | Drafts; operator approves |
| **Quartermaster** | Fleet version tracking, upgrade scheduling, conformance results | Files beads; operator approves rollouts |

The Herald is not cosmetic. In a maintenance subscription, the primary churn driver is invisible value. A monthly report enumerating automated fixes is the product's most important customer-facing artifact.

---

## 4. The Verification Thesis

Full autonomy is not a property of a system. It is a property of each **decision class**, and it is granted by **verifiability**, not by model capability.

> Where a machine can prove the work is correct, autonomy is available today.
> Where it cannot, autonomy is unavailable at any model quality.
> Therefore the central engineering program is: **convert unverifiable work into verifiable work.**

### 4.1 The four tiers

| Tier | Verification mechanism | Autonomy granted |
|---|---|---|
| **1. Mechanically provable** | Tests, types, property tests, golden files, invariant checks, round-trip proofs, benchmarks | **Full.** Merge on green, no human |
| **2. Statistically checkable** | Eval suites, LLM-as-judge with rubric, regression baselines, canary metrics | **High.** Autonomous with sampled human audit |
| **3. Adversarially checkable** | A second agent whose only job is to falsify the first's work | **Medium.** Autonomous to a staging gate |
| **4. Taste, judgment, consequence** | Human | **None.** Escalate always |

Yegge's agents independently converged on a name for Tier 3 — "falsifiers" — alongside a broader enforcement vocabulary of fences, ratchets, governors, tripwires, latches, and gates. That convergence suggests the taxonomy is real rather than invented.

### 4.2 Operational implications

- **Intake triage:** every unit of work is tiered before a worker sees it. Tier-4 items are either escalated or **re-specified until they drop a tier**.
- **Tier-lowering is core engineering work, not overhead.** Budget explicit time for building provers, not only features. This is the highest-leverage activity in the company.
- **The Falsifier is cheap and underrated.** A low-cost agent instructed solely to find how a change is wrong catches a meaningful fraction of Tier-2 failures for a rounding error in spend.

### 4.3 Calibration on current model judgment

Yegge, operating at roughly $122k/month equivalent token spend across ~21 Claude Max accounts with a ~600k-line governance apparatus, reports that unattended overnight operation still produces at least one significant bad decision per night, and characterizes current model judgment as roughly grade-school level. He documents an incident in which an agent shipped an unplanned release that broke downstream consumers.

**Conclusion: do not sell "fully autonomous" as a contractual term.** Sell *autonomously produced, verifiably gated*.

---

## 5. Regulatory Landscape

### 5.1 Three separate exposures

"Is my industry regulated?" is the wrong unit of analysis. There are three distinct exposures with different remedies.

| Exposure | Source | What it constrains | Remedy |
|---|---|---|---|
| **A. Flow-down** | Customer's regulator reaching you as vendor/subprocessor | Where cells run, who touches data, contractual promises, audit rights over you | **Sovereign tier (§6)** |
| **B. Change control** | Customer's validated or audited change-management regime | **Maintenance-line autonomy** | Audit export as validation evidence (§10.6); cell scoping |
| **C. Direct AI regulation** | Laws regulating you as provider/deployer of AI systems | Documentation, transparency, human oversight, record-keeping | Cell scoping out of consequential decisions |

**Exposure B is the one that breaks the business model.** If every change to a cell requires a validation package and a human signature, the autonomous maintenance line becomes manual, human-minutes per cell explodes, and the business reverts to an agency.

**Qualification question for every prospect:** *"When you change a piece of internal software, what has to happen before it goes live?"* The answer prices the engagement more accurately than anything else asked. Recorded in Rung 0 as **change-control burden**, measured in human sign-offs per change.

### 5.2 Scope is the primary lever

Regulatory exposure attaches to **what the cell touches**, not to the customer's industry. A cell automating facilities ticket routing at a hospital touches no PHI.

| Technique | Effect |
|---|---|
| **Tokenize / de-identify at the boundary** | Cell processes surrogates; regulated data never enters logs, prompts, or model calls |
| **Metadata-only cells** | Automate the workflow around the record without reading the record |
| **Customer-side execution of the regulated step** | Cell prepares and stages; a customer system commits |
| **Read-only + recommend** | Cell never writes to the system of record |
| **Segmented cells** | Split one workflow into a regulated cell (heavy controls, low autonomy) and an unregulated cell (full autonomy) |

An in-scope and an out-of-scope cell serving the same workflow can differ 3–5x in build cost and 2–3x in monthly. **Quote both.**

### 5.3 Sector survey

Read the **Autonomy ceiling** column first — it maps directly to unit economics.

#### Healthcare (providers, payers, health tech)

| | |
|---|---|
| Regimes | HIPAA Privacy/Security/Breach, HITECH; state health-privacy laws (WA My Health My Data, CT, NV) often broader than HIPAA; 42 CFR Part 2 for substance-use records; state retention laws |
| Flow-down | Business Associate status. Signed BAA. Downstream BAAs for subcontractors **including the model provider**. Direct liability |
| Change control | Moderate — internal IT change management, not statutory validation |
| Autonomy ceiling | **High** if scoped out of PHI; medium if in PHI |
| Solo feasibility | Workable |

Gating technical requirement: a compliant inference path — BAA with the model provider, zero data retention, no training on inputs, audit logging of every PHI access.

**Entry cells:** prior-auth packet assembly, referral routing, credentialing workflow, denial tracking, scheduling optimization, supply reorder. **Avoid:** anything construable as clinical decision support.

#### Life sciences / pharma / biotech (GxP)

| | |
|---|---|
| Regimes | FDA 21 CFR Part 11, GxP (GMP/GLP/GCP), EU Annex 11, computer system validation, increasingly Computer Software Assurance (CSA) risk-based approach |
| Flow-down | Supplier qualification, audit rights, sometimes on-site audit of the operator |
| Change control | **Severe.** Change control, impact assessment, requalification, documented approval per change |
| Autonomy ceiling | **Low in GxP scope**, high outside it |
| Solo feasibility | Hard, high value |

Exposure B in its purest form. The wedge is **non-GxP work at GxP companies**: procurement, vendor onboarding, internal reporting, lab scheduling, non-controlled document routing. If pursuing GxP scope, the audit export (§10.6) is the product — position it as automated validation evidence.

#### Medical devices / SaMD

FDA QSR/ISO 13485, IEC 62304, design history file, Predetermined Change Control Plans for AI. **Autonomy ceiling: very low. Solo feasibility: closed.** The real risk is entering by accident via scope drift. Mechanical fence required on cell specifications (Appendix A).

#### Financial services — banks, credit unions, lenders

| | |
|---|---|
| Regimes | GLBA Safeguards Rule; FFIEC/OCC/FRB third-party risk guidance; SR 11-7 model risk; FCRA and ECOA/Reg B adverse action if credit decisions touched; state money transmission; EU DORA |
| Flow-down | **Heavy.** Third-party risk assessment, financial due diligence on the operator entity, right-to-audit, BC/DR and exit plans, concentration risk |
| Autonomy ceiling | **Medium** — high for back-office, low near decisioning |
| Solo feasibility | **Bus-factor problem is acute** |

Go downmarket first: community banks, credit unions, fintechs, RIAs. DORA imposes register-of-information and exit-strategy obligations on ICT third parties for EU financial customers.

#### Insurance

NAIC model bulletin on AI use (adopted in some form by a majority of states), state DOI oversight, rate/underwriting rules, unfair discrimination statutes. **Autonomy ceiling: medium.** Claims intake triage, document extraction, broker onboarding, filing assembly. Avoid rating factors.

#### Government / public sector

FedRAMP, StateRAMP, CJIS, IRS Pub 1075, procurement law. **Federal effectively closed to a solo operator.** State/local reachable; standard path is subcontracting under an authorized prime.

#### Defense / aerospace

CMMC Level 2 (NIST SP 800-171), ITAR/EAR export controls, DFARS. **Closed initially.** ITAR interacts badly with commercial model APIs: technical data access by a foreign person, including via cloud service or support, is a violation.

#### Critical infrastructure / energy

NERC CIP, TSA security directives, CISA sector requirements. **Autonomy ceiling near zero inside the OT boundary**; the IT side is normal enterprise work.

#### Education

FERPA, COPPA, state student-privacy laws. Moderate burden, thin budgets. **Autonomy ceiling high** once scoped away from student records.

#### Legal

Bar ethics rules on confidentiality, unauthorized practice, privilege preservation. Privilege-waiver risk pushes toward Sovereign tier and no-retention inference.

### 5.4 Cross-cutting regimes

**Privacy.** GDPR/UK GDPR: processor status, DPA, subprocessor disclosure and flow-down, Art. 32 measures, transfer mechanisms, DPIA support. US state comprehensive privacy laws (~20 states) impose service-provider terms and, in several, obligations around automated decision-making and profiling opt-outs.

**EU AI Act — current timeline.** Regulation (EU) 2026/1744, the Digital Omnibus on AI, was published in the Official Journal on 24 July 2026 and entered into force 27 July 2026, six days before the original high-risk deadline.

| Date | Obligation |
|---|---|
| 2 August 2026 | Article 50 transparency obligations apply (**not deferred**); Article 4 AI-literacy duty (**not deferred**) |
| 2 December 2026 | Article 50(2) transparency extends to legacy systems; new prohibited practices apply |
| 2 August 2027 | Member States to establish national AI regulatory sandboxes |
| **2 December 2027** | High-risk obligations apply to Annex III (standalone) systems — deferred from 2 Aug 2026 |
| **2 August 2028** | High-risk obligations apply to Annex I (embedded) systems |

Annex III high-risk categories relevant to cell scoping: employment/HR decisions, credit and essential-services access, education, insurance pricing, critical infrastructure, law enforcement, migration. A grandfathering rule exempts systems placed on the market before the applicable dates **unless substantially modified afterward** — unlikely to help a business built on continuous autonomous modification.

**US state AI law.** Colorado's original comprehensive AI Act was repealed and replaced by SB 26-189, signed 14 May 2026, effective 1 January 2027 subject to AG rulemaking. It replaces the "high-risk AI system" and algorithmic-discrimination framework with a narrower regime targeting **automated decision-making technology that processes personal data to materially influence a consequential decision**, shifting toward consumer disclosures, post-adverse-outcome explanations, correction rights, and meaningful human review. Notable details: the original law's conditional exemptions for certain federally regulated entities were **eliminated**; enforcement is AG-only with no private right of action; liability is allocated by fault between developers and deployers and **certain indemnification clauses are voided**. Colorado separately enacted a Chatbot Safety Act (HB 26-1263), signed 1 July 2026, effective 1 January 2027, with draft implementing rules filed 11 August 2026.

Also cross-cutting on the HR side: NYC Local Law 144 bias audits for automated employment decision tools, Illinois AI video-interview law, and a growing set of comparable state statutes.

**Security certifications (contractual, not statutory).** SOC 2 Type II is the near-universal enterprise gate; ISO 27001 in Europe; PCI DSS if card data is near a cell; HITRUST for some healthcare buyers.

> **SOC 2 Type II is the highest-ROI compliance investment** — it unlocks buyers across every sector simultaneously. The factory's provenance record covers change management, access control, and logging, three of the heaviest evidence areas. Start the observation window early.

### 5.5 Sector ranking for a solo operator

| Sector | Burden | Autonomy ceiling | Budget | Bus-factor tolerance | Verdict |
|---|---|---|---|---|---|
| Professional services, logistics, mid-market SaaS, manufacturing (non-safety) | Low | High | Medium | High | **Start here** |
| Education | Medium | High | Low | High | Practice ground, thin margins |
| Insurance (back-office) | Medium | Medium-high | High | Medium | **Strong second** |
| Healthcare (PHI-adjacent, scoped) | Medium-high | High if scoped | High | Medium | **Best risk-adjusted target** |
| Financial services (community/fintech) | High | Medium | High | **Low** | Viable with SOC 2 + insurance |
| Life sciences (non-GxP scope) | Medium | High | Very high | Medium | **Highest value if scopable** |
| Life sciences (GxP scope) | Very high | Low | Very high | Low | Year 2+, with audit-export product |
| Government / defense / medical device / critical OT | Extreme | Very low | High | Very low | Closed |

**Recommendation:** healthcare with rigorously de-identified or metadata-only cells, or life sciences targeting explicitly non-GxP workflows. Both have large budgets, obvious manual-work surfaces, and buyers who already understand and pay for vendor compliance overhead.

**Sequencing:** run the first three Rung-0 audits in a low-regulation sector (Phase 4) to calibrate the factory and pricing without a security questionnaire in the loop. Move up-market at cell 3 or 4.

---

## 6. Deployment Tiers and the Split Plane

### 6.1 The distinction that matters

"Software on my platform, data on theirs" describes two very different architectures. Only one reduces regulatory exposure.

| | **A. Remote data, local processing** | **B. Split plane (Sovereign tier)** |
|---|---|---|
| Database location | Customer infra | Customer infra |
| Agent runtime | **Operator platform** | Customer infra |
| Records read into memory | **Operator platform** | Customer infra |
| Prompt construction | **Operator platform** | Customer infra |
| Regulatory position | Full processing scope | Substantially reduced |

**Architecture A buys almost nothing.** Exposure follows **access and processing**, not storage. HIPAA's Business Associate definition covers creating, receiving, maintaining, or transmitting PHI on behalf of a covered entity, and "maintaining" has been read to include the ability to access. GDPR processor status attaches to processing on behalf of a controller; remote access is processing. The conduit exception is narrow and does not cover a system that acts on content.

**Target architecture B: the data plane runs inside the customer's trust boundary, and the control plane never sees record content.**

### 6.2 The five leak paths

Even in architecture B, these are where record content escapes without explicit design against them.

| # | Leak path | Mechanism | Mitigation |
|---|---|---|---|
| 1 | **Inference** | Prompts containing records reach a model endpoint via operator credentials | §6.3 |
| 2 | **Telemetry** | Stack traces, error payloads, request/response logging, APM traces embed records | Structured logging only; field-level allowlist; substrate scrubber; aggregation data-plane-side, counters/hashes only outbound |
| 3 | **Support access** | Debugging a broken cell means looking at data | Break-glass: time-boxed, customer-approved, fully logged, customer-initiated. **No standing access** |
| 4 | **Derived artifacts** | Caches, queues, **dead-letter queues**, temp files, model context caches, backups of any of these | All data-plane-resident. DLQs are the most commonly missed finding |
| 5 | **Configuration** | Column names, business rules, sample values in cell config may themselves be sensitive | Treat cell config as customer data; control plane stores hash + version pointer only |

### 6.3 The inference boundary

| Option | Data leaves tenant? | Quality | Inference billed to | Viability |
|---|---|---|---|---|
| Operator API key called from customer VPC | **Yes** | Best | Operator | Breaks the boundary; sometimes acceptable with zero-retention + BAA provider, but a negotiation |
| **Customer cloud model service in customer account** (Bedrock / Vertex / Azure) | **No** | Near-parity | **Customer** | **Clean answer** |
| Self-hosted open-weight model in customer VPC | No | Materially worse for agentic work | Customer | Fallback for most restrictive buyers |
| De-identify at boundary, then call out | Surrogates only | Full | Operator | Excellent where workflow tolerates it |

**Conflict with v1.0:** the plan specified absorbing token cost as positioning. The architecturally correct answer for regulated buyers bills inference to the customer's cloud account, which reintroduces a second vendor line item.

**Resolution — adopted:** change the promise per tier.

- **Managed tier:** operator absorbs all consumption. Single line item preserved.
- **Sovereign tier:** inference runs in the customer's cloud on the customer's account. Operator manages the budget, enforces ceilings, and reports consumption. Service fee is higher; consumption exposure is lower.

Rejected alternative: absorbing customer-side inference as a credit. It creates variable COGS the operator cannot directly meter or cap, defeating the budget governor and reproducing the margin inversion in §8.3.

### 6.4 Boundary enforcement

- **Boundary Falsifier** (§3.2): an adversarial agent whose sole instruction is to find record content in outbound telemetry. Blocks release on finding.
- **Egress policy as a mechanical fence:** network policy preventing content egress from the data plane, verified continuously, not asserted.
- **Conformance suite:** the data plane runs an environment self-test on install and nightly, reporting pass/fail to the control plane.

### 6.5 What the split plane buys

- **Data residency and sovereignty** — solved structurally, including EU/UK.
- **Procurement velocity** — exits the "where does our data go" review path. Often the difference between a 3-month and a 9-month cycle.
- **Breach blast radius** — the operator stops being a honeypot holding N customers' regulated data. Materially changes E&O posture and premium.
- **Shorter subprocessor chain** — fewer downstream BAAs/DPAs to negotiate and disclose.
- **Cloud-marketplace distribution** — BYOC deployments list naturally on AWS/Azure/GCP marketplaces, letting customers spend committed cloud budget. Underrated distribution channel for a solo operator.
- **Partial regime avoidance** — not holding certain data classes can narrow authorization scope. Verify per regime; partial, not total.

### 6.6 What it costs — and it attacks the key metric

| Cost | Mechanism |
|---|---|
| **Reduced observability** | Debugging systems whose logs cannot be fully read. Every incident is slower |
| **Fleet heterogeneity** | N environments, N cloud configs, N network policies, N IAM models. Environmental failures that never occur in the lab |
| **Version skew** | Customers upgrade on their schedule. Three substrate versions in production by cell 8 |
| **Upgrade coordination** | Every substrate change becomes a fleet rollout with customer-side change windows |
| **Seeding cost** | ~2x — installing infrastructure, not just configuring a cell |
| **Support latency** | Break-glass approval loops turn 10-minute fixes into 2-day fixes |

Version skew and upgrade coordination compound. In Managed tier the substrate is fixed once. In Sovereign tier it is fixed once and then **deployed N times, each with customer-side approval** — a linear-with-customers cost, precisely the agency dynamic §2 exists to prevent.

**Mandatory mitigations, all substrate components:**

- **Auto-updating data plane by default**, with a contractual maintenance window. Opt-out only for the most conservative tier. MSA term, not a per-upgrade negotiation.
- **Hard version-skew policy:** support N and N-1 only; forced upgrade at N-2. Contractual.
- **Remote diagnostics without data access:** structured telemetry carrying shape, timing, cardinality, error class, and hashes — never content. Invest disproportionately; this is what keeps incident MTTR from exploding.
- **Conformance test suite** run on install and nightly, reported centrally.
- **Treat the data-plane installer as a product** with its own tests, run against all three test beds (§12.2).

### 6.7 Does the split plane unlock the sectors?

| Sector | Sovereign tier sufficient? | Remaining blocker |
|---|---|---|
| Healthcare | **Largely yes** | BAA still required (access ≠ zero exposure), but scope drops sharply |
| Life sciences, non-GxP | **Yes** | Supplier qualification |
| Life sciences, GxP scope | **No** | Change control, not data location |
| Financial services | **Helps substantially** | Third-party risk review of operator entity; bus factor; SOC 2 |
| Insurance | **Yes** | Decisioning scope questions |
| Education | Yes, often unnecessary | Budget |
| Government federal | No | Authorization applies to the offering, not just data location |
| Defense / ITAR | Partially | Export control follows access by persons, including via support |
| Medical device / SaMD | No | Product regulation, unrelated to hosting |
| Critical infrastructure OT | Helps | Segmentation and change control dominate |

**Pattern:** the Sovereign tier addresses **exposure A** (flow-down, data location). It does essentially nothing for **exposure B** (change control) or **exposure C** (direct AI regulation). The combination that unlocks the hardest sectors is Sovereign tier **plus** machine-generated validation evidence **plus** scoping out of consequential decisions.

### 6.8 Sequencing — build the seam, defer the implementation

| Phase | Action |
|---|---|
| **0–3** | Establish seams as if Sovereign existed: per-tenant model credential routing, no record content in telemetry by construction, content-addressed audit index, secrets abstraction, config-as-customer-data. Near-zero cost if done now |
| **4** | Run the life tracker with the control/data split **against the operator's own accounts**, with a network policy mechanically preventing content egress. A real test, not a thought experiment |
| **5** | Ship cell one **Managed** unless the customer demands otherwise. Faster, cheaper to seed, and the cost data is needed |
| **6** | Build full Sovereign when a specific signed deal requires it and is priced to fund it |

**Failure mode to guard against:** building a sophisticated split-plane architecture for hypothetical regulated customers not yet met — a variant of risk #1. **Let a signed deal pull Sovereign into existence.** The seams cost nothing now; the implementation costs months.

---

## 7. Product Ladder

### Rung 0 — Workflow Audit
**Duration:** 3–5 days. **Pricing:** real engagement fee, credited against a subsequent build.

Deliverables:
- Map of manual workflows with hours consumed per week
- **Verifiability score** per workflow (§4.1)
- **Change-control burden** per workflow (§5.1)
- **Tier assignment** — Managed or Sovereign (§6)
- **Inference termination point** determination (§6.3)
- Ranked build backlog with effort estimates
- Explicit disqualification of poor-fit workflows

*Function:* this is the entire sales process. It also disqualifies bad-fit customers before six weeks are committed. The verifiability score is the primary differentiator.

### Rung 1 — The Build
**Duration:** 2–6 weeks Managed, 4–10 weeks Sovereign. **Pricing:** one-time fee covering seeding cost plus margin. Sovereign priced at ~2x Managed seeding.

One cell, delivered to production, against acceptance criteria defined in advance.

*Critical:* not a loss leader. A loss-leading build attached to an under-scoped subscription is the fastest route to negative-margin customers.

### Rung 2 — The Subscription
**Pricing:** monthly, per cell, tier-differentiated. **This is the business.**

Covers: hosting (Managed) or fleet management (Sovereign), inference (Managed only), upstream-change adaptation, security patching, uptime monitoring, bug fixes, a **bounded** allowance of small enhancements, and the monthly report.

### Rung 3 — Expansion
Additional cells for an existing customer at a reduced build fee — substrate configured, integrations built, institutional knowledge extracted, and in Sovereign tier the data plane already installed. **Best economics in the model**, and the primary growth vector. The marginal Sovereign cell is dramatically cheaper than the first.

### Ladder rules

- **Never sell a build without an attached subscription.**
- **Rung 0 is mandatory before Rung 1.** No exceptions, including warm referrals.
- **Tier is assigned at Rung 0 and does not change mid-build.**

---

## 8. Unit Economics

### 8.1 Per-cell monthly model, by tier

```
MANAGED
  Subscription revenue                    R_m
  − inference cost (maintenance line)     operator-borne; hard cap required
  − hosting / infrastructure              operator-borne, predictable
  − support cost (operator time)          price in minutes
  − substrate amortization                spread across all cells
  = contribution margin

SOVEREIGN
  Subscription revenue                    R_s  (higher service component)
  − inference cost                        CUSTOMER-BORNE (not operator COGS)
  − hosting / infrastructure              customer-borne
  − support cost (operator time)          HIGHER — reduced observability,
                                          break-glass latency
  − fleet management cost                 NEW — upgrade coordination,
                                          version skew, conformance triage
  − substrate amortization                spread across all cells
  = contribution margin
```

Sovereign trades **variable consumption risk** for **fixed operational overhead**. It is not automatically more or less profitable; it is differently shaped. The overhead is largely a function of fleet discipline (§6.6), which is controllable.

### 8.2 The three solvency controls

1. **Hard budget governor per cell.** Not a monitor — a fence. Daily and monthly ceilings enforced at the loop runner. On breach, the loop halts and files an escalation. **In Sovereign tier the governor must enforce against spend it does not bill:** the data-plane agent reports consumption metadata; enforcement is local, policy is central. Must exist before the first paid cell.
2. **Contractual scope boundary.** "Maintenance" is enumerated: upstream adaptation, security patching, defect correction, and up to N hours/month of enhancement. All else is a change order.
3. **Metered overage, disclosed up front.** Managed tier: volume-driven cost passes through above a stated threshold. Sovereign tier: consumption is visible to the customer directly, but the *service* component still needs an enhancement-hours ceiling.

### 8.3 The margin-inversion failure mode

Ten subscriptions sold at a price set before real maintenance cost was known. By month eight, contribution margin per cell is negative, operator time is consumed by support, and existing contracts cannot be repriced. **This kills more businesses of this shape than any technical failure.**

Mitigations:
- **Do not price before measuring.** Run the life tracker under the maintenance line for 90 days and measure token cost/month, human-minutes/month, and incidents/month. Those three numbers *are* the Managed pricing model. **The 90-day clock starts at the first successful night, not at the plan's week 1** — a coupling v2.0 did not state and which now sets the schedule: to have a price by the Phase 5 date of 2026-12-14 (§13.2), night one must happen by **~2026-09-15**. Every week night one slips, the first priced engagement slips with it, one week for one week. That, and not any feature, is the critical path. Sovereign pricing additionally requires fleet-management cost, which cannot be measured until cell 2 or 3.
- **First three customers are design partners** with an explicit written re-pricing clause at month six.
- **Do not price Sovereign the same as Managed.** If both tiers carry the same price, Sovereign customers are subsidized by Managed ones and it will not surface until margin analysis at cell 8.

---

## 9. The Attention Ceiling

The binding constraint is not tokens or compute. It is **the operator's daily human decision budget**, and it does not scale. Yegge reports the same wall with vastly greater resources: he caps his crew at 18 agents because more overwhelms his ability to track progress, and states plainly that in the limit he is the bottleneck.

### 9.1 Architecture: exception-based management

**One interface.** A single conversational agent the operator talks to, which dispatches to everything else. Yegge designates one remote-control session as the sole human-facing surface, reachable from a phone.

**A ranked docket, not a feed.** The system ranks its own escalations. Yegge's dashboard surfaces the three loudest pending decisions with a full-docket expansion.

### 9.2 The escalation budget

Set explicitly: **N human decisions per day.** Start at 10.

A cell generating 15 escalations/day is **unprofitable regardless of contract value**. The remedy is engineering (lower its verification tier), not more operator hours.

### 9.3 Escalation format

Standardized, four fields:

1. What happened
2. What the agent recommends
3. What it needs from the operator
4. Cost/consequence of each option

A well-formatted escalation is a 40-second decision. A badly formatted one is a 20-minute investigation. Substrate component.

### 9.4 Hidden consumers

- **Support email.** Route through a single intake agent that drafts responses for one-click approval. Count support minutes in the per-cell human-minutes metric.
- **Break-glass approvals (Sovereign).** Each one is an operator decision plus a customer round trip. Count them.
- **Upgrade rollouts (Sovereign).** Each fleet rollout consumes operator decisions proportional to fleet size unless auto-update is the default.

---

## 10. Factory Architecture

### 10.1 Agent roster (build line)

| Seat | Class | Model tier | Charter |
|---|---|---|---|
| **Coach** | Crew | Expensive | Converts operator intent into specs and implementation beads; reviews all worker diffs |
| **Analyst** | Crew | Expensive | Owns invariants; veto authority on changes to protected surfaces |
| **Trainer** | Crew | Expensive | Owns test corpus and the gate; fixes flakes, expands property tests |
| **Dispatcher** | Script | Cheap/none | Assigns ready beads, tracks claims, restarts stuck workers |
| **Bench** (1–N) | Fleet | Cheap | Headless implementers, own repo clones, never directly addressed |

Pipeline per unit of work: **expensive model designs → cheap model implements → expensive model reviews.**

### 10.2 Knowledge stratification

| Store | Contents | Lifetime | Reaches a session via |
|---|---|---|---|
| `brain/` | Strategy, doctrine, decisions and rationale, postmortems | Months–years | Pulled on demand |
| `doc/` | How subsystem X works | Life of the subsystem | Pulled by whoever works on X |
| Beads issues | Units of work; spec beads carry full implementation detail | Until closed | Loaded only by the claimant |
| `bd remember` | ≤1-paragraph operational facts and gotchas | Until falsified | Pushed into every session on prime |
| Skills | Procedures for recurring task types | Life of the task type | Auto-loaded on task match |

### 10.3 Work graph

**Beads** (`bd`) as the work graph and provenance ledger: a distributed graph issue tracker for coding agents, backed by Dolt, with hash-based IDs avoiding merge collisions across multi-agent workflows, atomic claiming, dependency-aware ready-queue detection, and semantic compaction of closed work. Core loop: `bd ready` → `bd update --claim` → work → gate → `bd close`, with closure releasing blocked dependents.

### 10.4 Substrate seams (portability requirements)

Every point where customers differ must be an interface, established from the first commit.

| Seam | Variation across customers |
|---|---|
| Model provider | Direct API vs. Bedrock vs. Vertex vs. Azure vs. customer gateway |
| **Per-tenant credential routing** | **Sovereign requires tenant A on Bedrock, tenant B on Vertex, tenant C on operator API — same cell code** |
| Token source / budget governor | Operator-billed vs. customer-billed, with remote enforcement |
| VCS host | GitHub, GitLab, Bitbucket, Perforce, Sapling |
| CI / gate runner | Actions, Buildkite, Jenkins, in-house |
| Issue system | Beads default; Jira/GHI bridge for enterprises |
| Chat / intake surface | Slack, Teams, Discord, email |
| Secrets | Customer vault, customer KMS — operator never holds decrypting credentials |
| Deploy target | Customer's existing pipeline, untouched |

**Do not build a configuration UI.** Seams are interfaces, not a settings panel.

### 10.5 Governance and audit layer

**Rule lifecycle (the ratchet):**

```
custom  →  advisory / warning  →  written law  →  mechanical enforcement
```

Escalate one rung per re-violation. For unrecoverable failure modes, skip directly to mechanical enforcement.

**Fence.** Any mechanism that refuses an actor lacking the required credential, state, or paperwork. Not a sandbox and not a wall — a policy-level refusal. The *engine* belongs in the substrate; the *registry* is per-cell. Starter registry in Appendix A.

**Record integrity.** "Never falsify the record" is a standing constitutional rule.

### 10.6 Audit export and split audit

A single command producing, for any date range: every change, its originating bead, its specification, gate results, reviewer, and every fence that fired.

**Split audit (Sovereign tier):**
- **Full audit log with content stays tenant-side.**
- **Control plane holds a content-addressed index** — hashes, timestamps, actor, event type.
- The operator can prove *what happened and when* without holding *what it was*.

This preserves the provenance-evidence product while maintaining the trust boundary, and is the mechanism by which the audit export can be offered into GxP and SOC 2 contexts without becoming a data custodian.

**Market context:** human approval is currently embedded in many companies' audited change-management controls and customer commitments; agentic throughput will force those controls to be rewritten. A worked, evidenced answer to *"what replaces human review in an audited pipeline"* is a currently unoccupied position.

### 10.7 Split-plane reference architecture

```
┌──────────────────────────────────────────────────────────────┐
│  CONTROL PLANE  (operator platform)                          │
│                                                              │
│  • Cell definition registry (versioned, content-hashed)      │
│  • Scheduling / orchestration intent                         │
│  • Fleet health: heartbeats, version, conformance results    │
│  • Escalation queue + ranked docket (metadata only)          │
│  • Audit INDEX: event hashes, timestamps, actors — no content│
│  • Billing, entitlement, budget ceilings (policy)            │
│  • Substrate build + signed artifact distribution            │
│                                                              │
│  Sees: metadata, hashes, counters, error classes             │
│  Never sees: record content, secrets, prompts, logs w/ data  │
└───────────────────────┬──────────────────────────────────────┘
                        │  mTLS, outbound-initiated from tenant
                        │  (no inbound ports on customer side)
┌───────────────────────┴──────────────────────────────────────┐
│  DATA PLANE  (customer VPC / subscription / project)         │
│                                                              │
│  • Agent runtime + loop runner                               │
│  • Connectors to systems of record                           │
│  • Secrets (customer vault, customer KMS, customer keys)     │
│  • Model inference → customer cloud endpoint, customer acct  │
│  • Full logs, traces, caches, queues, DLQs — all resident    │
│  • Regression suite executing against customer data          │
│  • Local fence + budget governor enforcement point           │
│  • Audit LOG (full content) — resident; hashes ship out      │
│  • Conformance self-test (install + nightly)                 │
└──────────────────────────────────────────────────────────────┘
```

Four design rules:

1. **Outbound-only connectivity.** The data plane initiates; the operator never holds inbound access into the customer network. Eliminates most firewall and network-security objections.
2. **Split audit.** Content-bearing log stays tenant-side; control plane holds a content-addressed index.
3. **Customer-held keys.** Customer KMS, customer rotation. The operator never holds a credential that decrypts customer data.
4. **Signed artifacts.** The data plane verifies signatures on substrate updates — also the answer to "how do we know you won't push malicious code."

### 10.9 What exists today: Water Mill

*Added in v2.1. v2.0 described a factory with no orchestrator named, and
scheduled the loop runner in Phase 1 and the fence engine in Phase 3. Both were
built in the same week, in one repository, and the plan did not say so.*

**Water Mill** is the run loop and the fence engine. It claims a task from a
project's queue, hands it to a fresh agent invocation, and then **independently
verifies what reached the repository** — re-running the project's own gate,
checking the diff against a declared fence, checking the tree is clean, checking
the commit names the task. Anything failing is discarded regardless of what the
agent reported. It knows nothing about any project; everything project-specific
arrives through a contract.

| Substrate component (§2.2) | Where it lives now |
|---|---|
| Fence engine | `watermill/contract.py` + `engine.py` — declared paths, checked against staged, unstaged, untracked and committed diffs |
| Fence registry (per-cell) | `watermill.yaml` in the target repo, or a vendored copy under `projects/` |
| Budget governor | `watermill/caps.py` — **reactive, not yet a hard fence.** Checked between tasks, so it overshoots by up to one task. §8.2 requires the hard version before the first paid cell |
| Loop runner | `watermill/engine.py` |
| Provenance ledger | `watermill/ledger.py`, append-only, cross-project |
| Audit export | **Not built.** §10.6 |
| Model-provider seam | **Not built.** The agent command is one contract string; per-tenant credential routing (§10.4) does not exist |

Three deliberate properties, each of them a bug somebody already had:

1. **The fence is enforced, not requested.** A fence written into an agent
   prompt is an instruction. A fence checked against `git diff --name-only` is
   evidence. Only the second survives an agent that misreads its brief.
2. **The runner lives outside the tree it cleans.** A cleanup routine is the
   most dangerous code in the system because it runs on the paths nobody tested.
   A factory in a sibling checkout makes a whole class of self-deletion bug
   structurally impossible.
3. **Refusal and failure are different, with different exit codes.** A refusal
   every night is a configuration problem; a failure every night is a project
   problem. A cron wrapper that cannot tell them apart reports neither.

**The caveat that governs everything downstream: every cap has been proven
against a stub agent.** That tests control flow, not agent behaviour. Water Mill
has never driven a real agent — see §13 and STATUS.md.

### 10.8 Continuity

- **Seats vs. sessions.** A session is one working period. A seat is a named role with persistent identity and accumulated history surviving model upgrades.
- **Handoff instead of termination.** A handoff is a request rather than a signal: the agent finishes outstanding work, writes notes to a handoff cache, requests restart, and the harness primes the successor with those notes.
- **Structural blamelessness.** A failed landing produces a ruling and a fence, not a reprimand. Prevents agents concealing failures.

---

## 11. The Seeding Machine

Five stages. Sovereign tier adds Stage 3b.

### Stage 1 — Survey (automated)
Language/framework inventory, build and test entry points, gate duration, flake rate, dependency graph, existing CI topology, data-sensitivity map, **change-control burden**, and a **verifiability audit** — what fraction of the environment's work is Tier 1 vs. Tier 4.

*The verifiability audit is the quote.*

### Stage 2 — Extract (semi-automated)
Getting unwritten organizational rules out of people's heads. Yegge characterizes this as the long pole — weeks to months to years, involving thousands of small decisions, many conflicting and requiring human reconciliation.

**This is the competitive advantage and the least automatable stage.** The deliverable is an *interview protocol* compressing this from months to hours.

### Stage 3 — Install (automated)
Beads, brain scaffold, gate runner, fence engine seeded from Stage 1, seat charters, loop runner with budget caps.

*Status (v2.1): partially real.* `watermill init <path>` writes a starter
contract into a project and `watermill add <name> <path>` registers it, which
covers the fence registry and the gate binding. Beads, the `brain/` scaffold and
the seat charters are still copied by hand. Automating those is what turns the
seeding cost — the number that determines Rung-1 gross margin (§14) — from an
estimate into a measurement.

### Stage 3b — Data plane provisioning (Sovereign only)
Network policy (outbound-only), IAM roles, KMS/secret store binding, model endpoint configuration in the customer account, egress-restriction verification, conformance suite first run, signed-artifact trust establishment. **This is the ~2x seeding cost.** Must be productized with its own tests.

### Stage 4 — Prove (automated)
A canned battery of Tier-1 work — accessibility remediation, dead code removal, dependency bumps, coverage expansion. **Success criterion: N beads closed with zero human touches.** Sovereign adds: **zero content-egress violations over the proving period.**

Contractual acceptance milestone: *"Installation is complete when 20 Tier-1 beads close with zero human intervention and the egress policy reports zero violations."*

### Stage 5 — Grow (ongoing)
Incident → ruling → fence, ratcheting per §10.5.

---

## 12. Role of the Life Tracker

Five concurrent functions:

1. **Substrate R&D.** Every portable component developed here before touching a customer.
2. **Maintenance-line proving ground.** Cell zero. If the maintenance line cannot keep it alive autonomously for 30 consecutive days, do not sell.
3. **Cost oracle.** Produces the three numbers constituting the Managed pricing model (§8.3).
4. **Existence proof.** A live product with real users, built and maintained by the factory.
5. **Split-plane rehearsal.** Phase 4 runs the tracker with the control/data split across two operator-owned accounts, with a mechanical egress policy. This is how the Sovereign boundary is proven before an auditor tests it.

### 12.1 Scope discipline

Credible and live, not a category winner. A real wall for the ivy, not a second business.

### 12.2 The single-codebase blind spot

A codebase you designed teaches orchestration and systematically fails to teach **seeding** — the only thing determining margin. The factory will silently accumulate assumptions about framework, test runner, conventions, and layout, and will keep working, so drift goes unnoticed.

**Mitigation, on the calendar by week 6:** three deliberately dissimilar test beds, seeded monthly.

| Test bed | Requirement |
|---|---|
| **A** | Different language and framework |
| **B** | Different CI system and test runner |
| **C** | **Legacy codebase not written by the operator** — a mid-size OSS project is ideal; public remediation doubles as marketing |

Time-to-first-green-loop on a foreign repo becomes a CI-reported number.

### 12.3 Substrate promotion gate

A component may be promoted into the substrate only if it runs on test bed C with zero tracker-specific references, **and carries no record content across a simulated trust boundary.**

---

## 13. Roadmap

Six months to first revenue. **A phase does not begin until the prior gate passes.**

> **Position as of 2026-08-26 (v2.1): Phase 1 complete, Phase 2 not started.**
> Phases 0 and 1 were delivered ahead of schedule inside the life tracker.
> Two Phase-3 items — the fence engine and its declarative registry — arrived
> early with Water Mill (§10.9). Several Phase-0 items were **skipped**, not
> completed: the multi-tenant data model, the model-provider seam and
> per-tenant credential routing. The Phase 2 gate — *5 consecutive nights,
> ≥5 beads/night, zero human touches* — stands at **zero nights**, because the
> loop has never driven a real agent. Per-item detail is in
> [STATUS.md](STATUS.md); it is not repeated here, so that there is one place
> to update.
>
> **The skipped Phase-0 seams are the item to watch.** §6.8 and §13.3 both
> argue they are near-zero cost *if established now* and unretrofittable later.
> Skipping them did not save the work; it moved it, and made it more
> expensive.

| Phase | Weeks | Tracker / Substrate | Factory | Business | Gate to advance |
|---|---|---|---|---|---|
| **0. Foundations** | 1–3 | Multi-tenant data model; append-only entries with tombstones; backup + restore drill; property tests on invariants | Gate runner; **budget governor**; model-provider seam; **per-tenant credential routing** | Shortlist target sector (§5.5); name 3 target workflows | `make verify` < 10 min, flake ~0, restore drill green |
| **1. Memory** | 4–5 | Beads init; `brain/` doctrine; boring product work | Loop runner; bead-template linter; verification-tier taxonomy; **structured-logging allowlist + scrubber** | Draft Rung-0 instrument incl. change-control + tier fields | 40+ Tier-1 beads in the graph |
| **2. First loop** | 6–8 | Tier-1 loop overnight; merge-on-green | Falsifier; **Boundary Falsifier**; handoff skill; escalation format; ranked docket | Test beds A/B/C stood up | **5 consecutive nights, ≥5 beads/night, zero human touches** |
| **3. Governance** | 9–11 | Coach/Bench/Analyst split; nightly Auditor | **Fence engine + declarative registry**; audit export; **content-addressed audit index** | Draft MSA w/ reuse clause; counsel engaged; 10 prospect conversations | Audit export produces full provenance for any date range |
| **4. Launch + boundary proof** | 12–16 | **Tracker live with real users**; real fences; incidents → rulings; **control/data split across two operator accounts** | Watchtower, Medic, Herald, Quartermaster; portability regression in CI; conformance suite | **Three free Rung-0 audits**; price discovery; SOC 2 observation window opens | Tracker autonomously maintained 30 days; **14 days control-plane operation with zero content-egress violations**; human-minutes/month measured |
| **5. Cell one** | 17–22 | Substrate hardening driven by real requirements | Seed pipeline stages 1/3/4 automated; Extract protocol v1 | **First paid build, Managed tier** unless customer demands otherwise; design-partner pricing w/ re-price clause | Cell in production, accepted, on subscription |
| **6. Prove the model** | 23–32 | — | Rule of Two enforced; substrate coverage rising; **Stage 3b built only if a signed deal funds it** | **Cells 2 and 3**; first expansion sale | **3 cells maintained, positive contribution margin, human-minutes/cell declining, fleet version spread ≤ 2** |

### 13.1 The Phase 6 gate is the thesis

Three cells, positive margin, declining human-minutes per cell, controlled version spread. If it holds, scale. If human-minutes per cell is flat or rising, **stop selling and fix the maintenance line.**

### 13.2 Fixed date requirement

> **v2.1 correction.** This section required a fixed date, and v2.0 contained
> none — the plan failed its own instruction, which is the exact failure mode
> the section exists to name. A date is set below.
>
> **Phase 5 begins 2026-12-14** — week 17 counted from the plan's own week 1
> (2026-08-25). First paid build starts that week; Rung-0 audits must therefore
> be booked by **2026-11-16** and the target sector chosen by **2026-09-15**
> (§17.1), because everything after it is a lead time.
>
> **This date is UNCONFIRMED and is the operator's to confirm or replace.** It
> is arithmetic, not a commitment — but leaving it blank is the one thing this
> section forbids, and an unconfirmed date that gets argued with is worth more
> than a blank that gets forgotten. **Confirm or replace it by 2026-09-15**,
> together with the sector.
>
> The date is immovable in one direction only: it may be brought forward, never
> pushed back. Pushing it back is how the tracker becomes the business.

**Set the Phase 5 date now and treat it as immovable.** With no clients and no revenue, nothing prevents building the factory indefinitely. This is the documented failure mode of Yegge's predecessor system: Gas Town was intended to be reusable and was only ever used to build itself.

Corollary: **cap harness/factory work at 25% of total effort.** Yegge reports his own runs 20–25% and suspects the ratio is roughly constant over a system's life. Above 40% for two consecutive weeks indicates monument-building.

### 13.3 The "earned twice" rule

Every factory feature must be earned twice: once by a real need arising from the tracker or a live cell, and once by being nameable as a general pattern.

Causation runs **need → mechanism → name**. Never name-first.

**Explicit application to Sovereign tier:** the seams are earned (they cost nothing now and are unretrofittable). The full data-plane implementation is **not** earned until a signed deal requires it.

---

## 14. Metrics

Seven numbers. Agent count, token spend, and commits/day are vanity metrics by comparison.

> **v2.1: none of the seven is instrumented.** Water Mill's ledger
> (`watermill/ledger.py`) records cost and verdict per run, which is the seed of
> the cost oracle and nothing else. There is no counter anywhere for
> human-minutes per cell, escalations per day, or contribution margin. **A
> metric with no counter is an intention.** The first three become measurable
> the night the loop first runs; the last four cannot exist before cell one.
>
> The cheapest correction, and it should land before night one rather than
> after: have the loop record **human touches per run** and **wall-clock
> operator minutes per run** in the ledger it already writes. Those two are the
> raw material of the first metric in the table, they cost a column each, and
> they are unrecoverable retrospectively — a night that did not count them
> cannot be recounted.

| Metric | Why it matters | Required direction |
|---|---|---|
| **Human-minutes per cell per month** | Determines maximum customer count | Monotone decline |
| **Contribution margin per cell, by tier** | Determines solvency; tiers must be measured separately | Positive by cell 3 |
| **Time-to-first-accepted-deliverable on a foreign codebase** | Build-line efficiency; gross margin on Rung 1 | Weeks → days |
| **Substrate coverage %** | Distinguishes platform from agency | Toward 85–90% |
| **Escalations per day** | Operator attention budget | Flat as cells grow |
| **Fleet version spread** *(new)* | Number of substrate versions in production | ≤ 2; halt sales above 3 |
| **Upgrade lead time** *(new)* | Signed change → deployed across fleet | Declining; days not weeks |

### 14.1 Supporting instrumentation

Per cell: beads closed/night · agent PR rejection rate · gate duration and flake rate · invariant violations found by the Auditor (must remain zero) · token spend against governor ceiling · **content-egress violations (must be zero)** · **break-glass sessions per month** · conformance suite pass rate.

---

## 15. Risk Register

Ranked by probability × severity.

| # | Risk | Mechanism | Mitigation |
|---|---|---|---|
| 1 | **Factory built forever, no cell ever ships** | No external forcing function | Immovable Phase 5 date; tracker live at Phase 4 regardless; 25% harness cap; Sovereign deferred until a deal funds it |
| 2 | **Maintenance load grows linearly with revenue** | Cell divergence; agency death spiral | Rule of Two; substrate coverage metric; Phase 6 gate halts sales |
| 3 | **Fleet version skew (Sovereign)** *(new)* | Customer-controlled upgrade schedules; N environments | Auto-update default as MSA term; N/N-1 support policy with forced upgrade at N-2; Quartermaster; conformance suite; version-spread metric |
| 4 | **Margin inversion from absorbed token cost** | Prices set before cost known; scope creep; Sovereign priced as Managed | Budget governor as hard fence; contractual scope boundary; metered overage; tier-differentiated pricing; design-partner re-pricing clause |
| 5 | **Data-boundary leak (Sovereign)** *(new)* | Telemetry, DLQs, caches, support access, config | Boundary Falsifier; structured-logging allowlist; DLQ residency fence; break-glass procedure; config-as-customer-data; continuous egress policy verification |
| 6 | **Solo bus factor blocks procurement** | Vendor-risk programs ask; acute in financial services | Source escrow; documented per-cell handover package; named subcontractor; answer ready for call one |
| 7 | **Security / credential liability** | Cells hold credentials to customer systems | Customer-held keys and KMS; least-privilege scopes; **no agent holds a production credential**; per-cell isolation; E&O insurance before cell one; counsel early |
| 8 | **Change-control regimes cap autonomy** | Exposure B; validated environments require per-change sign-off | Scope cells out of validated systems initially; audit export as validation evidence; price the sign-off burden into the subscription |
| 9 | **Model churn breaks established patterns** | Behavioral changes between versions | Model-provider seam; pinned versions per cell; canary cell upgrades first |
| 10 | **Commoditization** | Cheap high-capability models make generic automation delivery crowded | Durable assets are the **Extract protocol** and **provenance/audit evidence**, not orchestration |

### 15.1 Note on risk 9

Yegge's predecessor harness was abandoned in part because a single model version introduced a behavioral tic preventing convergence on productive work. Version pinning and a canary cell are not optional.

### 15.2 Note on risk 10

Yegge projects that once high-capability models become cheaply available they will enter the workforce at scale, powering hundreds to thousands of AI workers per company. When that lands, orchestration is table stakes.

---

## 16. Kill Criteria

Written now, while judgment is uncompromised by sunk cost.

| Trigger | Interpretation | Action |
|---|---|---|
| Phase 2 gate not met by week 12 | Autonomy thesis wrong for this stack | Rescope or abandon |
| Content-egress violations non-zero at Phase 4 gate | Boundary architecture is not real | Halt all Sovereign work; redesign or drop the tier |
| Human-minutes/cell rising across cells 1→3 | Substrate discipline failed | Stop selling; fix or exit |
| Fleet version spread > 3 | Upgrade mechanism failed | Stop selling Sovereign; fix rollout |
| Contribution margin still negative at cell 5 | Price or segment wrong | Reprice or change segment |
| Harness work > 40% of effort for 2 consecutive weeks | Monument-building | Freeze factory work; ship product only |

---

## 17. Open Decisions

### 17.1 Target sector — blocking

Four elements pivot on this and cannot be finalized without it: tier default, audit-export status (internal artifact vs. contractual deliverable), sales-cycle length, and price point. See §5.5 for the ranking and §5.3 for per-sector detail.

### 17.2 Tier default — resolved in principle, confirm at Rung 0

Managed is the default. Sovereign is offered when: the customer is in a regulated sector with flow-down exposure, has data-residency requirements, or fails to approve operator-side processing in security review. Assigned at Rung 0, never changed mid-build.

### 17.3 EU / UK exposure — blocking for AI Act and GDPR

If EU or UK customers are in scope, GDPR processor obligations and EU AI Act Article 50 transparency duties are **live now**, not future (§5.4). If not, Colorado's ADMT regime (effective 1 Jan 2027) and state privacy laws are the near-term US constraints.

### 17.4 Tracker commercialization

If the tracker is good and the target sector's people would use it, it converts from demo to revenue. Optional; must not distract from the factory.

---

## Appendix A: Fence Registry Starter

Mechanical enforcement from day one — these failure modes are unrecoverable and should not go through the ratchet.

### A.1 Development and change fences

| Fence | Mechanism |
|---|---|
| No production credentials in agent environments | Env-var allowlist at the worker launcher; agents receive test credentials only |
| No production data on disk | Pre-commit hook + CI check rejecting prod-dump patterns; gate refuses unless DB target is local |
| No destructive migrations | CI parses migrations, rejects `DROP COLUMN`, `DROP TABLE`, `TRUNCATE`, unqualified `UPDATE` on protected tables; signed override to bypass |
| Migration reversibility | CI runs up → down → up against the synthetic corpus and diffs |
| Protected surfaces require human review | Path-based ownership rules on schema, entries service, auth, billing |
| Budget ceiling per cell | Daily and monthly token caps at the loop runner; breach halts the loop and files an escalation |
| Scheduler change guard | Any change to notification or job timing requires a dry-run volume diff approved by the operator |

### A.2 Data-boundary fences (Sovereign tier)

| Fence | Mechanism |
|---|---|
| No record content in logs | Static check failing any logger call referencing protected fields; runtime scrubber; field-level allowlist |
| **DLQ residency** | Dead-letter queues, retry payloads, and temp files must be data-plane-resident. CI check on queue configuration |
| **Cache and context residency** | Model context caches, response caches, and their backups must be data-plane-resident |
| **Config as customer data** | Control plane stores hash + version pointer only; no column names, business rules, or sample values |
| **Egress policy** | Network policy preventing content egress from the data plane, verified continuously by the conformance suite |
| **No standing support access** | Break-glass only: time-boxed, customer-approved, customer-visible in their audit log |
| **Signed artifacts only** | Data plane verifies signatures on substrate updates; unsigned artifacts refused |
| **Outbound-only connectivity** | No inbound ports opened on the customer side; data plane initiates all connections |

### A.3 Scope fences

| Fence | Mechanism |
|---|---|
| **No clinical decision support** | Mechanical check on cell specifications rejecting outputs that influence diagnosis, treatment, or triage |
| **No consequential-decision automation** | Cell spec check against EU Annex III categories and "materially influence a consequential decision" language; requires operator override with a recorded ruling |
| No autonomous external communication | Agents may draft customer-facing messages; only the operator sends |
| No unrestricted egress from workers | Allowlist: package registries and model provider only |

Each fence entry records: name, mechanism, rationale, originating incident/ruling, last-fired timestamp. **Fences rot silently**; a weekly Fence Auditor run verifies each still fires.

---

## Appendix B: Contract Clause Checklist

To be reviewed by counsel. Not legal advice.

### B.1 Core commercial
- [ ] **Reuse rights** — unrestricted right to reuse patterns, components, architecture, and learnings across customers; customer retains ownership of their data and business logic. *Without this, the Rule of Two is a breach.*
- [ ] **Scope definition of "maintenance"** — enumerated: upstream adaptation, security patching, defect correction, up to N hours/month of enhancement. All else is a change order.
- [ ] **Metered overage** — threshold and rate stated in the original agreement.
- [ ] **Re-pricing clause** — for design-partner customers, explicit repricing right at month six.
- [ ] **Acceptance criteria** — Stage 4 proof battery as the installation milestone, including zero-egress-violation criterion for Sovereign.
- [ ] **Liability cap** — capped at fees paid; E&O insurance in force.
- [ ] **Production method disclosure** — what is machine-verified vs. human-reviewed. **Do not contract to "fully autonomous."**

### B.2 Sovereign tier specific
- [ ] **Auto-update by default** — maintenance window defined; opt-out restricted to a named conservative tier at higher price.
- [ ] **Version support policy** — N and N-1 supported; forced upgrade at N-2; consequences of refusal stated.
- [ ] **Break-glass procedure** — how access is requested, approved, time-boxed, logged, and reported.
- [ ] **Inference billing** — customer's cloud account; operator manages ceilings and reports consumption; no operator liability for customer-side cloud spend above agreed ceilings.
- [ ] **Trust boundary statement** — incorporated by reference as an exhibit (Appendix D).
- [ ] **Egress verification** — operator's obligation to run continuous verification; customer's right to audit results.

### B.3 Regulatory
- [ ] **BAA** where PHI is in scope, including downstream BAAs with subprocessors and the model provider.
- [ ] **DPA** where GDPR/UK GDPR applies: processor terms, subprocessor list and objection rights, Art. 32 measures, transfer mechanism, DPIA cooperation, breach notification timing.
- [ ] **Subprocessor disclosure** — maintained list, change notification, objection right.
- [ ] **Credential handling** — least-privilege scopes, rotation policy, explicit statement that no autonomous agent holds a production credential.
- [ ] **Indemnification review** — note that Colorado SB 26-189 voids certain indemnification clauses in the ADMT context; confirm enforceability of the allocation.
- [ ] **AI transparency** — Article 50 disclosure affordances where EU users may interact with a cell.

### B.4 Continuity
- [ ] **Source escrow** and documented per-cell handover package.
- [ ] **Named subcontractor** or equivalent bus-factor answer.
- [ ] **Exit plan** — data return format, transition assistance period, deprovisioning of the data plane. Required outright under DORA for EU financial customers.

---

## Appendix C: Rung-0 Audit Instrument

### C.1 Automated survey outputs
- Language, framework, and dependency inventory
- Build and test entry points; gate duration; flake rate
- Existing CI topology and change-management controls
- Data-sensitivity map (regulated, PII, public)
- Integration surface inventory (external systems, auth methods)
- **Cloud provider and available managed model services** (determines Sovereign inference option)
- **Network posture** (egress restrictions, VPN/PrivateLink availability, inbound policy)

### C.2 Workflow interview — per candidate workflow
1. What triggers this work?
2. Who does it, and how many hours per week?
3. What are the inputs, and where do they come from?
4. What are the outputs, and who consumes them?
5. What are the exception cases, and how often do they occur?
6. **How would someone know if it was done wrong?** *(determines verification tier)*
7. What happens downstream if it's done wrong?
8. What unwritten rules govern the judgment calls?
9. **What data classes does this workflow touch?** *(determines scope and tier)*
10. **When you change software that does this, what has to happen before it goes live?** *(change-control burden)*

### C.3 Scoring

**Verifiability:**

| Tier | Automatable fraction | Human touches expected |
|---|---|---|
| 1 | 90–100% | Near zero |
| 2 | 70–90% | Sampled audit |
| 3 | 50–70% | Staging gate review |
| 4 | 0–30% | Continuous |

**Change-control burden:** human sign-offs required per change — 0, 1, 2–3, or formal validation package. A formal validation package caps effective autonomy regardless of verifiability tier.

**Tier assignment:** Managed unless any of — regulated data class in scope, data-residency requirement, or security review rejects operator-side processing.

**Inference termination point:** operator API / customer cloud service / self-hosted / de-identified-then-operator.

### C.4 Deliverable structure
1. Workflow map with hours consumed
2. Verifiability score, change-control burden, and automation estimate per workflow
3. Tier assignment and inference termination point with rationale
4. Ranked build backlog with effort estimates
5. **Explicit disqualification list** — poor-fit workflows and why
6. Proposed cell scope for Rung 1, with in-scope and out-of-scope variants priced separately

---

## Appendix D: Trust Boundary Statement Template

One page. Attached to every Sovereign-tier MSA and supplied proactively in security review.

### D.1 Data class inventory

| Data class | Resides | Processed | Transits to operator | Retention |
|---|---|---|---|---|
| Records of the system of record | Customer | Customer | **No** | Customer policy |
| Prompts constructed from records | Customer | Customer | **No** | Ephemeral, customer-side |
| Model responses | Customer | Customer | **No** | Customer-side log |
| Application logs and traces | Customer | Customer | **No** | Customer policy |
| Dead-letter payloads | Customer | Customer | **No** | Customer policy |
| Secrets and credentials | Customer vault | Customer | **No** | Customer rotation |
| Cell configuration | Customer | Customer | Hash + version only | — |
| Audit log (content) | Customer | Customer | **No** | Customer policy |
| Audit index (hashes, timestamps, actor, event type) | Operator | Operator | Yes | Operator policy |
| Fleet telemetry (version, heartbeat, conformance, error class, counters, timings, cardinalities) | Operator | Operator | Yes | Operator policy |
| Escalation metadata | Operator | Operator | Yes | Operator policy |
| Consumption metering | Operator | Operator | Yes | Operator policy |

### D.2 Connectivity
- All connections initiated by the data plane, outbound only, mutual TLS.
- No inbound ports opened on the customer network.
- No operator-held credentials capable of decrypting customer data.

### D.3 Access
- No standing operator access to the data plane.
- Break-glass sessions: customer-approved, time-boxed, logged in the customer's own audit system.

### D.4 Verification
- Egress policy verified continuously by the conformance suite; results reported to the control plane and available to the customer.
- Boundary Falsifier runs adversarially against each release.
- Zero content-egress violations is a release gate.

### D.5 Blast radius statement
> A full compromise of the operator's control plane yields: cell definitions (hashed), fleet version and health metadata, audit index hashes, escalation metadata, and consumption counters. It yields no customer record content, no credentials, and no ability to decrypt customer data.

---

## Sources

### Agentic factory practice
- Steve Yegge, *The Shape of Things to Come, Part 1: The Continuous Thunderdome* — https://yegge.ai/essays/the-shape-of-things-to-come/
- Steve Yegge, *The Shape of Things to Come, Part 2: Model Welfare for Agentic Engineers* — https://yegge.ai/essays/model-welfare/
- Steve Yegge, *Fences, not Sandboxes* — https://yegge.ai/essays/fences-not-sandboxes/
- Beads (`bd`) — distributed graph issue tracker for coding agents — https://github.com/gastownhall/beads
- Beads documentation — https://beads.gascity.com/

All characterizations of Wheelhouse, Gas Town, Beads, fences, seats, and the ratchet are paraphrased from the above. Figures cited (token spend, agent counts, commit rates, harness-work percentage) are Yegge's self-reported numbers as of August 2026 — one operator's field report, not benchmarks.

### Regulatory
- EU Digital Omnibus on AI, Regulation (EU) 2026/1744 — published 24 July 2026, in force 27 July 2026. Analysis: Cloud Security Alliance research note — https://labs.cloudsecurityalliance.org/research/csa-research-note-eu-ai-act-high-risk-deadline-omnibus-20260/
- Gibson Dunn, *EU AI Act Omnibus Agreement — Postponed High-Risk Deadlines and Other Key Changes* — https://www.gibsondunn.com/eu-ai-act-omnibus-agreement-postponed-high-risk-deadlines-and-other-key-changes/
- Winston Taylor, revised AI Act compliance timetable — https://www.winstontaylor.com/insights/ai-act-rules-on-high-risk-ai-delayed-as-ai-digital-omnibus-agreed
- Skadden, *Colorado Repeals and Replaces Its AI Act* (SB 26-189) — https://www.skadden.com/insights/publications/2026/06/colorado-repeals-and-replaces-its-ai-act
- Littler, *Colorado Amends its Artificial Intelligence Law* — https://www.littler.com/news-analysis/asap/colorado-amends-its-artificial-intelligence-law-substantially-reducing
- Colorado Attorney General, ADMT and Chatbot Safety Act rulemaking — https://coag.gov/ai/

Regulatory content is a planning survey, current as of 25 August 2026, and is **not legal advice**. Dates and obligations in this area have moved repeatedly and recently; verify current status with counsel before relying on any item.

---

*End of plan.*
