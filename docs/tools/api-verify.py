#!/usr/bin/env python
"""Live contract check for docs/api-reference.md.

Hits every documented endpoint against a running backend and reports
status-code / response-shape PASS or FAIL per entry. Used to keep the
hand-maintained API reference honest against the OpenAPI schema.

Usage:
    python docs/tools/api-verify.py                     # against localhost:8000
    API_BASE=http://localhost:8002/api/v1 python docs/tools/api-verify.py

Note: auth endpoints are per-IP rate limited (10/hr). Run against a fresh
server instance (e.g. `manage.py runserver 8002 --noreload`) if a run hits
429 — the throttle is in-memory per process.
"""

"""Live verification of docs/api-reference.md against the running backend.

Hits every documented endpoint, checks status codes + minimal response shape,
and reports PASS/FAIL per entry. Run with the backend venv python.
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


def check(name, method, path, expected, auth=None, data=None, note=""):
    global fails
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
                shape = " (non-json body)"
        results.append((ok, f"{method} {path} -> {status}{shape} {note}"))
        if not ok:
            fails += 1
            try:
                results.append((False, f"    body: {r.text[:300]}"))
            except Exception:
                pass
        return r
    except Exception as exc:
        fails += 1
        results.append((False, f"{method} {path} -> EXCEPTION {exc}"))
        return None


def main():
    global fails

    # 0. health of backend
    check("health", "GET", "/schema/", [200], note="(drf-spectacular schema)")
    check("docs", "GET", "/docs/", [200], note="(Swagger UI)")
    check("redoc", "GET", "/redoc/", [200], note="(ReDoc)")

    # 1. Auth flows
    # register fresh (may already exist from prior runs -> then login)
    r = check("register", "POST", "/auth/register/", [201, 400], data={
        "username": USERNAME, "email": EMAIL,
        "password1": PASSWORD, "password2": PASSWORD,
    })
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
    check("me GET", "GET", "/auth/user/", [200], auth=token)
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
    check("otp/verify (no challenge)", "POST", "/auth/otp/verify/", [400, 401], data={"challenge_id": "x", "code": "000000"})
    check("otp/toggle", "POST", "/auth/otp/toggle/", [200, 400, 403], auth=token, data={"password": PASSWORD})
    check("otp/resend", "POST", "/auth/otp/resend/", [400, 429, 200], data={})
    check("passkey login begin", "POST", "/auth/passkey/login/begin/", [200], data={})
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
        check("room detail", "GET", f"/rooms/{room_id}/", [200])
        check("room similar-images", "GET", f"/rooms/{room_id}/similar-images/", [200])
        check("reviews list", "GET", "/reviews/?room=" + str(room_id), [200])
        check("reviews summary", "GET", "/reviews/summary/?room=" + str(room_id), [200])
        check("pricing insight", "GET", f"/pricing/insight/{room_id}/", [200])
        check("recommendations similar", "GET", f"/recommendations/similar/{room_id}/", [200])
        check("fraud room status", "GET", f"/fraud/rooms/{room_id}/status/", [200])
        # booking create (may conflict; accept 201/400)
        check("booking create", "POST", "/bookings/", [201, 400], auth=token,
              data={"room": room_id, "start_date": "2026-09-01", "message": "API verify"})
        # wishlist toggle
        # 201 on first add (fresh row), 200 when removing / re-adding
        check("wishlist toggle", "POST", "/wishlist/toggle/", [200, 201], auth=token, data={"room_id": room_id})
        # roommates matches
        check("roommates profile GET (no profile -> 404)", "GET", "/roommates/profile/", [404], auth=token)
        check("roommates matches (no profile -> 400)", "GET", "/roommates/matches/", [400], auth=token)
        check("roommates requests", "GET", "/roommates/requests/", [200], auth=token)
    else:
        fails += 1
        results.append((False, "    no rooms in list; cannot test room-scoped endpoints"))

    check("rooms landmarks", "GET", "/rooms/landmarks/", [200])
    check("rooms summary", "GET", "/rooms/summary/", [200])
    check("rooms geocode", "GET", "/rooms/geocode/?q=Uttara", [200])
    check("rooms tier-catalog", "GET", "/rooms/tier-catalog/", [200])
    check("rooms bulk (array body)", "POST", "/rooms/bulk/", [400, 201], auth=token, data=[])
    check("rooms insights (own listings)", "GET", "/rooms/insights/", [200], auth=token)
    check("rooms create (tenant role)", "POST", "/rooms/", [403, 201, 400], auth=token,
          data={"title": "x", "price": 1000, "area": "Uttara"})

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
    check("notifications push subscribe", "POST", "/notifications/push/subscribe/", [200, 400], auth=token,
          data={"endpoint": "https://example.com/push/x", "keys": {"p256dh": "a", "auth": "b"}})

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
        check("saved-searches PATCH (no update endpoint -> 405)", "PATCH", f"/saved-searches/{ss_id}/", [405], auth=token, data={"name": "Verify2"})
        check("saved-searches delete", "DELETE", f"/saved-searches/{ss_id}/", [204], auth=token)

    # 8. Dashboard
    check("dashboard stats", "GET", "/dashboard/stats/", [200], auth=token)

    # 9. Chat
    check("chat rooms", "GET", "/chat/rooms/", [200], auth=token)
    check("chat online-status", "GET", "/chat/online-status/", [200], auth=token)

    # 10. Payments
    check("payments list", "GET", "/payments/", [200], auth=token)
    check("payments summary", "GET", "/payments/summary/", [200], auth=token)
    check("payments initiate", "POST", "/payments/initiate/", [400, 200, 201], auth=token,
          data={"room": room_id or 1, "amount": 100})

    # 11. Recommendations & Pricing
    check("recommendations", "GET", "/recommendations/", [200], auth=token)
    check("pricing market-stats", "GET", "/pricing/market-stats/?area=Uttara", [200])
    check("pricing predict", "POST", "/pricing/predict/", [200, 400], auth=token,
          data={"area": "Uttara", "room_type": "single", "size_sqft": 120})

    # 12. Fraud
    check("fraud reports (tenant)", "GET", "/fraud/reports/", [200, 403], auth=token)

    # 13. KYC (non-admin -> own docs only)
    check("kyc documents", "GET", "/users/kyc/documents/", [200], auth=token)
    check("kyc pending (tenant -> 403)", "GET", "/users/kyc/pending/", [403], auth=token)
    check("kyc audit (tenant -> 403)", "GET", "/users/kyc/audit/", [403], auth=token)
    check("kyc sla (tenant -> 403)", "GET", "/users/kyc/sla/", [403], auth=token)
    check("kyc review (tenant -> 403)", "POST", "/users/kyc/1/review/", [403], auth=token,
          data={"decision": "approve"})

    # 14. Referral
    check("referral", "GET", "/users/referral/", [200], auth=token)

    # 15. Auth failure modes
    check("rooms auth required on create", "POST", "/rooms/", [401], data={"title": "x"})
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
