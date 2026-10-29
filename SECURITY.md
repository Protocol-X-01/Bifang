# Security Policy

## 🔒 Supported Versions

We provide security updates for the following versions:

| Version | Supported |
|---------|-----------|
| Latest release | ✅ |
| Previous release | ⚠️ (Critical only) |
| Older versions | ❌ |

## 🔒 Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to: **security@protocol-x.example.com**

Include the following information:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Any known mitigations

We will acknowledge receipt within 48 hours and provide a timeline for a fix.

## 🛡️ Safety Model

Bifang is designed with a defense-in-depth approach:

### Sandboxing
- **Disposable Git worktrees** — Original checkout untouched until explicit Apply
- **Filesystem confinement** — Tools restricted to Bifang workspace
- **Bubblewrap support** — Linux command isolation (where available)

### Approval System
- **Three approval levels** — Manual · Auto source edits · Full tool approval
- **Explicit confirmation** — Every mutation requires approval
- **Destructive patterns blocked** — In every mode

### Model Safety
- **Typed model tools** — Validated before use
- **Model routing receipts** — Requested vs reported model logged
- **Token usage tracking** — Visible token consumption

### Audit & Transparency
- **JSONL audit transcripts** — Under `.bifang/sessions`
- **Model routing receipts** — Requested vs reported model
- **Check receipts** — Bound to exact candidate SHA-256

## 🚫 Out of Scope

The following are **not** considered security vulnerabilities:

- Issues requiring physical access
- Social engineering attacks
- Vulnerabilities in third-party dependencies (report upstream)
- Denial of service from resource exhaustion (rate limits apply)
- Issues in unmaintained dependencies (we update regularly)

## 🔄 Security Updates

Security patches are released as:
- **Patch releases** for critical vulnerabilities
- **Minor releases** for moderate vulnerabilities
- Included in next regular release for low-severity issues

## 📞 Contact

- **Security Email**: security@protocol-x.example.com
- **PGP Key**: Available on request

---

*Bifang is defense in depth, not a formally verified security boundary. Use disposable VMs for hostile repositories.*