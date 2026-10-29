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

## Read a selected page

The current source also registers `web_extract` with one `url` argument. After
finding documentation, the agent can request its exact HTTPS page through
Tavily Extract. The action uses the same approval policy as search. It does not
add extraction to read-only team or isolated implementation capabilities.

Each call sends one URL, uses basic extraction with a 15-second provider timeout,
and caps the total operation at 25 seconds. Response bodies are limited to 1 MB;
retained content to 12,000 characters. Results carry their content hash, truncation
flag and untrusted-data label. Only the selected URL's result is accepted;
partial failures return an unavailable-page result without exposing provider errors.
There are no automatic retries or depth upgrades.

URLs must use HTTPS with an ordinary hostname and no user credentials or fragment.
IP literals, local-style hostnames and nonstandard ports are rejected. The local
client contacts Tavily's fixed API origin; Tavily retrieves the selected page.
Choose public links without private access tokens in their query strings.

An [October 28 live check](evidence/tavily-extract-20261028.json) retained 5,944
characters from Python's public asyncio documentation. The focused search,
extraction, agent-action and approval/tool suites pass 83 tests. This is current
source evidence; existing installed binaries and the hosted service do not gain
the tool until rebuilt and deployed.

Crawling, mapping and automated research remain separate pending tools.

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
Extraction: [Tavily Extract API](https://docs.tavily.com/documentation/api-reference/endpoint/extract).
