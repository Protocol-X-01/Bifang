# Mobile pairing

The owner-tested Xiaomi app renders correctly, supports keyboard entry and
transitions between orientations. Authentication is the current hosted-workflow
blocker. The selected design is **desktop-approved pairing with Authenticator
confirmation**, not independent mobile accounts.

## Connection flow

1. The phone starts a short-lived request against the chosen trusted HTTPS
   service. Its random device proof stays private to the requesting native client;
   the displayed eight-character code is for the desktop approval screen.
2. The already-connected desktop confirms that phone code with an Authenticator
   code. Existing operator authentication is required; a previously paired phone
   cannot approve another device or manage operator credentials.
3. The phone polls at the advertised interval and exchanges its private proof once
   for a subject-bound, one-hour session. The desktop can revoke that session.
   Coding still uses the existing candidate-bound approval and independent-check
   gates. Provider keys never need to be entered on the phone.

Authenticator provisioning uses a private `otpauth` QR/URI, not a QR containing a
provider key. A provisioning URI contains the authenticator verification secret
and must stay in the trusted enrollment surface, not source, chat, logs or public
artifacts. QR pairing alone is not an additional authentication factor; the
Authenticator confirmation is separate. See [OWASP MFA guidance](https://cheatsheetseries.owasp.org/cheatsheets/Multifactor_Authentication_Cheat_Sheet.html)
and [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238).
The split device/user-code interaction follows the pattern described in
[RFC 8628](https://datatracker.ietf.org/doc/html/rfc8628); Authenticator provisioning
uses the [documented key URI format](https://github.com/google/google-authenticator/wiki/Key-Uri-Format).

## Implemented local source

- Explicit opt-in through the private `BIFANG_REMOTE_AUTHENTICATORS` registry,
  mapping existing operator subjects to their already-provisioned Base32 TOTP
  credentials. An absent/empty registry leaves the pairing routes disabled.
- Five-minute requests, rate-limited initiation/approval and adaptive poll delay.
  Only device start/token/cancel POSTs are public when enabled. Existing bearer-token
  authentication remains required for all other application routes.
- RFC-vector-tested TOTP with a 30-second period and one-step clock tolerance;
  accepted counters are atomically persisted to prevent reuse after restart.
- Owner-only SQLite state containing proof/session hashes, not raw bearer tokens
  or authenticator seeds. Issuance is one-time, sessions expire, and revocation is
  owner-scoped. At most 32 active sessions are issued per subject.
- API tests cover unauthenticated approval denial, proof/token separation,
  ownership preservation, revocation and denying paired devices operator powers.

The shared desktop/companion screen now includes native phone start/poll/cancel,
desktop phone-code approval with a masked Authenticator field, session listing
and revocation. Device proofs and issued access tokens stay inside the native
process; only a public pairing code and an attempt identity reach the phone UI.
Cancellation is attempt-bound, including cancellation racing with issuance.
Disconnect revokes paired sessions; operator credentials remain unchanged.

Local tests cover cancellation after a lost exchange response, session logout,
stale cancellation, strict native reply contracts and frontend lifecycle races.
These are source checks, not proof of an authenticated physical-phone workflow.

The registry is an operator secret, not a frontend environment setting. Existing
operator subjects must be configured first. Seed provisioning/rotation and
recovery must retain their trusted operator boundary; never expose an enrolled
seed through an ordinary authenticated session or reset a factor with only the
session being strengthened.

## Private first-time enrollment

Use a trusted interactive operator terminal with the local `qrencode` utility.
Create an owner-only parent directory outside source repositories, then run:

```sh
python -m bifang.pairing_setup --subject OWNER_SUBJECT --directory /private/path/new-enrollment
```

Use an existing operator subject from the service client registry. The helper
refuses existing enrollment directories and source repositories. It creates a
private QR file, asks for a hidden Authenticator code, and saves `pairing.env`
only after confirmation. Failed confirmation removes generated material. It
does not install configuration, rotate an existing factor, contact a cloud
service or change the running application. Open the QR locally, not in chat.
Remove the provisioning image after enrollment; retain the seed configuration
only in trusted secret storage. Revoking a device session is not factor rotation.

For AWS, the optional encrypted `/bifang/remote/authenticator_registry` parameter
contains just the registry JSON, not a dotenv assignment. The runtime fetcher
validates existing subjects and fails closed on access/configuration errors;
only a genuinely missing optional parameter is ignored. The temporary native
service environment remains private and is removed after readiness. Never put
seeds, operator tokens or provider credentials in a mobile build.

## Backup and recovery

Job backups and pairing backups are separate databases. Back up both, keeping
the authenticator registry in separate trusted secret storage. With existing
owner-only source and destination directories:

```sh
python -m bifang.pairing_backup --source /private/state/device-pairing.sqlite3 --destination /private/backups/pairing.sqlite3
```

The online snapshot verifies integrity and intentionally discards device
sessions and pending pairing requests; it does not disconnect the live service.
For recovery, stop the service and invoke the same command on the trusted backup,
targeting a **new** `device-pairing.sqlite3` in a private recovery directory. Do
not directly copy an old database over a live service. Recovery advances the
Authenticator replay fence to the current time plus one step, so wait up to a
minute before approving again. Phones must re-pair. No old requests are replayed.

## Remaining delivery gates

The owner approved updating the existing AWS service and Xiaomi test app on
October 26. The exact pairing APK was updated on the phone without clearing its
data. The owner confirmed scanning the Authenticator QR. The hosted rollout
passed trusted HTTPS checks for pairing initiation/cancellation, operator access,
and coding alongside pairing. Successful phone authentication and the complete
physical-device workflow remain unverified. No public release or
Vercel change was authorized by that approval. Source/UI tests and an Android
build do not establish that authentication on the offered phone is unblocked.
Finish with the exact rebuilt APK on the offered phone and a real authenticated
remote check/review/Apply walkthrough before marking this flow delivered.
