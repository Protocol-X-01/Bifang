# Tavily web access

Current source routes the existing approved `web_search` tool through Tavily's
Search API. This replaces the brittle DuckDuckGo HTML scrape, not the agent
execution/approval system. No extra SDK dependency is required: the async HTTP
client already used by Bifang sends requests to `https://api.tavily.com/search`.

Set `TAVILY_API_KEY` in a private environment file outside the checkout and
point `BIFANG_ENV_FILE` there. Never put keys in URLs, model messages, mobile
bundles, screenshots or repository configuration. A missing key produces an
actionable error; it does not silently contact a different search provider.

Each call uses basic search, one request, no automatic depth upgrade, at most
eight sources, no generated answer, images or full-page content. Queries are
limited to 400 characters; response bodies to 1 MB; snippets to 4,000 characters.
Non-success responses, redirects, malformed output and errors are sanitized.
No automatic retries or alternate-provider fallback spend additional credits.

Results include titles, URLs and hashes of the retained snippets, explicitly
labelled untrusted external data. A content hash identifies returned text; it
does not prove that text is true. Tool capabilities and approval remain outside
the model. Read-only review workers and isolated implementation workers do not
gain web access merely because the parent has it.

Only the search query is sent, not an automatic repository dump. In full
approval mode an agent can request external tools without further prompts, so
use manual approval for sensitive repositories. Do not include secrets or
private source in web queries.

Extraction, crawling, mapping and research are separate pending tools, each
requiring explicit destination, cost, depth and size controls. They are not
enabled by this search integration.

## Codex integration is separate

The user-supplied `codex mcp add tavily --url https://mcp.tavily.com/mcp/` and
`codex mcp login tavily` configure this development assistant, not the shipped
Bifang app. OAuth sign-in requires the owner. This source change does not claim
that Codex MCP OAuth was installed or completed.

Mocked tests cover authentication placement, source labelling, URL filtering,
bounded parameters, missing keys and sanitized HTTP failures/redirects.
After owner permission, both the Tavily CLI and Bifang adapter returned two
live public-web sources each. The authenticated usage endpoint returned 200.
The bounded receipt is `outputs/bifang-web-services-check-20261024.json` in the
development workspace; no private source or transcripts were uploaded.
Account usage limits are not a dollar-credit balance or a deployment guarantee.

Reference: [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search).
