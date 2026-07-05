# Archived routes

## auth.py.bak

Archived 2026-07-05. Built entirely on Firebase Admin SDK for session
authentication (ID token verification in `/authenticate-session`, plus a
`login_required` decorator gating `/dashboard` and `/test-secrets` on a
session key only that Firebase flow ever set). Firebase auth is no longer
part of this project.

The blueprint (`auth_bp`) was defined but never actually registered on the
Flask app (`create_app()` in `app.py` only ever registered `schedule_bp`),
so none of these routes were reachable in production even before this
archive — this is a cleanup of dead code, not a behavior change.

One route had no Firebase dependency at all: `/auth/upload_schedule`, a
plain form page. That one was preserved and re-homed directly in
`app.py::create_app()` rather than archived with the rest.

Two templates (`templates/auth/login.html`, `templates/auth/signup.html`)
still reference `auth_bp.login_page` / `auth_bp.signup_page` via
`url_for()`. Nothing renders them anymore, so this is dormant, not a live
break — worth cleaning up (or replacing with a real auth flow) if this
code is revived.

If session-based auth is needed again, this file is a reasonable starting
point but should not be restored as-is without replacing the Firebase
dependency.
