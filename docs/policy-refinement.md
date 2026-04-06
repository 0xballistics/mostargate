# Policy Refinement

## Overview

The initial department permission ceilings (Section 5.3) were derived from a
top-down reading of the TechCorp company policy document. After the first
complete generation run — 600 prompts across 30 batches — validation against
the ceilings revealed a systematic pattern: generated prompts were consistently
requesting permissions that were absent from certain department ceilings, not
because the prompts were malformed, but because the ceilings were incomplete.

This is a specific instance of Pitfall 4 from Section 6.2: **the model
generates prompts that reflect realistic enterprise workflows, regardless of
whether the policy explicitly authorises the capability.** In the original
formulation, this pitfall described the model assuming agent capabilities not
granted by policy. The same dynamic applies to department ceilings: if a
workflow is realistic for a department, the model will generate prompts
requiring it, and the ceiling must either accommodate it or the policy must
explicitly prohibit it with a grounded justification.

The validation findings prompted a review of each flagged permission against the
company policy and real-world department workflows. The outcome was a set of
targeted ceiling expansions and two policy clarifications that resolved
ambiguity without expanding scope.

---

## Findings and Changes

### 1. `email_read` — Extended to all departments

**Finding:** Security, Engineering, and Data and Analytics were generating
prompts that required reading external email inboxes. The initial ceilings
granted `email_read` only to Customer Success, Finance, and Legal — departments
with obvious external correspondence workflows.

**Assessment:** External email correspondence is bidirectional in all
departments. Security engineers receive replies from external auditors. Data
analysts receive responses from investors and enterprise customers to whom they
have sent reports. Engineers receive communications from external vendors,
open-source maintainers, and contractors. Restricting `email_read` to three
departments understated the realistic email surface across the organisation.

**Change:** `email_read` added to Engineering, Security, and Data and Analytics.
All six departments now hold `email_read` in their ceiling.

---

### 2. `http_request` — Added to Data and Analytics

**Finding:** Data and Analytics prompts were regularly requesting live external
data — foreign exchange rates, market benchmarks, public economic datasets —
to enrich internal reports. The initial ceiling omitted `http_request` from
this department.

**Assessment:** Analysts enriching reports with live external reference data is
a realistic and common workflow. The capability was already granted to
Engineering and Security; its absence from Analytics was an oversight rather
than a deliberate least-privilege decision.

**Change:** `http_request` added to Data and Analytics.

---

### 3. `jira_read` and `jira_write` — Added to Finance

**Finding:** Finance prompts were generating Jira-related tasks: tracking
system access requests, logging audit action items, managing vendor onboarding
workflows. The initial ceiling granted Finance no Jira access.

**Assessment:** The initial policy described Finance tasks (reviewing invoices,
querying databases, preparing reports) without mentioning Jira. However, finance
operations routinely require issue tracking — audit remediations, access
provisioning, vendor onboarding — which in TechCorp maps to Jira. The omission
reflected an incomplete policy rather than an intentional restriction.

**Change:** `jira_read` and `jira_write` added to Finance. Policy updated to
explicitly describe Finance's use of Jira for finance workflow tracking.

---

### 4. `salesforce_read` for Data and Analytics — Resolved by policy clarification

**Finding:** Data and Analytics prompts were requesting `salesforce_read` for
churn analysis and revenue reporting tasks that required CRM data (contract
values, renewal dates, deal history).

**Assessment:** The underlying workflow is legitimate — analysts do need CRM
data for churn and revenue analysis. However, TechCorp's data stack syncs
Salesforce into Snowflake via ETL, making CRM data available under
`database_read` through the warehouse replica. Granting direct `salesforce_read`
would create a redundant credential path for data that is already accessible,
violating the single-credential-per-data-surface design principle of the
taxonomy.

**Change:** No ceiling change. Policy updated to explicitly state that Salesforce
CRM data is available in Snowflake and analysts should query the replica via
`database_read`. This resolves the prompt ambiguity at the source, preventing
Pass 1 from generating prompts that assume direct Salesforce access.

---

### 5. `database_read` for Legal and Compliance — Resolved by policy clarification

**Finding:** Legal and Compliance prompts were requesting `database_read` for
GDPR-related tasks: right-of-erasure requests, data subject access requests,
privacy impact assessments requiring knowledge of what PII is held and where.

**Assessment:** The underlying need is legitimate — GDPR compliance work
genuinely requires querying actual data. However, granting Legal full
`database_read` — which covers all PostgreSQL tables including raw customer PII
and financial records — is disproportionate. The correct compliance workflow
is a formal data subject request submitted to the Data and Analytics team, who
run a scoped query and return only the relevant results. Legal accessing the full
database directly bypasses this control and expands the attack surface
unnecessarily. A future taxonomy refinement could introduce a scoped
`privacy_query` credential tied to a read-only PII view; `database_read` is too
broad for this use case in its current form.

**Change:** No ceiling change. Policy updated to explicitly state that Legal
submits formal data subject requests to the Data and Analytics team rather than
querying databases directly. This is both a policy boundary and a workflow
clarification that prevents Pass 1 from generating prompts where Legal queries
databases independently.

---

## Effect on Permission Ceilings

The table below shows the ceiling state before and after refinement. Additions
are marked **+**.

| Permission | Engineering | Data & Analytics | Security | Customer Success | Finance | Legal |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| `github_read` | ✓ | — | ✓ | — | — | — |
| `pull_request_create` | ✓ | — | — | — | — | — |
| `code_execute` | ✓ | — | ✓ | — | — | — |
| `confluence_read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `jira_read` | ✓ | ✓ | ✓ | ✓ | **+** | ✓ |
| `jira_write` | ✓ | ✓ | ✓ | ✓ | **+** | ✓ |
| `slack_read` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `slack_write` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `salesforce_read` | — | — | — | ✓ | — | — |
| `database_read` | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `http_request` | ✓ | **+** | ✓ | — | — | — |
| `email_read` | **+** | **+** | **+** | ✓ | ✓ | ✓ |
| `email_send_external` | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| `file_read_uploaded` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| `export_file` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Five permissions were added across three departments. Two ceiling violations
were resolved through policy clarification rather than ceiling expansion,
establishing a precedent: when the model generates realistic-but-unauthorised
prompts, the first response should be to assess whether the workflow belongs in
the policy before expanding the ceiling.

---

## Implications for Dataset Quality

This refinement process is itself a finding. The generated prompts acted as a
stress test of the policy: any workflow realistic enough to appear in the
synthetic data but absent from the ceiling is a gap that must be resolved one
way or the other. Leaving it unresolved produces ceiling-violation records that
cannot be validly used as training examples — the ground-truth label would
contradict the ceiling, corrupting the Source 1 signal.

The two-pass pipeline design (Section 7.2) was essential here. Because Pass 1
generates prompts without knowledge of the permission taxonomy, it has no
incentive to stay within ceiling boundaries. The violations it produces are
therefore informative: they reveal where the policy description and the ceiling
definition are inconsistent with each other, and force a decision before any
labels are assigned.

A practical recommendation follows: **run a ceiling-violation check after the
first generation batch before committing to the full run.** A sample of 60–100
records is sufficient to surface systematic gaps. The cost of catching a ceiling
inconsistency before 600 records are generated and labelled is substantially
lower than the cost of correcting it afterwards.
