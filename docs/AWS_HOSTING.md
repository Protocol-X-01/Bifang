# AWS hosting path

The owner selected AWS as an alternative to LangSmith managed deployment on
October 24, 2026, reporting existing credits and a separate medical application.
Read-only STS identity and EC2 network-metadata checks subsequently succeeded in
`us-east-1` using the owner-designated private configuration. Account identifiers
and credentials were withheld. The owner's subsequent AWS CLI login was verified
against the same account; active-plan and remaining-credit metadata were read
privately. No account keys are copied to the host. A restricted instance role
provides management access and reads only Bifang's artifact/parameter namespace.
Do not reuse or modify the medical application's resources or data, and do not
copy its credentials into Bifang's source, deployment image or phone clients.

LangSmith tracing is independent of hosting. The replacement key in the private
configuration returned HTTP 200 for a read-only project metadata request; this
does not establish deployment entitlement. LangSmith Plus is not required for
running Bifang's own authenticated service on AWS.

## Initial persistent service

An [October 28 external check](evidence/hosted-readiness-20261028.json) confirms
trusted HTTPS, healthy review/coding workers, judge access to both schemas and
Nebius model discovery, and rejection of missing or incorrect credentials. One
judge-authenticated synthetic Nemotron Nano review completed using 298 tokens.
After the owner refreshed AWS sign-in, a [renewal follow-up](evidence/hosted-renewal-20261028.json)
confirmed the timer is enabled and active, its last run succeeded, and the public
endpoint serves a renewed, default-trusted certificate expiring November 4 at
03:27:36 UTC. This supersedes the earlier October 31 expiry observation. Funding
through judging and full paired coding-workflow acceptance remain separate checks.

`deploy/Dockerfile.remote` packages the authenticated review worker separately
from the desktop filesystem server. It uses the existing locked Python 3.11
dependencies, a non-root UID and a private state directory. No provider keys,
client tokens, local `.env`, GPU packages, shell tools or desktop API endpoints
are added to this service image. Build from the repository root:

```sh
docker build -f deploy/Dockerfile.remote -t bifang-remote:validation .
```

The recipe built and passed [exact-image runtime checks](evidence/remote-container.json)
in a disposable Ubuntu 24.04 Docker builder: non-root/read-only execution,
authentication, other-owner isolation, idempotency, container restart and actual
backup-command recovery. The credential-free fixture deliberately produced a
failed review receipt; this does not replace live inference or AWS host-restart
proof. The temporary VM, writable disk and key were removed. No image was
uploaded during that local test. Resolved base-image digests are
recorded in the receipt; the recipe's tags can change on future builds.

## Current AWS preparation

The isolated `bifang-remote-host` bootstrap stack reached `CREATE_COMPLETE`, and
its Systems Manager agent reported Online. It uses a small CPU instance,
encrypted 16-GiB root disk and separate retained encrypted 20-GiB state volume.
SSH and the worker port are not publicly exposed. The exact screened source snapshot
was uploaded to its private TLS-only artifact bucket for an on-host image build.
The on-host source checksum and image build passed. Its image reports Python
3.11.17 and SQLite 3.46.1; this preserves the desktop project's Python <3.12
constraint without installing TensorRT or provisioning GPUs on the API host.
The stable-address update then completed without replacing that instance.
Actual API reads verified IMDSv2 and encrypted 16/20-GiB disks in use. The pinned
image now runs under systemd, with a healthy worker bound to loopback. Only the
provider keys and client-token hash registry were stored as encrypted SSM
parameters; the host retrieves them with its restricted role. The temporary
runtime environment file is removed after readiness. Plaintext client tokens
and AWS account keys were not uploaded.

The challenge-only nginx listener passed its on-host syntax and HTTP-404 checks.
An add-only change set enabled ports 80/443 without replacing the instance;
HTTP does not proxy the API. Trusted public-IP HTTPS now passes external
default-trust verification, missing/wrong-token rejection, other-owner
read/cancel/delete isolation and idempotent submission. One synthetic Nano
review succeeded, reporting 335 tokens with matching requested/reported model
IDs. It remains unverified model analysis; no tools or private source were used.

Staging and production IP certificates were issued, and the renewal dry-run
succeeded. The installed twice-daily randomized systemd timer uses a pinned
Certbot image; the real renewal unit also passed after disabling Certbot's
second internal random delay. This avoids exceeding the unit's timeout.
Both nginx and the app emit a single non-cacheable response policy.

A real online backup on the encrypted state volume passed integrity checks.
An isolated, network-disabled restore recovered the exact completed analysis,
owner isolation and idempotency without another provider call. An actual host
reboot changed the kernel boot identity and preserved the completed live
receipt, trusted HTTPS, renewal timer and ephemeral-config cleanup. Recovery
made no provider calls. See the [hosted evidence receipt](evidence/aws-hosted-review.json).
That receipt identifies the earlier review-only image. The later
[coding promotion receipt](evidence/aws-public-coding.json) identifies the exact
privately tested image now serving both review and coding over the same HTTPS
origin, with the previous receipt preserved.

IP certificates are short-lived and require functioning renewal throughout
judging; an enabled timer is not proof of future availability. See
[Let's Encrypt's IP-certificate guidance](https://letsencrypt.org/2026/03/11/shorter-certs-certbot).

The source template also prepares a stable Elastic IP and explicitly opt-in
80/443 ingress. Keep `EnableHttpsIngress=false` until the HTTP listener serves
only certificate challenges and the authenticated HTTPS service is prepared.
Do not expose port 8125, SSH or the Docker daemon. No domain registration is
required for the selected public-IP HTTPS path.

AWS's regional pricing API returned $0.0208/hour for Linux `t3.small` and
$0.08/GB-month for baseline gp3 storage. With one $0.005/hour public IPv4 address
and 36 GiB of disks, a 30-day-month estimate is $0.7152/day before credits,
traffic, object storage, logs, model use and taxes. Standard CPU-credit mode
avoids Unlimited surplus-credit charges; it does not promise sustained burst
performance. Stopping compute does not stop retained-disk/IP/storage charges.
Review availability through judging rather than deleting the service at the
submission deadline; no automatic deletion has been scheduled.

An [October 28 cost refresh](evidence/judging-host-cost-20261028.json) verified
the running `t3.small`, Standard CPU-credit mode and 36 GiB of attached gp3
storage. The regional Pricing API returned the same compute/storage rates.
From that check through December 15 at 20:00 UTC, the base estimate is $34.51,
or $51.76 with a 50% buffer. This excludes inference, traffic, logs, object
storage, taxes and other account workloads. Private account credit metadata
was checked separately; credit expiry and service eligibility remain unverified.

[Public IPv4 pricing](https://aws.amazon.com/vpc/pricing/),
[EBS pricing](https://aws.amazon.com/ebs/pricing/),
[Free Tier plan metadata](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_freetier_GetAccountPlanState.html).

The first deployment should use an isolated Bifang stack with a single worker
host and an encrypted, locally mounted persistent volume. Bind the container
port only to loopback or a private load-balancer target, terminate HTTPS and
provide the client-token hash registry and provider credentials through a
separate runtime secret configuration. Keep all Linux capabilities dropped,
the application filesystem read-only and a bounded writable temporary mount.
The state mount must be writable by UID 10001 with mode 0700. Do not mount the
host Docker socket or unrelated project directories.

This is a single-host first deployment, not an availability or scale claim.
SQLite WAL needs same-host access and must not be placed on an EFS/NFS shared
filesystem. For multiple service replicas, replace the store with a reviewed
transactional server database and rerun lease/idempotency/owner-isolation tests.
Fargate's normal task disk is ephemeral; simply moving this container there
would not preserve its jobs through replacement.

## Account and deployment gates

1. Select the intended AWS account/profile and region; confirm identity without
   publishing account identifiers or credentials. Prefer temporary SSO access.
2. Verify remaining credits, expiry and eligible services in Billing; credits
   are not a guarantee that all charges are covered. Estimate the selected
   region's instance, disk, public IPv4, TLS ingress, logs and backup costs.
3. Use isolated Bifang IAM roles, tags, network rules and secrets. Require IMDSv2
   if using EC2. Prefer Systems Manager management over public SSH ingress.
4. Before exposing the service, validate TLS, wrong/missing bearer rejection,
   two-owner isolation, duplicate submission, cancellation and runtime health.
5. Prove job/result survival through actual process and host restart. Restore a
   database backup through SQLite's backup API and verify the restored receipt;
   copying only a live WAL database file is not a complete backup procedure.
6. Add operational request/body/concurrency limits, log retention, monitoring,
   rollback and cleanup instructions. Redact source, answers and credentials
   from logs. Only then connect native mobile clients.

## Consistent backup and recovery

The operator-only backup command uses SQLite's online backup API, verifies the
snapshot and publishes a new mode-0600 file without overwriting an existing
backup. In the exported snapshot only, pending/running jobs are marked
`interrupted` and their source cleared, preventing automatic model replay after
restore. The active database and worker are not changed. Those requests require
a new explicit submission after recovery. Create a separate owner-only backup
directory first, then run:

```sh
python -m bifang.remote_backup --state /var/lib/bifang --destination /private-backups/review-jobs-001.sqlite3
```

Do not place backups in web-served paths or source control. They contain retained
reviews and may retain older source bytes, so need encryption and a retention policy. This
command provides no remote download endpoint. It does not back up provider
credentials, client-token registries or the rest of the host configuration.

For recovery, stop the service and choose a new, private state directory. Copy
the snapshot to `review-jobs.sqlite3`, set the service UID and mode 0600, then
start the service with the restored directory. Never replace just the database
under an active worker or combine a snapshot with stale `-wal`/`-shm` files.
The tests recover a completed receipt, its idempotency key and owner isolation
from a snapshot taken while another database connection remains open. A restored snapshot
can lack newer requests and tombstones: reconcile that recovery gap before
accepting retries. This is not a zero-data-loss or exactly-once billing claim.

The local Python runtime reports SQLite 3.50.4. Upstream identifies a rare
[WAL-reset corruption bug](https://www.sqlite.org/wal.html#walreset) fixed in
3.51.3 and the 3.50.7/3.44.6 backport branches. The remote store now selects
rollback journaling on other version ranges, rather than enabling WAL on an
unverified runtime. This is a local compatibility safeguard, not a claim that
corruption was observed. Check the deployed image's actual SQLite version too.

## Full requested remote workflow

The deployed coding API now integrates selected-source proposals, durable
approval decisions, independent gVisor execution, patch review, staging and
separate hosted-snapshot Apply. The real private chain and public promotion
have separate [evidence](REMOTE_CODING.md). User-facing client workflows remain
a separate delivery and verification gate; hosted Apply is not desktop Git Apply.
Model credentials belong to the control service, not to sandboxes executing
untrusted project code. Never expose the desktop filesystem API directly as a
shortcut. iOS and Android builds and device walkthroughs remain separate gates.

## Research and alternatives

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview):
  open-source orchestration is separate from LangSmith managed deployment.
- [AWS storage options](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/using_data_volumes.html)
  and [Fargate ephemeral storage](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/fargate-task-storage.html).
- [SQLite WAL requirements](https://www.sqlite.org/wal.html).
- [Systems Manager Session Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager.html).
- [AWS credit details](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/useconsolidatedbilling-credits.html).

The earlier isolated Vercel Workflows prototype compiled locally but was not
deployed or connected to inference. The existing team was verified as active
Hobby; no upgrade or new project was created. Workflows has included Hobby
allowances, but completed payloads are readable for only one day on that plan.
Its default step retries and non-atomic start deduplication also need explicit
handling before billed inference or Apply. AWS was selected before that probe
progressed to a deployment. The existing Vercel judge relay remains unchanged.
See [Workflow pricing](https://vercel.com/docs/workflows/pricing),
[retention](https://vercel.com/docs/workflows/retention) and the SDK's
[idempotency](https://workflow-sdk.dev/docs/foundations/idempotency) guidance.
