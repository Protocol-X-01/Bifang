# Session task plans and terminal activity

`todo_write` now replaces an actual per-agent-session plan and returns the
new revision and complete list as JSON. `todo_read` returns a snapshot without
changing it. The list may contain up to 100 tasks, each with a nonempty content
string of at most 1,000 characters, an allowed status and priority. At most
one task may be in progress. Unknown fields are rejected. Validation occurs
before replacing state, so invalid updates leave the previous plan intact.
An empty list explicitly clears it.

This is planning metadata, not execution permission. Observe mode can record
a plan but cannot thereby authorize a file write or command. Plans belong to
their Agent instance, not a process-wide registry. New agents and server
restarts start with an empty plan; conversation restoration does not replay
tools or reconstruct plan state. Task descriptions can contain private data;
normal conversation/audit retention and access rules still apply.

`GET /sessions/{session_id}/tasks` provides a read-only snapshot using the
same access boundary as the session API. No new unauthenticated remote
endpoint is introduced. A dedicated native-desktop task widget is not yet
implemented.

The terminal Activity tab displays the actual plan and recent routing
receipts, rendering task/model labels literally rather than as Rich markup.
It does not expose or infer hidden chain-of-thought. Request Metrics displays
actual reported usage with receipt coverage; missing usage is shown as not
reported, not silently converted into zero. Context counts are estimates.
There is no claim of measured GPU memory, billing or throughput.

Validation: `tests/test_task_plan.py`, `tests/test_terminal_activity.py` and
the existing terminal-history regressions. These are local source/headless
UI tests, not a newly packaged native application verification.
