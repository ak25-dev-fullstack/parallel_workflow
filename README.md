# Network Config Analyzer — Mini Orchestrator

A mini orchestrator (Python + Anthropic SDK) that spawns 3 parallel subagents to analyze a
Cisco-style router/switch config, and compares three ways of coordinating them:
**sequential**, **parallel (fan-out/fan-in)**, and **coordinator-worker**.

Built for CCAR-F exam prep — the point is to understand the three orchestration patterns,
not to build a polished tool.

## Why this task

Config files are static text, so no live network is needed to start. The three analysis
angles below map onto CCNA study material directly, so building this doubles as exam review.
It's also a natural fit to later point at real output from a Raspberry Pi (`show running-config`
equivalent, `iptables`/`ufw` rules).

## The three subagents

Given one config file, each subagent analyzes a different concern:

1. **Security/ACL review** — flags overly permissive rules, missing access control, etc.
2. **CCNA concept explainer** — explains what each relevant command does and why, in
   study-note form.
3. **Troubleshooting/optimization** — suggests fixes and improvements.

## The three orchestration patterns

1. **Sequential pipeline** — three Claude calls run one after another. Each step *can*
   depend on the previous step's output (e.g. feed security findings into the
   troubleshooting prompt) — this is the legitimate use case for sequential over parallel,
   not just an unoptimized version of it.
2. **Parallel pipeline (fan-out/fan-in)** — the same three calls fired concurrently via
   `asyncio.gather`, since the three concerns are independent of each other. No LLM
   coordinates them; code just dispatches and collects.
3. **Coordinator-worker** — a coordinator call reads the config first and decides what each
   worker should actually focus on (e.g. if there are no ACLs at all, the security worker's
   task becomes "flag that no access control is configured" instead of "review ACLs").
   Workers run in parallel with the coordinator's per-worker instructions, then a synthesis
   call merges their output into one prioritized report.

`compare.py` runs all three pipelines against the same config and reports wall-clock latency
and token usage for each, so the differences are measured, not just asserted.

## Project structure

```
parallel_workflow/
  .env                    # ANTHROPIC_API_KEY (not committed)
  .gitignore
  test_setup.py            # phase 1 sanity check — confirms SDK/auth work
  sample_configs/
    basic_router.cfg       # hand-written sample config for testing
  agents.py                # shared Claude call wrapper (async) + all system/user prompts
  pipelines/
    sequential.py
    parallel.py
    coordinator.py
  compare.py                # runs all 3 pipelines, prints latency + token comparison
  run_security_review.py    # standalone single-call test of the security prompt
  run_ccna_explainer.py     # standalone single-call test of the CCNA prompt
  run_troubleshooting.py    # standalone single-call test of the troubleshooting prompt
  results/                  # saved report .txt files from each pipeline run (git-ignored)
```

## Sourcing sample configs

Options, easiest first:

1. **Write a small one by hand** — 15-30 lines: hostname, a couple VLANs, one ACL, a static
   route. Good CCNA practice in itself, and the best starting point since it's small and
   fully understood.
2. **Packet Tracer / GNS3** — `show running-config` on any lab device gives a real one.
3. Cisco's own documentation examples (fine to copy for local, non-shared learning use).

## Build plan

### Phase 0 — Environment ✅ done
`.venv` + `anthropic` + `python-dotenv`, `.env` holding `ANTHROPIC_API_KEY`,
`test_setup.py` confirms the SDK and auth work.

### Phase 1 — Single-call baseline (~30-45 min) ✅ done
One Claude call, one config file, one concern (start with the security review). Proves the
prompt design works before adding concurrency.

Design questions to work through:
- How is the config passed into the prompt — inline as a labeled block
  (`` "Config:\n```\n{config}\n```" ``) so Claude clearly distinguishes instructions from data.
- What makes the prompt specific enough to produce gradeable output instead of generic
  Cisco-security boilerplate? ("List each ACL rule, state whether it's overly permissive,
  and why" beats "review this config.")

**Checkpoint:** run against the sample config — does the output reference specific lines
from *this* config, or could it have been written without reading it?

### Phase 2 — Three prompts, three concerns (~30 min) ✅ done
Write the CCNA-explainer and troubleshooting prompts the same way. Test each standalone
before wiring up any pipeline.

Open design question: should all three subagents see the whole config, or should relevance
be filtered first? Full config to all three is the right choice for v1 — intelligent
routing of what's relevant to whom is what makes coordinator-worker interesting later.

### Phase 3 — Sequential pipeline (~30 min) ✅ done
Three `await` calls in a row. Worth trying real chaining here — e.g. feed call 1's
security findings into call 3's troubleshooting prompt, so sequential is doing something
parallel structurally can't (using one step's output in the next).

### Phase 4 — Parallel pipeline (~45-60 min) ✅ done
`asyncio.gather` over the three independent analyses. This is where the real wall-clock
speedup shows up, since the three angles are genuinely independent for a given config.

### Phase 5 — Coordinator-worker (~60-90 min) ✅ done
The most involved piece:
1. Coordinator call reads the config, outputs a short delegation plan tailored to what's
   actually present in it.
2. Three worker calls run in parallel using the coordinator's per-worker instructions.
3. Synthesis call merges the three outputs into one prioritized report.

This is the piece that earns the name "coordinator" rather than just being pattern 2 with
extra steps — worth the extra time, since it's the concept most likely to matter for the
CCAR-F exam.

### Phase 6 — compare.py (~30-45 min) ✅ done
Wrap each pipeline call in `time.perf_counter()`, sum `usage.input_tokens` /
`usage.output_tokens` across calls, print a comparison table. Run all three against the
same input config.

## Results

`compare.py` run against `sample_configs/basic_router.cfg`:

```
pipeline     calls  elapsed (s)  in tokens  out tokens  total tokens
--------------------------------------------------------------------
sequential       3        63.63       5748        5854         11602
parallel         3        25.48       3847        5711          9558
coordinator      5        62.09      12061        9758         21819
```

- **Parallel is ~2.5x faster than sequential** for the same three concerns, and cheaper too
  (troubleshooting isn't paying for the extra `security_findings` context) — the fan-out/fan-in
  payoff shows up exactly where you'd expect for three independent concerns.
- **Coordinator's wall-clock time lands close to sequential's**, not parallel's, even though its
  three workers run concurrently — it has two more calls (delegation, synthesis) bookending that
  parallel core, and those can't overlap with anything.
- **Coordinator is the most expensive pipeline by tokens** (~2.3x parallel) — mostly the synthesis
  call's input, which has to ingest all three workers' full output text to merge them.
- The tradeoff: parallel wins on speed and cost when the three concerns are genuinely independent;
  coordinator spends more time and tokens in exchange for per-worker instructions tailored to
  what's actually in the config, and one prioritized report instead of three raw ones.

## Notes on models

All three pipelines currently use Claude Sonnet 5 for every call (workers included), rather than
mixing in Haiku 4.5 for workers as originally planned — kept deliberately consistent across
pipelines so the latency/token comparison in `compare.py` reflects the orchestration pattern
itself, not a model-choice difference. Swapping workers to Haiku 4.5 would be a reasonable next
experiment, but the two shouldn't be changed in the same comparison run.

## Next test config ideas (once the basic version works)

- A config with no ACLs at all (tests whether the security worker/coordinator notices an
  *absence*, not just flags bad rules).
- A config with a misconfigured VLAN (tests whether the troubleshooting worker catches a
  real error vs. general advice).
