"""Deterministic exposed-secret / API-key detector (non-AI).

Scans PUBLIC page content (HTML, inline scripts, JSON) for credentials that a
site has accidentally published: cloud keys, tokens, private keys, connection
strings, etc. This is an OSINT / defensive-security surface — it tells you which
credentials are *leaking in public*, so you (the admin) can react.

Safety design:
- The raw secret is NEVER stored. We return a MASKED form (first/last chars) and
  a sha256 fingerprint (for dedup), plus a short surrounding context snippet.
- Detection is pure regex + light entropy checks: fully deterministic and
  explainable (identical input -> identical output).
- The pipeline routes findings into an admin-only Discord channel / API scope.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

# (name, severity, compiled pattern). Patterns match the SECRET itself (group 0
# or the first capturing group when present).
_RULES: list[tuple[str, str, re.Pattern[str]]] = [
    ("aws_access_key_id", "high",
     re.compile(r"\b(AKIA|ASIA|AGPA|AIDA|AROA|ANPA)[0-9A-Z]{16}\b")),
    ("aws_secret_access_key", "high",
     re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*['\"]?([A-Za-z0-9/+=]{40})")),
    ("google_api_key", "high", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    ("google_oauth_client", "medium", re.compile(r"\b[0-9]+-[0-9a-z_]{32}\.apps\.googleusercontent\.com\b")),
    ("gcp_service_account", "high", re.compile(r'"type"\s*:\s*"service_account"')),
    ("stripe_secret_key", "high", re.compile(r"\bsk_live_[0-9a-zA-Z]{24,}\b")),
    ("stripe_restricted_key", "high", re.compile(r"\brk_live_[0-9a-zA-Z]{24,}\b")),
    ("github_pat", "high", re.compile(r"\bghp_[0-9A-Za-z]{36}\b")),
    ("github_fine_grained_pat", "high", re.compile(r"\bgithub_pat_[0-9A-Za-z_]{60,}\b")),
    ("github_oauth", "high", re.compile(r"\bgho_[0-9A-Za-z]{36}\b")),
    ("slack_token", "high", re.compile(r"\bxox[baprs]-[0-9A-Za-z-]{10,48}\b")),
    ("slack_webhook", "medium", re.compile(r"https://hooks\.slack\.com/services/[A-Za-z0-9/]{40,}")),
    ("discord_bot_token", "high", re.compile(r"\b[MNO][A-Za-z0-9_-]{23,25}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,38}\b")),
    ("discord_webhook", "medium", re.compile(r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/[0-9]{17,20}/[A-Za-z0-9_-]{60,}")),
    ("twilio_account_sid", "medium", re.compile(r"\bAC[0-9a-fA-F]{32}\b")),
    ("sendgrid_key", "high", re.compile(r"\bSG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}\b")),
    ("openai_key", "high", re.compile(r"\bsk-[A-Za-z0-9]{20}T3BlbkFJ[A-Za-z0-9]{20}\b")),
    ("openai_project_key", "high", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b")),
    ("anthropic_key", "high", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("mailgun_key", "high", re.compile(r"\bkey-[0-9a-zA-Z]{32}\b")),
    ("jwt", "medium", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("private_key_block", "high", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("db_connection_string", "high", re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s'\"<>]+:[^\s'\"<>@]+@[^\s'\"<>]+")),
    ("basic_auth_url", "medium", re.compile(r"\bhttps?://[^\s/'\"<>:@]+:[^\s/'\"<>@]{4,}@[^\s'\"<>]+")),
    ("bearer_token", "low", re.compile(r"(?i)\bbearer\s+([A-Za-z0-9\-_.=]{20,})")),
    ("generic_api_key_assignment", "low",
     re.compile(r"(?i)\b(?:api[_-]?key|apikey|secret|access[_-]?token|auth[_-]?token|client[_-]?secret)\b\s*[=:]\s*['\"]([A-Za-z0-9\-_./+=]{16,})['\"]")),
]

# What each key class unlocks — static knowledge, so we can tell the admin
# "this leaked key is company X's and would expose Y" WITHOUT ever sending the
# key anywhere. This is the safe "connect the key to the data" intelligence.
_PROVIDER_INFO: dict[str, tuple[str, str]] = {
    "aws_access_key_id": ("AWS", "s3/ec2/iam and anything the key's IAM policy allows"),
    "aws_secret_access_key": ("AWS", "paired secret for an AWS access key"),
    "google_api_key": ("Google", "maps/places/other google apis the key is scoped to"),
    "google_oauth_client": ("Google", "oauth client identity for a google app"),
    "gcp_service_account": ("Google Cloud", "gcp resources the service account can reach"),
    "stripe_secret_key": ("Stripe", "payments, customers, charges, payouts"),
    "stripe_restricted_key": ("Stripe", "scoped stripe resources per the restricted key"),
    "github_pat": ("GitHub", "private repos + org data per the token scope"),
    "github_fine_grained_pat": ("GitHub", "scoped repos/org data per the fine-grained token"),
    "github_oauth": ("GitHub", "github account data per the oauth scope"),
    "slack_token": ("Slack", "workspace messages, files, users"),
    "slack_webhook": ("Slack", "post messages into a slack channel"),
    "discord_bot_token": ("Discord", "control a bot: read/post in its servers"),
    "discord_webhook": ("Discord", "post messages into a discord channel"),
    "twilio_account_sid": ("Twilio", "sms/voice, phone numbers, billing"),
    "sendgrid_key": ("SendGrid", "send email + contacts"),
    "openai_key": ("OpenAI", "llm api usage billed to the owner"),
    "openai_project_key": ("OpenAI", "project-scoped llm api usage billed to the owner"),
    "anthropic_key": ("Anthropic", "llm api usage billed to the owner"),
    "mailgun_key": ("Mailgun", "send email + logs"),
    "jwt": ("JWT", "a session/identity per its claims"),
    "private_key_block": ("PKI", "tls/ssh identity: decrypt or sign as the owner"),
    "db_connection_string": ("Database", "direct read/write access to the database"),
    "basic_auth_url": ("HTTP Basic", "the endpoint the embedded credentials authenticate"),
    "bearer_token": ("Bearer", "the api the bearer token authenticates"),
    "generic_api_key_assignment": ("Generic", "the service this api key/secret authenticates"),
}


def provider_info(secret_type: str) -> tuple[str, str]:
    return _PROVIDER_INFO.get(secret_type, ("Unknown", "an unidentified service"))


# Substrings that mark an obvious placeholder / example -> ignored (low noise).
_PLACEHOLDERS = (
    "your_", "example", "changeme", "xxxx", "0000000000", "placeholder",
    "<your", "dummy", "test_key", "sample", "redacted", "replace-me",
    "abcdef123456", "1234567890",
)


@dataclass
class Secret:
    secret_type: str
    masked: str
    fingerprint: str
    context: str
    severity: str
    raw: str | None = None          # uncensored value; only set when kept

    @property
    def provider(self) -> str:
        return provider_info(self.secret_type)[0]

    @property
    def unlocks(self) -> str:
        return provider_info(self.secret_type)[1]

    def as_dict(self, *, include_raw: bool = False) -> dict:
        d = {
            "type": self.secret_type,
            "masked": self.masked,
            "fingerprint": self.fingerprint,
            "context": self.context,
            "severity": self.severity,
            "provider": self.provider,
            "unlocks": self.unlocks,
        }
        if include_raw and self.raw is not None:
            d["raw"] = self.raw
        return d


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    counts: dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def _mask(raw: str) -> str:
    raw = raw.strip()
    if len(raw) <= 10:
        return raw[:2] + "…"
    return f"{raw[:4]}…{raw[-4:]} ({len(raw)} chars)"


def _fingerprint(raw: str) -> str:
    return "sha256:" + hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:32]


def _looks_placeholder(raw: str) -> bool:
    low = raw.lower()
    return any(p in low for p in _PLACEHOLDERS)


def scan_secrets(text: str, *, max_findings: int = 50,
                 keep_raw: bool = False) -> list[Secret]:
    """Return de-duplicated exposed-secret findings in ``text`` (deterministic).

    ``keep_raw`` retains the uncensored value on ``Secret.raw`` so an admin-only
    surface can show it. Off by default: the masked value is always what's used
    for context and any non-admin path.
    """
    if not text:
        return []
    findings: list[Secret] = []
    seen: set[str] = set()
    for name, severity, pat in _RULES:
        for m in pat.finditer(text):
            raw = m.group(1) if m.groups() else m.group(0)
            if not raw:
                continue
            raw = raw.strip().strip("'\"")
            if _looks_placeholder(raw):
                continue
            # entropy gate for the noisy generic/bearer rules (avoid plain words)
            if name in ("generic_api_key_assignment", "bearer_token"):
                if len(raw) < 16 or _entropy(raw) < 3.0:
                    continue
            fp = _fingerprint(raw)
            if fp in seen:
                continue
            seen.add(fp)
            start = max(0, m.start() - 30)
            end = min(len(text), m.end() + 20)
            ctx = re.sub(r"\s+", " ", text[start:end]).strip()
            # scrub the raw secret out of the stored context (context stays masked
            # even when uncensored storage is on; the raw value lives in .raw)
            ctx = ctx.replace(raw, _mask(raw))
            findings.append(Secret(name, _mask(raw), fp, ctx[:200], severity,
                                   raw=raw if keep_raw else None))
            if len(findings) >= max_findings:
                return findings
    return findings
