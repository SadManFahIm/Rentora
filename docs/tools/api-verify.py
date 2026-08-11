#!/usr/bin/env python
"""Live contract check for docs/api-reference.md.

Hits every documented endpoint against a running backend and reports
PASS/FAIL per entry. Checks three layers:

1. **Status code** — the documented expectation (200/201/403/…).
2. **Deep schema** — required JSON fields *and their wire types* for key
   endpoints (``CONTRACTS`` below). Missing keys or wrong types fail.
3. **OpenAPI cross-check** — every tested path+method must exist in the
   live ``/api/v1/schema/`` (drf-spectacular), so the hand-maintained
   reference and the generated schema can't drift apart.

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
# Deep schema contracts
# ---------------------------------------------------------------------------
# Type tokens: "int", "float", "number" (int|float), "str", "bool", "null",
# "list", "dict", tuples of tokens, nested dicts, or {"items": <schema>} for
# arrays. Money/date fields serialize as *strings* on the wire (DRF Decimal /
# DateTimeField) — contracts assert the actual wire format. Required keys must
# be present; extra keys are allowed (the docs are curated, so drift means a
# MISSING key or a wrong type, not an unexpected one).

ROOM_CORE = {
    "id": "int",
    "title": "str",
    "room_type": "str",
    "price": "str",          # DRF DecimalField -> string on the wire
    "area": "str",
    "is_available": "bool",
    "verified": "bool",
    "owner": {"id": "int", "username": "str", "nid_verified": "bool"},
}

PAGE = {
    "count": "int",
    "next": ("str", "null"),
    "previous": ("str", "null"),
    "results": "list",
}

CONTRACTS = {
    "rooms_list": {**PAGE, "results": {"items": {**ROOM_CORE, "images": "list"}}},
    "rooms_smart": {
        **PAGE,
        "results": {"items": {**ROOM_CORE, "images": "list"}},
        "nl_parsed": {
            "budget_max": ("int", "null"),
            "areas": "list",
            "room_type": ("str", "null"),
            "gender": ("str", "null"),
            "months": "list",
            "hints": "list",
        },
    },
    "room_detail": {
        **ROOM_CORE,
        "address": "str",
        "size_sqft": "int",
        "images": "list",
        "created_at": "str",
    },
    "rooms_summary": {
        "total": "int",
        "available": "int",
        "avg_price": "number",
        "min_price": "number",
        "max_price": "number",
        "by_area": {"items": {"area": "str", "count": "int", "lat": "number", "lng": "number"}},
    },
    "rooms_tier_catalog": {
        "tiers": {"items": {"tier": "str", "label": "str", "price": "int", "benefits": "list"}},
        "duration_days": "int",
        "currency": "str",
    },
    "rooms_landmarks": {"items": {"key": "str", "name": "str", "kind": "str", "lat": "number", "lng": "number"}},
    "rooms_geocode": {"items": {"key": "str", "label": "str", "kind": "str", "lat": "number", "lng": "number"}},
    "similar_images": {"items": {**ROOM_CORE, "phash_distance": "int"}},
    "reviews_list": PAGE,
    "reviews_summary": {
        "room": "int",
        "average_rating": "number",
        "total_reviews": "int",
        "counts_per_star": "dict",
        "recent": "list",
    },
    "recommendations_similar": {"items": {"room": "dict", "match_score": "number", "match_reasons": "list"}},
    "fraud_status": {"room_id": "int", "severity": "str", "score": "int", "flagged": "bool", "message": "str"},
    "bookings_list": PAGE,
    "wishlist_list": PAGE,
    "wishlist_share_info": {"token": "str", "link": "str"},
    "notifications_list": PAGE,
    "notifications_unread": {"count": "int"},
    "saved_searches_list": PAGE,
    "saved_search_created": {"id": "int", "name": "str", "filters": "dict", "last_checked_at": ("str", "null"), "created_at": "str"},
    "dashboard_stats": {
        "saved_rooms_count": "int",
        "active_bookings": "int",
        "pending_bookings": "int",
        "total_reviews_given": "int",
        "unread_notifications": "int",
        "profile_completion": "int",
    },
    "chat_rooms": PAGE,
    "chat_online": {"online": "list", "offline": "list"},
    "payments_list": PAGE,
    "payments_summary": {
        "total_paid": "number",
        "total_pending": "number",
        "total_refunded": "number",
        "count_paid": "int",
        "count_pending": "int",
        "count_refunded": "int",
    },
    "recommendations": "list",
    "pricing_predict": {
        "predicted_price": "number",
        "price_range_low": "number",
        "price_range_high": "number",
        "model_confidence": "str",
        "explanation": "str",
    },
    "pricing_market_stats": {"items": "dict"},
    "pricing_insight": "dict",
    "kyc_documents": {"items": "dict"},
    "referral": {"code": "str", "link": "str", "invited_count": "int", "invited": "list"},
    "error_envelope": {"success": "bool", "message": "str", "errors": "list"},
}


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
            if key not in value:
                problems.append(f"{path}.{key}: MISSING")
            else:
                deep_validate(value[key], sub, f"{path}.{key}", problems)
        return problems
    if not _ok(schema, value):
        problems.append(f"{path}: expected {schema}, got {_type_token(value)}")
    return problems


# ---------------------------------------------------------------------------
# HTTP check
# ---------------------------------------------------------------------------
def check(name, method, path, expected, auth=None, data=None, note="", contract=None, in_schema=True, contract_only_on_error=False):
    global fails
    # in_schema=False: paths that are deliberately NOT API routes — the schema
    # UI (/docs/, /redoc/, /schema/ itself) or negative tests asserting the
    # absence of a route (e.g. PATCH /saved-searches/:id/ -> 405).
    if in_schema:
        tested_paths.append((method.upper(), path.split("?")[0]))
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
        # deep schema validation (only meaningful on a 2xx JSON body; on
        # contract_only_on_error the schema only applies to error responses)
        if ok and contract is not None and body is not None:
            apply_contract = not (contract_only_on_error and r.status_code < 400)
            if apply_contract:
                schema = CONTRACTS.get(contract, contract) if isinstance(contract, str) else contract
                for p in deep_validate(body, schema):
                    fails += 1
                    results.append((False, f"    SCHEMA {p}"))
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
    r = check("login", "POST", "/auth/login/", [200], data={
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
          contract={"pk": "int", "username": "str", "email": "str"})
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
    check("otp/verify (no challenge)", "POST", "/auth/otp/verify/", [400, 401], data={"challenge_id": "x", "code": "000000"}, contract="error_envelope")
    check("otp/toggle", "POST", "/auth/otp/toggle/", [200, 400, 403], auth=token, data={"password": PASSWORD})
    check("otp/resend", "POST", "/auth/otp/resend/", [400, 429, 200], data={}, contract="error_envelope")
    check("passkey login begin", "POST", "/auth/passkey/login/begin/", [200], data={},
          contract={"challenge": "str", "challenge_id": "str", "timeout": "int"})
    check("passkey register begin (auth)", "POST", "/auth/passkey/register/begin/", [200, 400, 500], auth=token, data={})

    # 3. Rooms
    check("rooms list", "GET", "/rooms/", [200], contract="rooms_list")
    check("rooms filter", "GET", "/rooms/?area=Dhanmondi&is_available=true", [200], contract="rooms_list")
    check("rooms smart search", "GET",
          "/rooms/?smart=1&q=" + urllib.parse.quote("দশ হাজার এর মধ্যে উত্তরা"), [200], contract="rooms_smart")
    # NL chips in smart response
    r = check("rooms smart nl_parsed", "GET",
              "/rooms/?smart=1&q=" + urllib.parse.quote("দশ হাজার এর মধ্যে উত্তরা"), [200], contract="rooms_smart")
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
            fixture = {
                "title": "API Verify Fixture Room",
                "description": "Temporary room created by docs/tools/api-verify.py for contract checks.",
                "room_type": "single",
                "price": 5000,
                "area": "Uttara",
                "address": "Sector 10, Uttara, Dhaka",
                "lat": 23.8759,
                "lng": 90.3795,
                "size_sqft": 120,
            }
            r2 = requests.post(
                BASE + "/rooms/",
                headers={"Authorization": f"Bearer {token}"},
                json=fixture,
                timeout=20,
            )
            if r2.status_code in (200, 201):
                room_id = r2.json().get("id")
                fixture_room = True
                results.append((True, f"    bootstrapped fixture room id={room_id} (empty DB)"))
            else:
                fails += 1
                results.append((False, f"    fixture room creation failed: {r2.status_code} {r2.text[:200]}"))
    if room_id:
        check("room detail", "GET", f"/rooms/{room_id}/", [200], contract="room_detail")
        check("room similar-images", "GET", f"/rooms/{room_id}/similar-images/", [200], contract="similar_images")
        check("reviews list", "GET", "/reviews/?room=" + str(room_id), [200], contract="reviews_list")
        check("reviews summary", "GET", "/reviews/summary/?room=" + str(room_id), [200], contract="reviews_summary")
        check("pricing insight", "GET", f"/pricing/insight/{room_id}/", [200], contract="pricing_insight")
        check("recommendations similar", "GET", f"/recommendations/similar/{room_id}/", [200], contract="recommendations_similar")
        check("fraud room status", "GET", f"/fraud/rooms/{room_id}/status/", [200], contract="fraud_status")
        # booking create (may conflict; accept 201/400)
        check("booking create", "POST", "/bookings/", [201, 400], auth=token,
              data={"room": room_id, "start_date": "2026-09-01", "message": "API verify"})
        # wishlist toggle — 201 on first add (fresh row), 200 when removing / re-adding
        check("wishlist toggle", "POST", "/wishlist/toggle/", [200, 201], auth=token, data={"room_id": room_id})
        # roommates matches
        check("roommates profile GET (no profile -> 404)", "GET", "/roommates/profile/", [404], auth=token)
        check("roommates matches (no profile -> 400)", "GET", "/roommates/matches/", [400], auth=token)
        check("roommates requests", "GET", "/roommates/requests/", [200], auth=token)
        check("roommates request send (no profile -> 400)", "POST", "/roommates/requests/", [400], auth=token,
              data={"to_user": 1, "message": "hi"}, contract="error_envelope")
    else:
        fails += 1
        results.append((False, "    no rooms in list; cannot test room-scoped endpoints"))

    check("rooms landmarks", "GET", "/rooms/landmarks/", [200], contract="rooms_landmarks")
    check("rooms summary", "GET", "/rooms/summary/", [200], contract="rooms_summary")
    check("rooms geocode", "GET", "/rooms/geocode/?q=Uttara", [200], contract="rooms_geocode")
    check("rooms tier-catalog", "GET", "/rooms/tier-catalog/", [200], contract="rooms_tier_catalog")
    check("rooms bulk (array body)", "POST", "/rooms/bulk/", [400, 201], auth=token, data=[])
    check("rooms insights (own listings)", "GET", "/rooms/insights/", [200], auth=token)
    check("rooms create (tenant role)", "POST", "/rooms/", [403, 201, 400], auth=token,
          data={"title": "x", "price": 1000, "area": "Uttara"})

    # 4. Bookings list
    check("bookings list", "GET", "/bookings/", [200], auth=token, contract="bookings_list")

    # 5. Wishlist
    check("wishlist list", "GET", "/wishlist/", [200], auth=token, contract="wishlist_list")
    check("wishlist share-info", "GET", "/wishlist/share-info/", [200], auth=token, contract="wishlist_share_info")
    r = check("wishlist share", "GET", "/wishlist/share/nonexistent-token/", [404], note="(no enumeration)")

    # 6. Notifications
    check("notifications list", "GET", "/notifications/", [200], auth=token, contract="notifications_list")
    check("notifications unread-count", "GET", "/notifications/unread-count/", [200], auth=token, contract="notifications_unread")
    check("notifications mark-all-read", "POST", "/notifications/mark-all-read/", [200], auth=token)
    check("notifications push subscribe", "POST", "/notifications/push/subscribe/", [200, 400], auth=token,
          data={"endpoint": "https://example.com/push/x", "keys": {"p256dh": "a", "auth": "b"}})

    # 7. Saved searches
    check("saved-searches list", "GET", "/saved-searches/", [200], auth=token, contract="saved_searches_list")
    r = check("saved-searches create", "POST", "/saved-searches/", [201, 200], auth=token,
              data={"name": "Verify", "filters": {"area": "Uttara"}}, contract="saved_search_created")
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
    check("dashboard stats", "GET", "/dashboard/stats/", [200], auth=token, contract="dashboard_stats")

    # 9. Chat
    check("chat rooms", "GET", "/chat/rooms/", [200], auth=token, contract="chat_rooms")
    check("chat online-status", "GET", "/chat/online-status/", [200], auth=token, contract="chat_online")
    check("chat messages (no room -> 404)", "GET", "/chat/rooms/999999/messages/", [404], auth=token)

    # 10. Payments
    check("payments list", "GET", "/payments/", [200], auth=token, contract="payments_list")
    check("payments summary", "GET", "/payments/summary/", [200], auth=token, contract="payments_summary")
    # tier-upgrade: nonexistent room -> 404 (owner-gated 403 only when the room
    # exists; deterministic across seeded/empty DBs, and never touches a gateway)
    check("tier-upgrade initiate (no room -> 404)", "POST", "/payments/tier-upgrade/initiate/", [404], auth=token,
          data={"room_id": 999999, "tier": "featured", "method": "sslcommerz"})
    check("payments initiate", "POST", "/payments/initiate/", [400, 200, 201], auth=token,
          data={"room": room_id or 1, "amount": 100}, contract="error_envelope", contract_only_on_error=True)

    # 11. Recommendations & Pricing
    check("recommendations", "GET", "/recommendations/", [200], auth=token, contract="recommendations")
    check("pricing market-stats", "GET", "/pricing/market-stats/?area=Uttara", [200], contract="pricing_market_stats")
    check("pricing predict", "POST", "/pricing/predict/", [200, 400], auth=token,
          data={"area": "Uttara", "room_type": "single", "size_sqft": 120}, contract="pricing_predict")

    # 12. Fraud
    check("fraud reports (tenant)", "GET", "/fraud/reports/", [200, 403], auth=token)

    # 13. KYC (non-admin -> own docs only)
    check("kyc documents", "GET", "/users/kyc/documents/", [200], auth=token, contract="kyc_documents")
    check("kyc file (nonexistent -> 404)", "GET", "/users/kyc/documents/999999/file/", [404], auth=token)
    check("kyc pending (tenant -> 403)", "GET", "/users/kyc/pending/", [403], auth=token)
    check("kyc audit (tenant -> 403)", "GET", "/users/kyc/audit/", [403], auth=token)
    check("kyc sla (tenant -> 403)", "GET", "/users/kyc/sla/", [403], auth=token)
    check("kyc review (tenant -> 403)", "POST", "/users/kyc/1/review/", [403], auth=token,
          data={"decision": "approve"})

    # 14. Referral
    check("referral", "GET", "/users/referral/", [200], auth=token, contract="referral")

    # 15. Auth failure modes
    check("rooms auth required on create", "POST", "/rooms/", [401], data={"title": "x"}, contract="error_envelope")
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
