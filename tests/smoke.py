"""Live smoke test against a running server: login, CSRF, issue, return, admin endpoints, static files."""
import http.cookiejar
import json
import sys
import urllib.error
import urllib.request
import uuid

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def csrf():
    return next((c.value for c in jar if c.name == "csrftoken"), "")


def call(method, path, body=None, idem=False):
    headers = {"Content-Type": "application/json", "X-CSRFToken": csrf(), "Referer": BASE + "/"}
    if idem:
        headers["Idempotency-Key"] = str(uuid.uuid4())
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=headers, method=method)
    try:
        with opener.open(req) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw and r.headers.get_content_type() == "application/json" else raw)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def check(label, cond):
    print(("PASS " if cond else "FAIL ") + label)
    if not cond:
        check.failed = True


check.failed = False
s, html = call("GET", "/")
check("index served", s == 200 and b"app.js" in html)
s, _ = call("GET", "/static/app.js")
check("app.js served", s == 200)
check("csrf cookie set", bool(csrf()))
s, _ = call("GET", "/api/v1/books")
check("books needs login (401)", s == 401)
s, d = call("POST", "/api/v1/auth/login", {"username": "librarian1", "password": "demo1234"})
check("librarian login", s == 200 and d["user"]["role"] == "LIBRARIAN")
s, d = call("GET", "/api/v1/patrons/lookup?code=student3")
check("patron lookup", s == 200 and d["patron"]["academic_year"] == 3)
pid = d["patron"]["id"]
s, d = call("GET", "/api/v1/books?q=Algorithms")
check("search", s == 200 and d["total"] >= 1)
s, d = call("GET", f"/api/v1/books/{d['results'][0]['id']}")
acc = next(c["accession_number"] for c in d["copies"] if c["status"] == "AVAILABLE" and c["borrowable"])
s, d = call("POST", "/api/v1/loans", {"patron_id": pid, "accession_number": acc}, idem=True)
check("issue (CSRF + idempotency through real middleware)", s == 201)
s, d = call("POST", "/api/v1/loans/return", {"accession_number": acc}, idem=True)
check("return", s == 200 and d["fine"] is None)
s, d = call("GET", "/api/v1/admin/audit")
check("librarian blocked from audit", s == 403)
call("POST", "/api/v1/auth/logout")
s, d = call("POST", "/api/v1/auth/login", {"username": "admin", "password": "demo1234"})
check("admin login", s == 200)
for path in ("/api/v1/admin/audit", "/api/v1/admin/jobs", "/api/v1/admin/notifications", "/api/v1/admin/rules",
             "/api/v1/admin/sections", "/api/v1/admin/closed-days", "/api/v1/admin/imports", "/api/v1/admin/demo/clock",
             "/api/v1/fines", "/api/v1/patrons", "/api/v1/collections", "/api/v1/categories", "/api/v1/departments"):
    s, _ = call("GET", path)
    check(f"GET {path}", s == 200)
s, d = call("GET", "/api/v1/admin/rules")
s2, _ = call("PUT", "/api/v1/admin/rules", {"rules": d["results"]})
check("rules round-trip PUT", s2 == 200)
s, d = call("GET", "/api/v1/nope")
check("unknown API -> JSON 404", s == 404 and d["error"]["code"] == "NOT_FOUND")
s, _ = call("GET", "/healthz")
check("healthz", s == 200)
sys.exit(1 if check.failed else 0)
