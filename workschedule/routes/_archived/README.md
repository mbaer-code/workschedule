# Archived routes

Archived 2026-07-05. This product doesn't support login and doesn't save
user data — it's stateless, anonymous, review-before-pay by design. The
files here are leftovers from an earlier direction that assumed persistent
user accounts. None of them were reachable from the live app before this
archive; this is dead-code cleanup, not a behavior change.

## auth.py.bak

Built entirely on Firebase Admin SDK for session authentication (ID token
verification in `/authenticate-session`, plus a `login_required` decorator
gating `/dashboard` and `/test-secrets` on a session key only that
Firebase flow ever set). Firebase auth is no longer part of this project.

The blueprint (`auth_bp`) was defined but never registered on the Flask
app — `create_app()` in `app.py` only ever registered `schedule_bp` — so
none of these routes were ever reachable in production.

One route, `/auth/upload_schedule`, had no Firebase dependency — a plain
form page rendering `templates/auth/upload_schedule.html`. It was briefly
re-homed standalone in `app.py`, then removed on closer inspection: the
only thing that ever linked to it was `templates/dashboard.html`, itself
only reachable through the same dead Firebase login flow. It had no real
entry point and duplicated `/schedule/upload` (the actual, working upload
page) with an older template and no timezone auto-detection. Not worth
keeping.

## dashboard.html.bak

Misnamed file — actually raw HTML, not Python, despite the `.py`
extension and living in `routes/`. Never imported as a module by anything
(a `.py` file can't be `import`ed if it isn't valid Python — this one
would have raised `SyntaxError` on any attempt). Archived alongside the
rest for the same reason: dead code from the login/dashboard direction.

## Related: templates/_archived/

The corresponding dead templates (`templates/auth/` — `index.html`,
`landing.html`, `login.html`, `signup.html`, `upload_schedule.html` — and
`templates/dashboard.html`) were archived in the same pass. None were
rendered by anything once `auth_bp` was removed from consideration.
`login.html` and `signup.html` still reference `auth_bp.login_page` /
`signup_page` via `url_for()`, which would raise a `BuildError` if ever
rendered again — harmless while archived, worth fixing first if revived.

If session-based auth or saved user data is ever added back, these files
are a reasonable reference point but shouldn't be restored as-is — the
Firebase dependency and the login-gated dashboard concept would need to
be rebuilt to match whatever the actual product decision is at that time.
