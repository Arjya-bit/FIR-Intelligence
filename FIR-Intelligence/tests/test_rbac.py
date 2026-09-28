"""Authentication, the role-permission matrix, and PII redaction."""

import pytest

import auth
from conftest import DEMO_LOGINS


class TestPasswordHashing:
    def test_round_trip(self):
        encoded = auth.hash_password("Correct@Horse1", rounds=1000)
        assert auth.verify_password("Correct@Horse1", encoded)
        assert not auth.verify_password("correct@horse1", encoded)

    def test_hash_is_salted(self):
        a = auth.hash_password("Same@Password1", rounds=1000)
        b = auth.hash_password("Same@Password1", rounds=1000)
        assert a != b, "identical passwords must not produce identical hashes"

    def test_plaintext_never_appears_in_the_hash(self):
        assert "Correct@Horse1" not in auth.hash_password("Correct@Horse1", rounds=1000)

    @pytest.mark.parametrize("encoded", [
        "", "garbage", "pbkdf2_sha256$notanint$aa$bb", "md5$1$aa$bb",
    ])
    def test_malformed_hashes_are_rejected_not_crashed(self, encoded):
        assert auth.verify_password("anything", encoded) is False

    @pytest.mark.parametrize("password,ok", [
        ("Str0ngEnough", True), ("short1A", False), ("alllowercase1", False),
        ("ALLUPPERCASE1", False), ("NoDigitsHere", False),
    ])
    def test_password_policy(self, password, ok):
        assert (auth.password_problems(password) == []) is ok


class TestSessionTokens:
    def test_round_trip(self):
        payload = auth.read_token(auth.issue_token("alice", "analyst"))
        assert payload["sub"] == "alice" and payload["role"] == "analyst"

    def test_tampered_payload_is_rejected(self):
        token = auth.issue_token("alice", "analyst")
        body, signature = token.split(".", 1)
        forged = auth._b64(b'{"sub":"alice","role":"admin","exp":9999999999}')
        assert auth.read_token(f"{forged}.{signature}") is None

    def test_expired_token_is_rejected(self):
        assert auth.read_token(auth.issue_token("alice", "analyst", ttl=-1)) is None

    @pytest.mark.parametrize("token", ["", "no-dot", "a.b", "...."])
    def test_malformed_tokens_are_rejected(self, token):
        assert auth.read_token(token) is None


class TestRoleModel:
    def test_every_role_grants_only_known_permissions(self):
        for role in auth.ROLE_ORDER:
            assert auth.permissions_for(role) <= auth.ALL_PERMISSIONS

    def test_privilege_increases_monotonically(self):
        """Each role in ROLE_ORDER is a superset of the one below it."""
        for lower, higher in zip(auth.ROLE_ORDER, auth.ROLE_ORDER[1:]):
            assert auth.permissions_for(lower) <= auth.permissions_for(higher), (
                f"{higher} does not include everything {lower} can do")

    def test_only_admin_manages_users(self):
        holders = [r for r in auth.ROLE_ORDER
                   if auth.ADMIN_USERS in auth.permissions_for(r)]
        assert holders == ["admin"]

    def test_unknown_role_grants_nothing(self):
        assert auth.permissions_for("superuser") == frozenset()


class TestLogin:
    def test_each_demo_account_signs_in(self, anon_client):
        for role, password in DEMO_LOGINS.items():
            res = anon_client.post("/api/auth/login",
                                   json={"username": role, "password": password})
            assert res.status_code == 200, role
            assert res.json()["user"]["role"] == role

    def test_session_cookie_is_httponly(self, anon_client):
        res = anon_client.post("/api/auth/login",
                               json={"username": "admin", "password": DEMO_LOGINS["admin"]})
        cookie = res.headers.get("set-cookie", "")
        assert "httponly" in cookie.lower(), "session must be unreadable from JS"
        assert "samesite=lax" in cookie.lower()

    def test_wrong_password_is_rejected(self, anon_client):
        res = anon_client.post("/api/auth/login",
                               json={"username": "admin", "password": "nope"})
        assert res.status_code == 401

    def test_error_does_not_reveal_whether_the_user_exists(self, anon_client):
        missing = anon_client.post("/api/auth/login",
                                   json={"username": "nosuchuser", "password": "x"})
        wrong = anon_client.post("/api/auth/login",
                                 json={"username": "admin", "password": "x"})
        assert missing.json()["detail"] == wrong.json()["detail"]

    def test_logout_clears_the_session(self, client):
        assert client.get("/api/auth/me").status_code == 200
        client.post("/api/auth/logout")
        client.cookies.clear()
        assert client.get("/api/auth/me").status_code == 401

    def test_roles_endpoint_is_public(self, anon_client):
        body = anon_client.get("/api/auth/roles")
        assert body.status_code == 200
        assert {r["role"] for r in body.json()} == set(auth.ROLE_ORDER)

    def test_lockout_after_repeated_failures(self, anon_client, monkeypatch):
        monkeypatch.setattr(auth, "MAX_FAILED_ATTEMPTS", 3)
        auth._failures.pop("analyst", None)
        for _ in range(3):
            anon_client.post("/api/auth/login",
                             json={"username": "analyst", "password": "wrong"})
        # Even the correct password is refused while locked.
        res = anon_client.post("/api/auth/login",
                               json={"username": "analyst", "password": DEMO_LOGINS["analyst"]})
        assert res.status_code == 401
        assert "locked" in res.json()["detail"].lower()
        auth._failures.pop("analyst", None)


class TestEndpointAuthorisation:
    ANONYMOUS_ALLOWED = ["/api/health", "/api/auth/roles", "/"]

    @pytest.mark.parametrize("path", [
        "/api/dashboard", "/api/firs", "/api/repeat-offenders", "/api/stations",
        "/api/networks", "/api/trends", "/api/report", "/api/filters",
        "/api/db-stats", "/api/auth/users", "/api/crime-types/theft",
    ])
    def test_protected_endpoints_reject_anonymous(self, anon_client, path):
        assert anon_client.get(path).status_code == 401

    @pytest.mark.parametrize("path", ANONYMOUS_ALLOWED)
    def test_public_endpoints_stay_public(self, anon_client, path):
        assert anon_client.get(path).status_code == 200

    def test_anonymous_cannot_chat_or_upload(self, anon_client):
        assert anon_client.post("/api/chat", json={"message": "hi"}).status_code == 401
        assert anon_client.post("/api/upload-firs", files={
            "file": ("b.json", "[]", "application/json")}).status_code == 401

    @pytest.mark.parametrize("role,path,expected", [
        # viewer: dashboards only
        ("viewer", "/api/dashboard", 200),
        ("viewer", "/api/firs", 200),
        ("viewer", "/api/repeat-offenders", 403),
        ("viewer", "/api/report", 403),
        # analyst: adds offenders, assistant, reports
        ("analyst", "/api/repeat-offenders", 200),
        ("analyst", "/api/report", 200),
        # investigator: same, plus identities (checked below)
        ("investigator", "/api/repeat-offenders", 200),
        # admin only for account management
        ("supervisor", "/api/auth/users", 403),
        ("investigator", "/api/auth/users", 403),
        ("admin", "/api/auth/users", 200),
    ])
    def test_permission_matrix(self, sign_in, role, path, expected):
        assert sign_in(role).get(path).status_code == expected

    @pytest.mark.parametrize("role,expected", [
        ("viewer", 403), ("analyst", 403), ("investigator", 403),
        ("supervisor", 200), ("admin", 200),
    ])
    def test_only_supervisors_and_admins_may_ingest(self, sign_in, role, expected):
        batch = '[{"fir_number":"RBAC/TEST/1","raw_text":"A theft was reported."}]'
        res = sign_in(role).post("/api/upload-firs", files={
            "file": ("batch.json", batch, "application/json")})
        assert res.status_code == expected

    @pytest.mark.parametrize("role,expected", [
        ("viewer", 403), ("analyst", 200), ("admin", 200),
    ])
    def test_assistant_requires_permission(self, sign_in, role, expected):
        res = sign_in(role).post("/api/chat", json={"message": "top crime patterns?"})
        assert res.status_code == expected

    def test_403_names_the_missing_permission(self, sign_in):
        detail = sign_in("viewer").get("/api/report").json()["detail"]
        assert auth.REPORT_GENERATE in detail


class TestRedaction:
    def _first_fir_with_accused(self, client):
        items = client.get("/api/firs?limit=100").json()["items"]
        return next(i for i in items if i["entities"]["accused"])

    def test_investigator_sees_identities(self, sign_in):
        client = sign_in("investigator")
        body = client.get("/api/firs?limit=5").json()
        assert body["pii_redacted"] is False
        assert "withheld" not in body["items"][0]["text"]

    @pytest.mark.parametrize("role", ["analyst", "viewer"])
    def test_lower_roles_get_redacted_records(self, sign_in, role):
        client = sign_in(role)
        body = client.get("/api/firs?limit=100").json()
        assert body["pii_redacted"] is True
        record = next(i for i in body["items"] if i["entities"]["accused"])
        names = [a["name"] for a in record["entities"]["accused"]]
        assert all(n.startswith("Accused #") for n in names), names
        assert all(a["address"] is None for a in record["entities"]["accused"])
        assert "withheld" in record["text"]
        assert "[redacted]" in record["summary"] or "Accused:" not in record["summary"]

    def test_redaction_survives_the_detail_endpoint(self, sign_in):
        number = sign_in("analyst").get("/api/firs?limit=1").json()["items"][0]["fir_number"]
        detail = sign_in("analyst").get(f"/api/firs/{number}").json()
        assert detail["pii_redacted"] is True
        assert "withheld" in detail["text"]

    def test_real_name_does_not_leak_through_any_field(self, sign_in):
        """A redacted record must not contain the offender's real name anywhere."""
        investigator = sign_in("investigator")
        target = self._first_fir_with_accused(investigator)
        real_name = target["entities"]["accused"][0]["name"]

        analyst = sign_in("analyst")
        redacted = next(i for i in analyst.get("/api/firs?limit=100").json()["items"]
                        if i["fir_number"] == target["fir_number"])
        assert real_name.lower() not in str(redacted).lower(), redacted

    def test_offender_profiles_are_anonymised(self, sign_in):
        named = sign_in("investigator").get("/api/repeat-offenders").json()
        anonymous = sign_in("analyst").get("/api/repeat-offenders").json()
        assert named and anonymous
        real_names = {o["primary_name"] for o in named}
        for offender in anonymous:
            assert offender["pii_redacted"] is True
            assert offender["primary_name"] not in real_names
            assert offender["aliases"] == []
            # The analytics an analyst legitimately needs still survive.
            assert offender["fir_count"] > 0
            assert offender["districts"]

    def test_drilldown_respects_redaction(self, sign_in):
        body = sign_in("analyst").get("/api/crime-types/theft").json()
        assert body["pii_redacted"] is True
        assert all("withheld" in f["text"] for f in body["top_firs"])


class TestAccountManagement:
    def test_admin_can_create_and_disable_a_user(self, sign_in):
        admin = sign_in("admin")
        created = admin.post("/api/auth/users", json={
            "username": "testofficer", "password": "Testing@123",
            "role": "analyst", "full_name": "Test Officer"})
        assert created.status_code == 200, created.text
        assert created.json()["role"] == "analyst"

        # The new account works...
        assert sign_in("admin") and admin.post("/api/auth/login", json={
            "username": "testofficer", "password": "Testing@123"}).status_code == 200

        # ...until it is disabled.
        admin = sign_in("admin")
        assert admin.post("/api/auth/users/testofficer/active?active=false"
                          ).status_code == 200
        assert admin.post("/api/auth/login", json={
            "username": "testofficer", "password": "Testing@123"}).status_code == 401

    @pytest.mark.parametrize("payload,fragment", [
        ({"username": "admin", "password": "Another@123", "role": "analyst"}, "exists"),
        ({"username": "weakpw", "password": "short", "role": "analyst"}, "Password"),
        ({"username": "badrole", "password": "Testing@123", "role": "root"}, "Unknown role"),
        ({"username": "bad name", "password": "Testing@123", "role": "analyst"}, "Username"),
    ])
    def test_invalid_user_creation_is_rejected(self, sign_in, payload, fragment):
        res = sign_in("admin").post("/api/auth/users", json=payload)
        assert res.status_code == 400
        assert fragment.lower() in res.json()["detail"].lower()

    def test_admin_cannot_disable_or_demote_themselves(self, sign_in):
        admin = sign_in("admin")
        assert admin.post("/api/auth/users/admin/active?active=false").status_code == 400
        assert admin.post("/api/auth/users/admin/role?role=viewer").status_code == 400

    def test_password_change_requires_the_current_password(self, sign_in):
        client = sign_in("viewer")
        assert client.post("/api/auth/password", json={
            "current_password": "wrong", "new_password": "Brand@New123"}).status_code == 403

    def test_password_change_enforces_the_policy(self, sign_in):
        res = sign_in("viewer").post("/api/auth/password", json={
            "current_password": DEMO_LOGINS["viewer"], "new_password": "weak"})
        assert res.status_code == 400

    def test_me_reports_the_permission_set(self, sign_in):
        body = sign_in("analyst").get("/api/auth/me").json()["user"]
        assert body["role"] == "analyst"
        assert auth.ASSISTANT_USE in body["permissions"]
        assert auth.FIR_READ_PII not in body["permissions"]


class TestDeploymentWarnings:
    def test_demo_credentials_are_detectable(self):
        """The app must be able to warn that published passwords are in use."""
        assert set(auth.using_demo_credentials()) >= {"admin", "viewer"}

    def test_no_shipped_signing_secret(self, monkeypatch):
        """A hardcoded fallback secret would let anyone forge a session."""
        assert auth.SECRET_KEY, "a signing key must exist"
        assert b"change" not in auth.SECRET_KEY.lower()
        assert b"secret" not in auth.SECRET_KEY.lower()
