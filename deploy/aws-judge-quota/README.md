# Shared public-demo allowance

The Vercel relay reserves each public completion through this authenticated
counter before calling Token Factory. A DynamoDB transaction updates the
persistent global allowance and current minute bucket atomically. All Vercel
instances use the same table. Expired access, denied reservations and service
failures do not reach the inference provider.

The counter receives a request ID, requested output-token count and input-body
size. It never receives model prompts, answers or provider credentials. Completed,
cancelled and failed upstream attempts keep their reservation, so uncertain
network results cannot refund capacity incorrectly. An allowance is shared
across visitors and persists through deployments.

## Deploy

Render the credential-free CloudFormation template:

```bash
python deploy/aws-judge-quota/template.py --output /private/bifang-quota-template.json
```

Create or update a `bifang-public-demo-quota` stack using that template, with
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
minute buckets have a `ttl` attribute; the global counter is retained.

Set `BIFANG_PUBLIC_QUOTA_URL` from the stack's `QuotaUrl` output and the matching
`BIFANG_PUBLIC_QUOTA_TOKEN` as a server-side Vercel secret. Keep
`BIFANG_JUDGE_PUBLIC_ACCESS=1` and the existing provider secret/expiry settings.
Deploy the five-module relay bundle, verify access and one small completion,
then promote it.

Default stack parameters allow 1,000 reservations, 4,000,000 requested output
tokens and 16 MiB of input bodies, at 60 reservations per minute. Review usage
before increasing these parameters. This bounds request volume rather than
promising a fixed dollar bill across models. The existing Vercel firewall
observation rule remains independent of the enforced counter.

The table has a retain policy. Deleting a stack preserves its counters; an
operator must deliberately handle that table during eventual cleanup.

Primary references: [DynamoDB transaction permissions](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/transaction-apis-iam.html)
and [Lambda Function URL permissions](https://docs.aws.amazon.com/lambda/latest/dg/urls-auth.html).
