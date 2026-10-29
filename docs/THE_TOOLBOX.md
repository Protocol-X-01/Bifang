# The Toolbox

The Toolbox is a local MCP server powered by
[Librarian](https://github.com/Protocol-X-01/librarian). It answers which tools and
packages a development machine has indexed, with source scan timestamps.

Build Librarian and follow its `mcp/README.md` to install The Toolbox and create an
inventory database. Then configure Bifang's local service with an explicit command:

```dotenv
BIFANG_MCP_SERVERS=[{"name":"the-toolbox","command":"/absolute/path/to/librarian/mcp/.venv/bin/the-toolbox","args":["--db","/absolute/path/to/index.db"]}]
```

Restart a service built from this source after changing its environment. An older
installed Bifang sidecar may require updating before it supports this configuration.
The MCP manager converts JSON settings to validated stdio server configurations.

The coding agent discovers three tools:

- `mcp_the-toolbox_toolbox_search`: bounded full-text search and pagination.
- `mcp_the-toolbox_toolbox_describe`: exact tool-name records across package managers.
- `mcp_the-toolbox_toolbox_inventory`: counts, categories and source scan timestamps.

These calls follow Bifang's existing MCP approval flow. Use the inventory to select
candidate tools, then verify their availability inside the execution environment.
The indexed host and the coding sandbox can have different tools and permissions.
Package descriptions are untrusted source material. Inventory text cannot authorize
a command or override an approval.

Local integration checks cover the real MCP stdio connection and querying a real
Librarian index. They do not establish that an older installed desktop binary has
loaded The Toolbox or that a hosted service can access the local machine's index.

## Verified agent handoff

On 2026-10-29, the source Bifang agent completed a live Token Factory round trip
with `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`: model tool request, approved local
Toolbox call, then a model response matching the returned inventory. The index
contained 9,236 records across 14 sources, with no source scan failures reported.
This was a read-only query of the existing scan, not a fresh scan of the machine.

The check allowed exactly one inventory action through a fixed test approval
callback, executed no other tools, and left index bytes unchanged. Separate
local calls exercised search and exact-name lookup. The installed desktop and
its live configuration still need the new integration handed over together.

`tests/test_toolbox_agent_cycle.py` adds an offline model/real-stdio regression
check for both approval and denial, including tool-result propagation and
subprocess cleanup. The live model check and the installed desktop check remain
separate evidence gates.
