"""Authentication and role-based access control.

Roles map to permissions, permissions guard endpoints, and the lower roles see
redacted records rather than a blanket refusal — an analyst can study crime
patterns without being handed every accused person's name and address, which is
the distinction that matters in a policing system.

Implemented on the standard library: PBKDF2-HMAC-SHA256 for passwords and an
HMAC-signed session token. No crypto is hand-rolled and no extra dependency is
pulled in for a hackathon deployment to get wrong.

Sessions are httpOnly cookies rather than a token in localStorage, so a script
injected into the dashboard cannot read them.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ── Permissions ────────────────────────────────────────────────────────────

FIR_READ = "fir:read"                 # list and open FIRs (redacted if no :pii)
FIR_READ_PII = "fir:read_pii"         # see accused/victim identities and addresses
FIR_INGEST = "fir:ingest"             # upload new FIR batches
ANALYTICS_READ = "analytics:read"     # dashboard, trends, stations, networks
OFFENDER_READ = "offender:read"       # repeat offender profiles
ASSISTANT_USE = "assistant:use"       # the AI assistant
REPORT_GENERATE = "report:generate"   # intelligence reports
ADMIN_USERS = "admin:users"           # create/disable accounts

ALL_PERMISSIONS = frozenset({
    FIR_READ, FIR_READ_PII, FIR_INGEST, ANALYTICS_READ,
    OFFENDER_READ, ASSISTANT_USE, REPORT_GENERATE, ADMIN_USERS,
})

#: Role definitions, least privilege upwards. A role is a named permission set;
#: endpoints never check the role directly, only the permission, so adding a
#: role never requires touching a route.
ROLES: dict[str, dict] = {
    "viewer": {
        "label": "Viewer",
        "description": "Read-only dashboards and statistics. FIR identities are "
                       "redacted; no assistant, reports or ingestion.",
        "permissions": frozenset({FIR_READ, ANALYTICS_READ}),
    },
    "analyst": {
        "label": "Crime Analyst",
        "description": "Full analytics, offender profiles, assistant and reports. "
                       "Personal identifiers in FIRs stay redacted.",
        "permissions": frozenset({FIR_READ, ANALYTICS_READ, OFFENDER_READ,
                                  ASSISTANT_USE, REPORT_GENERATE}),
    },
    "investigator": {
        "label": "Investigating Officer",
        "description": "Everything an analyst sees, plus the identities of "
                       "accused and victims.",
        "permissions": frozenset({FIR_READ, FIR_READ_PII, ANALYTICS_READ,
                                  OFFENDER_READ, ASSISTANT_USE, REPORT_GENERATE}),
    },
    "supervisor": {
        "label": "Station Supervisor",
        "description": "Investigator access plus ingesting new FIR batches.",
        "permissions": frozenset(ALL_PERMISSIONS - {ADMIN_USERS}),
    },
    "admin": {
        "label": "System Administrator",
        "description": "Full access including account management.",
        "permissions": frozenset(ALL_PERMISSIONS),
    },
}

ROLE_ORDER = ["viewer", "analyst", "investigator", "supervisor", "admin"]


def permissions_for(role: str) -> frozenset[str]:
    entry = ROLES.get(role)
    return entry["permissions"] if entry else frozenset()


# ── Password hashing ───────────────────────────────────────────────────────

PBKDF2_ROUNDS = int(os.getenv("FIR_PBKDF2_ROUNDS", "240000"))
_MIN_PASSWORD_LENGTH = 10


def hash_password(password: str, *, salt: bytes | None = None,
                  rounds: int = PBKDF2_ROUNDS) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
    except (ValueError, TypeError):
        return False
    # Constant time: a timing difference here leaks whether a prefix matched.
    return hmac.compare_digest(expected.hex(), digest_hex)


def password_problems(password: str) -> list[str]:
    """Policy checks, returned as a list so the UI can show all of them."""
    problems = []
    if len(password) < _MIN_PASSWORD_LENGTH:
        problems.append(f"must be at least {_MIN_PASSWORD_LENGTH} characters")
    if not any(c.islower() for c in password):
        problems.append("must contain a lowercase letter")
    if not any(c.isupper() for c in password):
        problems.append("must contain an uppercase letter")
    if not any(c.isdigit() for c in password):
        problems.append("must contain a digit")
    return problems


# ── Session tokens ─────────────────────────────────────────────────────────

SESSION_TTL_SECONDS = int(os.getenv("FIR_SESSION_TTL", str(8 * 3600)))
COOKIE_NAME = "fir_session"

_secret_from_env = os.getenv("FIR_SECRET_KEY", "").strip()
#: Without a configured secret, sessions are signed with a per-process key, so
#: everyone is logged out on restart. That is the safe default: a shipped
#: fallback secret would let anyone forge a session against any deployment.
SECRET_KEY = (_secret_from_env or secrets.token_urlsafe(48)).encode()
SECRET_IS_EPHEMERAL = not _secret_from_env


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_token(username: str, role: str, ttl: int = SESSION_TTL_SECONDS) -> str:
    payload = {"sub": username, "role": role,
               "exp": int(time.time()) + ttl,
               "jti": secrets.token_urlsafe(8)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(SECRET_KEY, body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(signature)}"


def read_token(token: str) -> dict | None:
    """Return the payload of a valid, unexpired token, else ``None``."""
    try:
        body, signature = token.split(".", 1)
        expected = hmac.new(SECRET_KEY, body.encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _unb64(signature)):
            return None
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


# ── User store ─────────────────────────────────────────────────────────────


@dataclass
class User:
    username: str
    password_hash: str
    role: str
    full_name: str = ""
    station: str = ""
    district: str = ""
    active: bool = True
    must_change_password: bool = False
    created_at: str = field(default_factory=lambda:
                            datetime.now(timezone.utc).isoformat())
    last_login: str | None = None

    @property
    def permissions(self) -> frozenset[str]:
        return permissions_for(self.role)

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def public(self) -> dict:
        role = ROLES.get(self.role, {})
        return {
            "username": self.username,
            "full_name": self.full_name,
            "role": self.role,
            "role_label": role.get("label", self.role),
            "role_description": role.get("description", ""),
            "station": self.station,
            "district": self.district,
            "active": self.active,
            "must_change_password": self.must_change_password,
            "permissions": sorted(self.permissions),
            "last_login": self.last_login,
            "created_at": self.created_at,
        }


#: Demo accounts, created on first boot when the store is empty.
#: Passwords are intentionally published in the README — this is a
#: demonstration deployment, not a production one. `using_demo_credentials()`
#: reports whether any are still in place so the app can warn loudly.
DEMO_ACCOUNTS = [
    ("admin", "Admin@FIR2024", "admin", "Arjya Ghosh", "HQ", "Lucknow"),
    ("supervisor", "Super@FIR2024", "supervisor", "SHO Hazratganj", "Hazratganj PS", "Lucknow"),
    ("investigator", "Invest@FIR2024", "investigator", "IO R. Verma", "Gomti Nagar PS", "Lucknow"),
    ("analyst", "Analyst@FIR2024", "analyst", "Crime Analyst", "District Crime Bureau", "Lucknow"),
    ("viewer", "Viewer@FIR2024", "viewer", "Duty Officer", "Control Room", "Lucknow"),
]

_users: dict[str, User] = {}
#: username -> (consecutive failures, locked-until timestamp)
_failures: dict[str, tuple[int, float]] = {}
MAX_FAILED_ATTEMPTS = int(os.getenv("FIR_MAX_LOGIN_ATTEMPTS", "5"))
LOCKOUT_SECONDS = int(os.getenv("FIR_LOCKOUT_SECONDS", "300"))


def seed_demo_users() -> list[str]:
    """Create the demo accounts if no users exist. Returns created usernames."""
    if _users:
        return []
    created = []
    for username, password, role, full_name, station, district in DEMO_ACCOUNTS:
        _users[username] = User(
            username=username,
            password_hash=hash_password(password),
            role=role,
            full_name=full_name,
            station=station,
            district=district,
        )
        created.append(username)
    return created


def using_demo_credentials() -> list[str]:
    """Which demo accounts still have their published password."""
    return [username for username, password, *_ in DEMO_ACCOUNTS
            if (user := _users.get(username)) and verify_password(password, user.password_hash)]


def get_user(username: str) -> User | None:
    return _users.get((username or "").strip().lower())


def list_users() -> list[User]:
    return sorted(_users.values(), key=lambda u: (ROLE_ORDER.index(u.role)
                  if u.role in ROLE_ORDER else 99, u.username))


class AuthError(Exception):
    """Login refused. ``retry_after`` is set when the account is locked."""

    def __init__(self, message: str, retry_after: int | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def authenticate(username: str, password: str) -> User:
    username = (username or "").strip().lower()
    attempts, locked_until = _failures.get(username, (0, 0.0))
    now = time.time()
    if locked_until > now:
        raise AuthError("Account temporarily locked after repeated failed "
                        "attempts.", retry_after=int(locked_until - now))

    user = _users.get(username)
    # Always run a verification so a missing user and a wrong password take the
    # same time — otherwise response timing enumerates valid usernames.
    reference = user.password_hash if user else hash_password("x" * 12)
    password_ok = verify_password(password or "", reference)

    if not user or not password_ok or not user.active:
        attempts += 1
        locked = now + LOCKOUT_SECONDS if attempts >= MAX_FAILED_ATTEMPTS else 0.0
        _failures[username] = (attempts, locked)
        if user and not user.active:
            raise AuthError("This account has been disabled.")
        if locked:
            raise AuthError("Too many failed attempts. Account locked for "
                            f"{LOCKOUT_SECONDS // 60} minutes.",
                            retry_after=LOCKOUT_SECONDS)
        raise AuthError("Incorrect username or password.")

    _failures.pop(username, None)
    user.last_login = datetime.now(timezone.utc).isoformat()
    return user


def create_user(username: str, password: str, role: str, *, full_name: str = "",
                station: str = "", district: str = "") -> User:
    username = (username or "").strip().lower()
    if not username.isidentifier():
        raise ValueError("Username must be letters, digits and underscores only.")
    if username in _users:
        raise ValueError(f"User '{username}' already exists.")
    if role not in ROLES:
        raise ValueError(f"Unknown role '{role}'. Valid roles: {', '.join(ROLE_ORDER)}")
    problems = password_problems(password)
    if problems:
        raise ValueError("Password " + "; ".join(problems) + ".")

    user = User(username=username, password_hash=hash_password(password),
                role=role, full_name=full_name, station=station, district=district)
    _users[username] = user
    return user


def set_password(username: str, new_password: str) -> None:
    user = _users.get(username)
    if not user:
        raise ValueError("No such user.")
    problems = password_problems(new_password)
    if problems:
        raise ValueError("Password " + "; ".join(problems) + ".")
    user.password_hash = hash_password(new_password)
    user.must_change_password = False


def set_active(username: str, active: bool) -> User:
    user = _users.get(username)
    if not user:
        raise ValueError("No such user.")
    user.active = active
    return user


def set_role(username: str, role: str) -> User:
    if role not in ROLES:
        raise ValueError(f"Unknown role '{role}'.")
    user = _users.get(username)
    if not user:
        raise ValueError("No such user.")
    user.role = role
    return user


def reset_store() -> None:
    """Test helper — clears users and lockout state."""
    _users.clear()
    _failures.clear()


# ── Redaction ──────────────────────────────────────────────────────────────

_REDACTED = "[redacted]"


def redact_fir(payload: dict) -> dict:
    """Strip personal identifiers from an FIR for roles without FIR_READ_PII.

    Counts and structure survive so the analytics still work; only the
    identifying fields are removed. The narrative goes too — it names people
    in prose, so redacting the structured fields alone would be theatre.
    """
    redacted = dict(payload)
    redacted["text"] = ("[FIR narrative withheld — requires the "
                        "'fir:read_pii' permission]")
    redacted["text_truncated"] = False
    redacted["pii_redacted"] = True

    entities = dict(redacted.get("entities") or {})
    entities["accused"] = [
        {"name": f"Accused #{i + 1}", "aliases": [], "age": person.get("age"),
         "gender": person.get("gender"), "father_name": None,
         "address": None, "id_marks": [], "phone": None}
        for i, person in enumerate(entities.get("accused") or [])
    ]
    entities["victims"] = [
        {"name": f"Victim #{i + 1}", "age": person.get("age"),
         "gender": person.get("gender"), "occupation": person.get("occupation"),
         "address": None}
        for i, person in enumerate(entities.get("victims") or [])
    ]
    if entities.get("location"):
        location = dict(entities["location"])
        location["place"] = _REDACTED
        entities["location"] = location
    redacted["entities"] = entities

    summary = redacted.get("summary") or ""
    if "Accused:" in summary:
        head, _, tail = summary.partition("Accused:")
        _, _, rest = tail.partition(";")
        redacted["summary"] = (head + "Accused: [redacted]" +
                               (";" + rest if rest else "")).strip()
    return redacted


def redact_offender(payload: dict) -> dict:
    """An offender profile is entirely personal data — reduce it to a count."""
    return {
        "primary_name": f"Offender #{abs(hash(payload.get('primary_name', ''))) % 9000 + 1000}",
        "aliases": [],
        "linked_firs": payload.get("linked_firs", []),
        "crime_types": payload.get("crime_types", []),
        "stations": payload.get("stations", []),
        "districts": payload.get("districts", []),
        "risk_level": payload.get("risk_level"),
        "mo_signature": payload.get("mo_signature", ""),
        "fir_count": payload.get("fir_count", 0),
        "match_confidence": payload.get("match_confidence", 0),
        "first_seen": payload.get("first_seen"),
        "last_seen": payload.get("last_seen"),
        "pii_redacted": True,
        "intelligence_assessment": (
            "Identity withheld — requires the 'fir:read_pii' permission. "
            f"Linked to {payload.get('fir_count', 0)} FIRs across "
            f"{len(payload.get('districts') or [])} district(s); risk "
            f"{str(payload.get('risk_level', '')).upper()}."
        ),
    }
