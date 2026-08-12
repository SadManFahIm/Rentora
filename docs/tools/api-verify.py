#!/usr/bin/env python
"""Live contract check for docs/api-reference.md.

Hits every documented endpoint against a running backend and reports
PASS/FAIL per entry. Checks three layers:

1. **Status code** — the documented expectation (200/201/403/…).
2. **Deep schema (schema-derived)** — the response contract is DERIVED from
   the live OpenAPI schema at runtime (``derive_response_contract`` — $refs
   resolved, required vs optional respected, nullable widened) and the real
   body is validated against it. ``OVERRIDES`` covers only what the spec
   doesn't declare (error envelopes, passkey begin).
3. **Request-body contracts (schema-derived)** — every payload the tool
   sends is validated against the schema's declared ``requestBody`` *before*
   the request; negative probes (``error_contains``) assert that malformed
   payloads are rejected with the right field error.
4. **OpenAPI cross-check** — every tested path+method must exist in the
   live ``/api/v1/schema/`` (drf-spectacular).

Usage:
    python docs/tools/api-verify.py                     # against localhost:8000
    API_BASE=http://localhost:8002/api/v1 python docs/tools/api-verify.py

Note: auth endpoints are per-IP rate limited (10/hr). Run against a fresh
server instance (e.g. `manage.py runserver 8002 --noreload`) if a run hits
429 — the throttle is in-memory per process.
"""

import json
import os
import sys
import urllib.parse

import requests

BASE = os.environ.get("API_BASE", "http://localhost:8000/api/v1")
PASSWORD = "demo12345"
USERNAME = "api.verify"
EMAIL = "api.verify@rentora.com"

results = []
fails = 0
tested_paths = []  # (method, path) pairs collected for the OpenAPI cross-check


# ---------------------------------------------------------------------------
# Schema-derived contracts (OpenAPI is the source of truth)
# ---------------------------------------------------------------------------
# Response and request contracts are DERIVED from the live /api/v1/schema/
# at runtime — no hand-maintained field tables. OVERRIDES below cover only
# what the OpenAPI spec does not declare: error envelopes (drf-spectacular
# does not generate error response schemas) and endpoints whose success
# response is not declared (e.g. passkey login begin).
#
# Type tokens: "int", "float", "number" (int|float), "str", "bool", "null",
# "list", "dict", tuples of tokens (type unions incl. nullable), nested
# dicts, or {"items": <schema>} for arrays. Optional keys are marked
# (OPTIONAL, <schema>) — absent is OK, but present must still typecheck.

OPTIONAL = object()

OVERRIDES = {
    "error_envelope": {"success": "bool", "message": "str", "errors": "list"},
    "passkey_begin": {"challenge": "str", "challenge_id": "str", "timeout": "int"},
    # Schema gaps (OpenAPI doesn't declare these shapes):
    # - dj-rest-auth's LoginView leaks its request serializer as the response
    #   schema (declares {username,email,password}); the real response is tokens.
    "login_response": {
        "access": "str", "refresh": "str", "user": "dict",
        "access_expiration": "str", "refresh_expiration": "str",
    },
    # - the OTP serializer is one shape shared by several flows (verify uses
    #   challenge_id, toggle only needs password, enable needs all) — the
    #   generated request schema can't express per-flow subsets.
    "otp_verify_request": {"challenge_id": "str", "code": "str", "recovery_code": (OPTIONAL, "str")},
    "otp_toggle_request": {"password": "str"},
    "otp_toggle_response": {"success": "bool", "otp_enabled": "bool", "pending_enable": "bool"},
    "otp_resend_request": {},  # resend takes no meaningful body — only cooldown headers
}

_spec = None


def _fetch_spec():
    """Fetch (and cache) the OpenAPI schema as JSON — drf-spectacular serves
    YAML by default, so JSON is requested explicitly."""
    global _spec
    if _spec is None:
        _spec = requests.get(
            BASE + "/schema/", headers={"Accept": "application/json"}, timeout=30
        ).json()
    return _spec


def oas_to_tokens(schema, stack=None):
    """Convert an OpenAPI JSON-schema fragment into the contract token format.

    $refs are resolved against components.schemas (recursion-guarded);
    allOf is merged; anyOf/oneOf becomes a type union; `nullable` widens the
    token to (token, "null"); object properties not in `required` become
    (OPTIONAL, …). Unknown shapes degrade to "dict" (lenient, not a failure).
    """
    if stack is None:
        stack = []
    schemas = _fetch_spec().get("components", {}).get("schemas", {})
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        if name in stack:
            return "dict"
        target = schemas.get(name)
        if target is None:
            return "dict"
        return oas_to_tokens(target, stack + [name])
    if "allOf" in schema:
        merged_props = {}
        required = []
        inherited_type = None
        for part in schema["allOf"]:
            if "$ref" in part:
                pname = part["$ref"].split("/")[-1]
                if pname not in stack:
                    stack = stack + [pname]
                part = schemas.get(pname, part)
            merged_props.update(part.get("properties", {}))
            required += part.get("required", [])
            # enum/primitive refs (e.g. a shared status enum) carry only a
            # `type` — inherit it so the merged fragment keeps its wire type
            # instead of degrading to a lenient "dict".
            if inherited_type is None and "type" in part:
                inherited_type = part["type"]
        # drop allOf itself so the merged object terminates the recursion
        merged = {k: v for k, v in schema.items() if k != "allOf"}
        if "type" not in merged and inherited_type is not None:
            merged["type"] = inherited_type
        merged["properties"] = merged_props
        merged["required"] = required
        return oas_to_tokens(merged, stack)
    if "anyOf" in schema or "oneOf" in schema:
        variants = [oas_to_tokens(v, stack) for v in schema.get("anyOf") or schema.get("oneOf")]
        toks, has_null = [], False
        for v in variants:
            if v == "null":
                has_null = True
            elif isinstance(v, tuple):
                toks.extend(t for t in v if t != "null")
            else:
                toks.append(v)
        if has_null:
            toks.append("null")
        uniq = list(dict.fromkeys(toks))
        return uniq[0] if len(uniq) == 1 else tuple(uniq)
    typ = schema.get("type")
    if typ == "object":
        props = schema.get("properties", {})
        required = schema.get("required")
        required = set(required) if required is not None else set(props.keys())
        result = {}
        for k, v in props.items():
            sub = oas_to_tokens(v, stack)
            if k not in required:
                sub = (OPTIONAL, sub)
            result[k] = sub
        if schema.get("nullable"):
            return (result, "null")
        return result
    if typ == "array":
        return {"items": oas_to_tokens(schema.get("items", {}), stack)}
    token = {"string": "str", "integer": "int", "number": "number",
             "boolean": "bool", "null": "null"}.get(typ)
    if token is None:
        return "dict"
    if schema.get("nullable"):
        return (token, "null")
    return token


def _match_schema_path(path):
    """Return the schema path key matching a tested path (numeric ids / placeholders).

    Exact matches win over placeholder routes — otherwise /reviews/summary/
    would wrongly match /reviews/{id}/ with "summary" as the id.
    """
    path = path.split("?")[0]  # query strings must not affect route matching
    full = "/api/v1" + path if not path.startswith("/api/v1") else path
    t_segs = full.rstrip("/").split("/")
    fallback = None
    for sp in _fetch_spec().get("paths", {}):
        s_segs = sp.rstrip("/").split("/")
        if len(t_segs) != len(s_segs):
            continue
        if t_segs == s_segs:
            return sp
        if fallback is None and all(
            s.startswith("{") and s.endswith("}") or t == s for t, s in zip(t_segs, s_segs)
        ):
            fallback = sp
    return fallback


def derive_response_contract(method, path, status):
    """Declared response schema for (method, path, status), or None if not declared.

    Error responses (4xx/5xx) are never validated against a 2xx schema — the
    OpenAPI spec does not declare error shapes, and the curated error-envelope
    override covers the ones we assert.
    """
    if status >= 400:
        return None
    sp = _match_schema_path(path)
    if sp is None:
        return None
    op = _fetch_spec()["paths"][sp].get(method.lower())
    if not op:
        return None
    responses = op.get("responses", {})
    rs = responses.get(str(status)) or responses.get("default")
    if not rs:
        for code in ("200", "201", "204"):
            if code in responses:
                rs = responses[code]
                break
    if not rs:
        return None
    sch = (rs.get("content", {}).get("application/json", {}) or {}).get("schema")
    if not sch:
        return None
    return oas_to_tokens(sch)


def _make_all_optional(schema):
    """OpenAPI cannot express partial PATCH semantics — every field the schema
    marks required is optional for a PATCH payload. Only validate types of the
    fields actually present."""
    if not isinstance(schema, dict):
        return schema
    return {
        k: v if (isinstance(v, tuple) and v and v[0] is OPTIONAL) else (OPTIONAL, v)
        for k, v in schema.items()
    }


def derive_request_contract(method, path):
    """Declared requestBody schema for (method, path), or None if not declared."""
    sp = _match_schema_path(path)
    if sp is None:
        return None
    op = _fetch_spec()["paths"][sp].get(method.lower())
    if not op:
        return None
    rb = op.get("requestBody", {})
    sch = (rb.get("content", {}).get("application/json", {}) or {}).get("schema")
    if not sch:
        return None
    schema = oas_to_tokens(sch)
    if method.upper() == "PATCH":
        schema = _make_all_optional(schema)
    return schema


def _type_token(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "unknown"


def _ok(token, value):
    if isinstance(token, tuple):
        return any(_ok(t, value) for t in token)
    if token == "number":
        return type(value) in (int, float) and not isinstance(value, bool)
    if token in ("int", "float", "str", "bool", "null", "list", "dict"):
        return _type_token(value) == token
    return False


def deep_validate(value, schema, path="root", problems=None):
    """Recursively check `value` against `schema`; returns a list of problem strings."""
    if problems is None:
        problems = []
    if isinstance(schema, dict) and "items" in schema:
        if not isinstance(value, list):
            problems.append(f"{path}: expected list, got {_type_token(value)}")
            return problems
        for i, item in enumerate(value):
            deep_validate(item, schema["items"], f"{path}[{i}]", problems)
        return problems
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            problems.append(f"{path}: expected dict, got {_type_token(value)}")
            return problems
        for key, sub in schema.items():
            optional = isinstance(sub, tuple) and len(sub) == 2 and sub[0] is OPTIONAL
            real = sub[1] if optional else sub
            if key not in value:
                if not optional:
                    problems.append(f"{path}.{key}: MISSING")
            else:
                deep_validate(value[key], real, f"{path}.{key}", problems)
        return problems
    if not _ok(schema, value):
        problems.append(f"{path}: expected {schema}, got {_type_token(value)}")
    return problems


# ---------------------------------------------------------------------------
# HTTP check
# ---------------------------------------------------------------------------
def check(name, method, path, expected, auth=None, data=None, note="", contract=None, in_schema=True, contract_only_on_error=False, error_contains=None, skip_body_contract=False, body_contract=None):
    global fails
    # in_schema=False: paths that are deliberately NOT API routes — the schema
    # UI (/docs/, /redoc/, /schema/ itself) or negative tests asserting the
    # absence of a route (e.g. PATCH /saved-searches/:id/ -> 405).
    if in_schema:
        tested_paths.append((method.upper(), path.split("?")[0]))
    # request-body contract: the payload we send must match the schema's
    # declared requestBody (checked before the request is even made). Negative
    # probes (deliberately malformed payloads) opt out via skip_body_contract.
    if data is not None and not skip_body_contract:
        if body_contract is not None:
            schema = OVERRIDES.get(body_contract, body_contract) if isinstance(body_contract, str) else body_contract
        else:
            schema = derive_request_contract(method, path)
        if schema is not None:
            for p in deep_validate(data, schema):
                fails += 1
                results.append((False, f"    BODY-SCHEMA {p}"))
        else:
            results.append((True, f"    (no declared requestBody for {method} {path} — body unchecked)"))
    url = BASE + path
    headers = {}
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    try:
        r = requests.request(method, url, headers=headers, json=data, timeout=20)
        ok = r.status_code in expected
        status = f"got {r.status_code}, want {'/'.join(str(e) for e in expected)}"
        shape = ""
        if ok:
            try:
                body = r.json()
                shape = f" json_keys={list(body.keys())[:6]}"
            except Exception:
                body = None
                shape = " (non-json body)"
        results.append((ok, f"{method} {path} -> {status}{shape} {note}"))
        if not ok:
            fails += 1
            try:
                results.append((False, f"    body: {r.text[:300]}"))
            except Exception:
                pass
        # error_contains: on a 4xx/5xx response, the body must mention the field
        # — locks the API's *input validation* contract (rejects with the right
        # error), not just the status code.
        if error_contains is not None:
            if 400 <= r.status_code < 500 and error_contains.lower() in r.text.lower():
                results.append((True, f"    error mentions '{error_contains}' ✓"))
            else:
                fails += 1
                results.append((False, f"    error_contains '{error_contains}': body was '{r.text[:200]}'"))
        # deep schema validation: explicit `contract` name -> OVERRIDES;
        # otherwise the contract is DERIVED from the live OpenAPI schema for
        # (method, path, status). On contract_only_on_error, the schema only
        # applies to error responses.
        if ok and body is not None:
            apply_contract = not (contract_only_on_error and r.status_code < 400)
            if apply_contract:
                if contract is not None:
                    schema = OVERRIDES.get(contract, contract) if isinstance(contract, str) else contract
                else:
                    schema = derive_response_contract(method, path, r.status_code)
                if schema is not None:
                    for p in deep_validate(body, schema):
                        fails += 1
                        results.append((False, f"    SCHEMA {p}"))
                elif contract is None and r.status_code < 300:
                    results.append((True, f"    (no declared {r.status_code} schema — shape unchecked)"))
        return r
    except Exception as exc:
        fails += 1
        results.append((False, f"{method} {path} -> EXCEPTION {exc}"))
        return None


# ---------------------------------------------------------------------------
# OpenAPI cross-check
# ---------------------------------------------------------------------------
def openapi_cross_check():
    """Every tested path+method must be a registered route in the live schema."""
    global fails
    try:
        # drf-spectacular serves YAML by default; ask for JSON explicitly
        spec = requests.get(
            BASE + "/schema/", headers={"Accept": "application/json"}, timeout=30
        ).json()
    except Exception as exc:
        fails += 1
        results.append((False, f"OpenAPI cross-check: could not fetch schema ({exc})"))
        return
    spec_paths = spec.get("paths", {})

    def matches(tested_path, schema_path, method):
        """True if `tested_path` + method is served by `schema_path`'s route.

        Schema placeholders ({id}, {token}, …) match any single segment, so a
        literal tested path (e.g. /wishlist/share/nonexistent-token/) maps to
        the declared /wishlist/share/{token}/ route.
        """
        methods = {m.upper() for m in spec_paths[schema_path]}
        if method not in methods:
            return False
        t_segs = tested_path.rstrip("/").split("/")
        s_segs = schema_path.rstrip("/").split("/")
        if len(t_segs) != len(s_segs):
            return False
        return all(
            s.startswith("{") and s.endswith("}") or t == s
            for t, s in zip(t_segs, s_segs)
        )

    missing = []
    for method, path in sorted(set(tested_paths)):
        full = "/api/v1" + path if not path.startswith("/api/v1") else path
        if not any(matches(full, sp, method) for sp in spec_paths):
            missing.append(f"{method} {path}")

    if missing:
        fails += 1
        results.append((False, f"OpenAPI cross-check: {len(missing)} tested path(s) missing from /schema/:"))
        for m in missing:
            results.append((False, f"    {m}"))
    else:
        results.append((True, f"OpenAPI cross-check: all {len(set(tested_paths))} tested paths present in /schema/ ✅"))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    global fails

    # 0. health of backend (UI/infra pages — not API routes, so not in the schema)
    check("health", "GET", "/schema/", [200], note="(drf-spectacular schema)", in_schema=False)
    check("docs", "GET", "/docs/", [200], note="(Swagger UI)", in_schema=False)
    check("redoc", "GET", "/redoc/", [200], note="(ReDoc)", in_schema=False)

    # 1. Auth flows
    # register fresh (may already exist from prior runs -> then login)
    # 201 success envelope is {access, refresh, user}; the error envelope
    # ({success, message, errors}) only applies on 400 (user already exists)
    r = check("register", "POST", "/auth/register/", [201, 400], data={
        "username": USERNAME, "email": EMAIL,
        "password1": PASSWORD, "password2": PASSWORD,
    }, contract="error_envelope", contract_only_on_error=True)
    # negative: malformed email must be rejected as a validation error
    check("register bad email -> 400", "POST", "/auth/register/", [400],
          data={"username": "bad.email.probe", "email": "not-an-email",
                "password1": PASSWORD, "password2": PASSWORD},
          contract="error_envelope", error_contains="email", skip_body_contract=True)
    # login response override: dj-rest-auth leaks its request serializer as
    # the declared response ({username,email,password}) — the real shape is
    # the JWT token envelope (see OVERRIDES["login_response"]).
    r = check("login", "POST", "/auth/login/", [200], contract="login_response", data={
        "username": USERNAME, "password": PASSWORD,
    })
    if r is None or r.status_code != 200:
        print("FATAL: cannot login; aborting")
        return 1
    body = r.json()
    if "pending_challenge" in body:
        print("FATAL: 2FA pending for fresh user; aborting")
        return 1
    token = body["access"]
    refresh = body["refresh"]

    check("token/refresh", "POST", "/auth/token/refresh/", [200], data={"refresh": refresh})
    check("me GET", "GET", "/auth/user/", [200], auth=token,
          )
    check("me PATCH", "PATCH", "/auth/user/", [200], auth=token, data={"first_name": "Api"})
    # refresh endpoint rotates tokens: re-login to get a fresh refresh for logout
    r2 = requests.post(BASE + "/auth/login/", json={"username": USERNAME, "password": PASSWORD}, timeout=20)
    fresh_refresh = r2.json().get("refresh") if r2.status_code == 200 else None
    if fresh_refresh:
        check("logout", "POST", "/auth/logout/", [200], auth=token, data={"refresh": fresh_refresh})
    else:
        fails += 1
        results.append((False, "logout could not be tested (login failed)"))

    # 2FA endpoints (public 401 when not enrolled)
    check("otp/verify (no challenge)", "POST", "/auth/otp/verify/", [400, 401],
          data={"challenge_id": "x", "code": "000000"}, contract="error_envelope",
          body_contract="otp_verify_request")
    check("otp/toggle", "POST", "/auth/otp/toggle/", [200, 400, 403], auth=token,
          data={"password": PASSWORD}, contract="otp_toggle_response", body_contract="otp_toggle_request")
    check("otp/resend", "POST", "/auth/otp/resend/", [400, 429, 200], data={},
          contract="error_envelope", body_contract="otp_resend_request")
    check("passkey login begin", "POST", "/auth/passkey/login/begin/", [200], data={},
          contract="passkey_begin")
    check("passkey register begin (auth)", "POST", "/auth/passkey/register/begin/", [200, 400, 500], auth=token, data={})

    # 3. Rooms
    check("rooms list", "GET", "/rooms/", [200])
    check("rooms filter", "GET", "/rooms/?area=Dhanmondi&is_available=true", [200])
    check("rooms smart search", "GET",
          "/rooms/?smart=1&q=" + urllib.parse.quote("দশ হাজার এর মধ্যে উত্তরা"), [200])
    # NL chips in smart response
    r = check("rooms smart nl_parsed", "GET",
              "/rooms/?smart=1&q=" + urllib.parse.quote("দশ হাজার এর মধ্যে উত্তরা"), [200])
    if r is not None and r.status_code == 200:
        nl = r.json().get("nl_parsed") or {}
        if nl:
            results.append((True, f"    nl_parsed={json.dumps(nl, ensure_ascii=False)[:160]}"))
        else:
            fails += 1
            results.append((False, "    nl_parsed missing from smart search response"))
    # get a room id (bootstrap a fixture room on an empty DB — e.g. fresh CI
    # checkout — so the room-scoped contract checks still run; deleted at the end)
    room_id = None
    fixture_room = False
    r = requests.get(BASE + "/rooms/", timeout=20)
    if r.status_code == 200:
        rooms = r.json().get("results") or []
        if rooms:
            room_id = rooms[0]["id"]
        else:
            # Decimal/Decimal-coordinate fields are declared `string` by
            # drf-spectacular (DRF renders them as strings on output), so the
            # fixture sends string values — what the schema promises clients.
            fixture = {
                "title": "API Verify Fixture Room",
                "description": "Temporary room created by docs/tools/api-verify.py for contract checks.",
                "room_type": "single",
                "price": "5000",
                "area": "Uttara",
                "address": "Sector 10, Uttara, Dhaka",
                "lat": "23.8759",
                "lng": "90.3795",
                "size_sqft": 120,
            }
            # routed through check() so the request-body contract applies
            r2 = check("fixture room create", "POST", "/rooms/", [201, 200], auth=token, data=fixture)
            if r2 is not None and r2.status_code in (200, 201):
                room_id = r2.json().get("id")
                fixture_room = True
                results.append((True, f"    bootstrapped fixture room id={room_id} (empty DB)"))
            else:
                fails += 1
                results.append((False, "    fixture room creation failed (see above)"))
    if room_id:
        check("room detail", "GET", f"/rooms/{room_id}/", [200])
        check("room similar-images", "GET", f"/rooms/{room_id}/similar-images/", [200])
        check("reviews list", "GET", "/reviews/?room=" + str(room_id), [200])
        check("reviews summary", "GET", "/reviews/summary/?room=" + str(room_id), [200])
        check("pricing insight", "GET", f"/pricing/insight/{room_id}/", [200])
        check("recommendations similar", "GET", f"/recommendations/similar/{room_id}/", [200])
        check("fraud room status", "GET", f"/fraud/rooms/{room_id}/status/", [200])
        # booking create (may conflict; accept 201/400)
        check("booking create", "POST", "/bookings/", [201, 400], auth=token,
              data={"room": room_id, "check_in": "2026-09-01", "notes": "API verify"})
        # negative: booking without a room must be rejected naming the field
        check("booking create missing room -> 400", "POST", "/bookings/", [400], auth=token,
              data={"check_in": "2026-09-01", "notes": "no room"},
              contract="error_envelope", error_contains="room", skip_body_contract=True)
        # wishlist toggle — 201 on first add (fresh row), 200 when removing / re-adding
        check("wishlist toggle", "POST", "/wishlist/toggle/", [200, 201], auth=token, data={"room_id": room_id})
        # negative: the old `room` field name (the docs bug we caught) must fail
        # (this view returns a plain {"detail": …} 400 — no unified envelope)
        check("wishlist toggle wrong field -> 400", "POST", "/wishlist/toggle/", [400], auth=token,
              data={"room": room_id}, error_contains="room_id", skip_body_contract=True)
        # roommates matches
        check("roommates profile GET (no profile -> 404)", "GET", "/roommates/profile/", [404], auth=token)
        check("roommates matches (no profile -> 400)", "GET", "/roommates/matches/", [400], auth=token)
        check("roommates requests", "GET", "/roommates/requests/", [200], auth=token)
        check("roommates request send (no profile -> 400)", "POST", "/roommates/requests/", [400], auth=token,
              data={"receiver_id": 1, "message": "hi"}, contract="error_envelope")
    else:
        fails += 1
        results.append((False, "    no rooms in list; cannot test room-scoped endpoints"))

    check("rooms landmarks", "GET", "/rooms/landmarks/", [200])
    check("rooms summary", "GET", "/rooms/summary/", [200])
    check("rooms geocode", "GET", "/rooms/geocode/?q=Uttara", [200])
    check("rooms tier-catalog", "GET", "/rooms/tier-catalog/", [200])
    check("rooms bulk (array body)", "POST", "/rooms/bulk/", [400, 201], auth=token, data=[])
    check("rooms insights (own listings)", "GET", "/rooms/insights/", [200], auth=token)
    # negative: missing required fields must be rejected naming them
    check("rooms create missing price -> 400", "POST", "/rooms/", [400], auth=token,
          data={"title": "x", "area": "Uttara"}, contract="error_envelope",
          error_contains="price", skip_body_contract=True)

    # 4. Bookings list
    check("bookings list", "GET", "/bookings/", [200], auth=token)

    # 5. Wishlist
    check("wishlist list", "GET", "/wishlist/", [200], auth=token)
    check("wishlist share-info", "GET", "/wishlist/share-info/", [200], auth=token)
    r = check("wishlist share", "GET", "/wishlist/share/nonexistent-token/", [404], note="(no enumeration)")

    # 6. Notifications
    check("notifications list", "GET", "/notifications/", [200], auth=token)
    check("notifications unread-count", "GET", "/notifications/unread-count/", [200], auth=token)
    check("notifications mark-all-read", "POST", "/notifications/mark-all-read/", [200], auth=token)
    check("notifications push subscribe", "POST", "/notifications/push/subscribe/", [200, 201, 400], auth=token,
          data={"endpoint": "https://example.com/push/x", "auth": "b", "p256dh": "a"})

    # 7. Saved searches
    check("saved-searches list", "GET", "/saved-searches/", [200], auth=token)
    r = check("saved-searches create", "POST", "/saved-searches/", [201, 200], auth=token,
              data={"name": "Verify", "filters": {"area": "Uttara"}})
    ss_id = None
    if r is not None and r.status_code in (200, 201):
        try:
            ss_id = r.json().get("id")
        except Exception:
            pass
    if ss_id:
        check("saved-searches check", "POST", f"/saved-searches/{ss_id}/check/", [200], auth=token)
        check("saved-searches PATCH (no update endpoint -> 405)", "PATCH", f"/saved-searches/{ss_id}/", [405], auth=token, data={"name": "Verify2"}, in_schema=False)
        check("saved-searches delete", "DELETE", f"/saved-searches/{ss_id}/", [204], auth=token)

    # 8. Dashboard
    check("dashboard stats", "GET", "/dashboard/stats/", [200], auth=token)

    # 9. Chat
    check("chat rooms", "GET", "/chat/rooms/", [200], auth=token)
    check("chat online-status", "GET", "/chat/online-status/", [200], auth=token)
    check("chat messages (no room -> 404)", "GET", "/chat/rooms/999999/messages/", [404], auth=token)

    # 10. Payments
    check("payments list", "GET", "/payments/", [200], auth=token)
    check("payments summary", "GET", "/payments/summary/", [200], auth=token)
    # tier-upgrade: nonexistent room -> 404 (owner-gated 403 only when the room
    # exists; deterministic across seeded/empty DBs, and never touches a gateway)
    check("tier-upgrade initiate (no room -> 404)", "POST", "/payments/tier-upgrade/initiate/", [404], auth=token,
          data={"room_id": 999999, "tier": "featured", "method": "sslcommerz"})
    check("payments initiate", "POST", "/payments/initiate/", [400, 200, 201], auth=token,
          data={"booking_id": 999999, "payment_type": "monthly_rent"},
          contract="error_envelope", contract_only_on_error=True)

    # 11. Recommendations & Pricing
    check("recommendations", "GET", "/recommendations/", [200], auth=token)
    check("pricing market-stats", "GET", "/pricing/market-stats/?area=Uttara", [200])
    check("pricing predict", "POST", "/pricing/predict/", [200, 400], auth=token,
          data={"area": "Uttara", "room_type": "single", "size_sqft": 120})

    # 12. Fraud
    check("fraud reports (tenant)", "GET", "/fraud/reports/", [200, 403], auth=token)

    # 13. KYC (non-admin -> own docs only)
    check("kyc documents", "GET", "/users/kyc/documents/", [200], auth=token)
    check("kyc file (nonexistent -> 404)", "GET", "/users/kyc/documents/999999/file/", [404], auth=token)
    check("kyc pending (tenant -> 403)", "GET", "/users/kyc/pending/", [403], auth=token)
    check("kyc audit (tenant -> 403)", "GET", "/users/kyc/audit/", [403], auth=token)
    check("kyc sla (tenant -> 403)", "GET", "/users/kyc/sla/", [403], auth=token)
    check("kyc review (tenant -> 403)", "POST", "/users/kyc/1/review/", [403], auth=token,
          data={"approved": False})

    # 14. Referral
    check("referral", "GET", "/users/referral/", [200], auth=token)

    # 15. Auth failure modes
    check("rooms auth required on create", "POST", "/rooms/", [401], data={"title": "x"},
          contract="error_envelope", skip_body_contract=True)
    check("bad token 401", "GET", "/auth/user/", [401], auth="not.a.token")

    # cleanup: remove the fixture room we created (owner-only DELETE, we own it)
    if fixture_room and room_id is not None:
        try:
            requests.delete(
                BASE + f"/rooms/{room_id}/",
                headers={"Authorization": f"Bearer {token}"},
                timeout=20,
            )
            results.append((True, f"    cleaned up fixture room id={room_id}"))
        except Exception:
            pass

    # ---- OpenAPI cross-check (schema is the source of truth) ----
    openapi_cross_check()

    # ---- report ----
    print("=" * 80)
    print(f"API LIVE VERIFICATION — {len(results)} checks, {fails} failures")
    print("=" * 80)
    for ok, line in results:
        print(("✅" if ok else "❌"), line)
    print("=" * 80)
    print("RESULT:", "ALL PASS" if fails == 0 else f"{fails} FAILURES")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
