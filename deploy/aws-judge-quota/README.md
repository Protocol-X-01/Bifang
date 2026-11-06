# Shared public-demo allowance

The Vercel relay reserves each public completion through this authenticated
counter before calling Token Factory. A DynamoDB transaction updates the
persistent global allowance, global minute bucket and three client buckets atomically. All Vercel
instances use the same table. Expired access, denied reservations and service
failures do not reach the inference provider.

The counter receives a request ID, requested output-token count, input-body
size and a keyed client digest. The relay groups IPv4 addresses individually and
IPv6 addresses by /64, then applies HMAC-SHA256 with its quota secret. The counter
receives neither raw visitor addresses nor model prompts, answers or provider credentials. Completed,
cancelled and failed upstream attempts keep their reservation, so uncertain
network results cannot refund capacity incorrectly. An allowance is shared
across visitors and persists through deployments.

## Deploy

Render the credential-free CloudFormation template:

```bash
python deploy/aws-judge-quota/template.py --output /private/bifang-quota-template.json
```

Create or update a `bifang-public-demo-quota-v2` stack using that template, with
`CAPABILITY_NAMED_IAM` and a strong owner-generated `QuotaSecret` parameter.
Supply secrets through an owner-only AWS CLI input file or the AWS console;
the parameter is `NoEcho`. The template creates one on-demand DynamoDB table,
a Python 3.12 Lambda function, a role scoped to transactional updates on that
table, and a seven-day log group. Function URL requests use the handler's bearer
authentication; no AWS access key is transferred to Vercel.

Initialize the `pk=budget` item once with numeric `requests`, `output_tokens`
and `input_bytes` set to zero and `expires_at` set to the configured UTC expiry's
Unix timestamp. Use `attribute_not_exists(pk)` so an existing allowance cannot
be reset accidentally. Missing or malformed budget state fails closed. Only
client and minute buckets have a `ttl` attribute; the global counter is retained.

When migrating the original counter, set `CreateBudgetTable=false` and
`BudgetTableName` to its existing table. Keep its `pk=budget` counters intact.
Deploy protocol 2 under the new function/stack name, with its own secret, before
changing the relay's quota URL and secret. The original live relay continues
using its original function until the new deployment is verified and promoted.
Protocol 2 rejects requests missing the client key or version header; there is
no legacy reservation path that bypasses client limits.

Set `BIFANG_PUBLIC_QUOTA_URL` from the stack's `QuotaUrl` output and the matching
`BIFANG_PUBLIC_QUOTA_TOKEN` as a server-side Vercel secret. Keep
`BIFANG_JUDGE_PUBLIC_ACCESS=1` and the existing provider secret/expiry settings.
Deploy the five-module relay bundle, verify access and one small completion,
then promote it.

Default stack parameters allow 1,000 reservations, 4,000,000 requested output
tokens and 16 MiB of input bodies, at 60 reservations per minute. Each client
group has a lifetime allowance of 250 requests, 1,000,000 requested output tokens
and 4 MiB input, plus a UTC-day allowance of 100 requests, 262,144 requested
output tokens and 2 MiB input, at 10 requests per minute. A five-item transaction
reserves all limits together; denied requests consume none of those counters.

Minute limits return 429 with a bounded `Retry-After`. Exhausted global/client
allowances return 403 without `Retry-After`; the daily response includes its UTC
midnight reset. Unavailable or malformed state returns 503. Review usage
before increasing these parameters. This bounds request volume rather than
promising a fixed dollar bill across models. The existing Vercel firewall
observation rule remains independent of the enforced counter.

On Vercel the relay trusts only its platform-overwritten `X-Forwarded-For` header,
and rejects missing, duplicate or chained values. Elsewhere it uses the direct
peer address and ignores forwarded headers. IP grouping is a fair-use control:
visitors sharing a network share an allowance, and changing networks can produce
another client group. The global limit still applies across all groups.

The table has a retain policy. Deleting a stack preserves its counters; an
operator must deliberately handle that table during eventual cleanup.

Primary references: [DynamoDB transaction permissions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html)
and [Lambda Function URL permissions](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html).
Vercel documents its [overwritten client-address headers](https://vercel.com/docs/headers/request-headers#x-forwarded-for).
