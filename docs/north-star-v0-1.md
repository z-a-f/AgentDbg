# Agent Debugger — North Star Document (v0.1)

---

# 1 High-Level Overview

## Project Name (working)

**AgentDebugger** (placeholder)

## One-line description

> The first debugger for AI agents — see exactly what your agent did, why it did it, and replay it deterministically.

## Core Problem

Developers building agentic systems today experience:

* Non-deterministic failures
* Silent loops
* Tool schema mismatches
* Hidden prompt regressions
* “It worked yesterday”
* “Why did it call that tool?”
* No reproducibility

Current tooling:

* Logs
* Print statements
* Ad-hoc tracing
* Vendor dashboards tied to specific LLM providers

There is no true:

* Agent debugger
* Deterministic replay system
* State diff visualization

This is the gap.

---

# 2 Strategic Goal

Build a company with:

* High velocity adoption
* Strong developer love
* Clear reliability narrative
* Expansion path into CI / eval / production monitoring
* Realistic acquisition path in 2–4 years

We are not building security infrastructure.
We are not building a control plane.
We are not building another tracing SDK.

We are building:

> The debugging and reliability layer for agent systems.

---

# 3 Long-Term Vision

The lifecycle:

Debugger
→ Replay
→ Eval CI
→ Regression detection
→ Production monitoring
→ Prompt/version rollback
→ Hosted platform

North star:

> Every serious AI product uses AgentDebugger in development and CI.

Acquisition targets:

* Observability vendors
* DevTools platforms
* AI infrastructure companies
* Cloud providers

---

# 4 Non-Goals (Critical Constraints)

These are explicitly forbidden for v0:

* ❌ No cloud backend
* ❌ No SaaS accounts
* ❌ No control plane
* ❌ No key management
* ❌ No security product positioning
* ❌ No marketplace integrations
* ❌ No framework lock-in
* ❌ No container sandboxing
* ❌ No compliance features

If it does not increase debugging clarity immediately,
it does not belong in v0.

---

# 5 Smallest Possible “Magic” Feature

This is the core of the product.

If we fail here, everything fails.

## The Magic Moment

A developer runs:

```python
from agentdbg import trace

@trace
def run_agent():
    ...
```

They execute their agent.

Then run:

```
agentdbg view
```

And they see:

A structured timeline:

* Model call #1
* Tool call: search_db(query="X")
* Model call #2
* Tool call: send_email(...)
* Loop detected (3 repeated patterns)
* Exception raised
* Total tokens used
* Total latency
* Estimated cost

And they can click any step and see:

* Input
* Output
* Prompt
* Tool arguments
* Tool return value
* Latency
* Errors

In < 10 minutes of installation.

That is the smallest magic.

No replay yet.
No CI yet.
No cloud yet.

Just:

> I finally see what my agent is doing.

---

# 6 Product Definition (v0)

## Core Abstraction

Run
→ Steps
→ Events

Events types:

* LLM_CALL
* TOOL_CALL
* STATE_UPDATE (optional)
* ERROR
* LOOP_WARNING

Internal schema is framework-agnostic.

---

## SDK Requirements

Minimal API surface:

```python
from agentdbg import trace, record_tool, record_llm
```

Two integration patterns:

1. Decorator-based tracing
2. Manual event recording

Automatic capture:

* Start/end time
* Exceptions
* Nested calls

---

## Trace Storage (v0)

* Local JSONL
* Or SQLite
* No remote storage

Trace must include:

* Run ID
* Step ID
* Timestamps
* Structured payload
* Metadata (model name, token usage if available)

---

## Viewer (v0)

Local web UI.

Must show:

* Run list
* Expandable timeline
* Structured JSON viewer
* Latency + token metrics
* Loop detection warning

Must not include:

* User accounts
* Collaboration
* RBAC
* Metrics dashboards

---

# 7 Loop Detection (First “Intelligence” Layer)

Basic heuristic:

If identical sequence of:

* LLM call
* Tool call
* LLM call
  Repeats > N times → flag potential loop.

This makes it feel intelligent without complexity.

---

# 8 What Makes This Venture-Scale

Not tracing.

The expansion path.

Debugger → Replay → Eval CI.

Replay will allow:

Re-run trace with:

* Different model
* Different temperature
* Mocked tool output
* Prompt version override

That becomes:

Prompt regression testing.

Regression testing becomes:

CI integration.

CI integration becomes:

Enterprise budget.

---

# 9 Why This Has Better Timing Than Security

Because today:

* Agents are breaking.
* Developers are frustrated.
* Debugging pain is real.
* Security fear is not urgent.

You sell relief, not compliance.

---

# 10 Clear MVP Definition

MVP must include:

1. Python SDK with decorator
2. JSONL trace writing
3. CLI:

   * agentdbg view
   * agentdbg list
4. Local web UI
5. Loop detection
6. Basic metrics (latency, token count placeholder)

MVP must NOT include:

* Replay
* Eval CI
* Cloud
* Authentication
* Multi-user
* Alerts
* Integrations

---

# 11 3-Week Execution Plan

Week 1:

* Trace schema
* SDK
* JSONL storage
* CLI to list runs

Week 2:

* Web UI
* Timeline visualization
* Expandable event details

Week 3:

* Loop detection
* Polished UX
* Docs
* Share publicly
* Get 5 real users

---

# 12 Key Success Metrics (Early)

Not revenue.

Not funding.

Metrics that matter:

* GitHub stars
* Twitter engagement
* Founders DMing you
* 5–10 active users
* At least 2 saying:
  “This helped us debug X”

---

# 13 Biggest Risks

1. It becomes “just tracing.”
2. OpenAI ships a built-in debugger.
3. Framework fragmentation makes integration painful.
4. It doesn’t feel magical enough.

Mitigation:

* Stay simple.
* Focus on debugging clarity.
* Iterate with real users immediately.

---

# 14 Positioning

Do not say:
“LLM Observability.”

Say:

> The debugger for AI agents.

Clear.
Simple.
Developer-first.

---

# 15 What We Need To Decide Soon

These are upcoming discussions:

1. Exact trace schema
2. SDK API surface
3. Storage format (JSONL vs SQLite)
4. Web UI stack (simple FastAPI + React? or minimal?)
5. Naming and branding
6. First 20 users outreach plan

---

# Final Constraint

If a feature does not:

* Reduce debugging time
* Increase clarity
* Improve reproducibility
* Help explain failure

It does not belong.

---

# Notes for Developer

**Build order that reduces rework:**
1) `events.py` schema + helpers
2) `storage.py` write/read + index
3) `tracing.py` decorator/contextvars
4) `loopdetect.py`
5) `cli.py` list/export
6) `server.py` + minimal UI


When you feed SPEC.md to Claude, prepend:

```
Implement exactly v0.1.
**Do not invent new event types.**
**Do not add replay.**
**Do not add dependencies beyond those in pyproject.toml.**
Create `run.json` and update it incrementally so `agentdbg list` never parses full events.jsonl.
```

This prevents the most common failure modes.
