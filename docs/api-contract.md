# Chat API contract

POST /chat

request:  { message, session_id }
response: { answer, citations: [ { title, article, url } ] }

Implemented today: 422 with a short code as the body — `{"detail": "message_empty"}` for a
missing, empty or whitespace-only message, `{"detail": "message_too_long"}` for one over
1000 characters. CORS allows credentials from `http://localhost:3000` exactly, never `*`.

## Planned, not implemented

The front-end team's endpoint list, quoted verbatim (2026-11-11). None of the `/auth/*`
endpoints exist in `backend/app/main.py` yet, and `/chat` does not authenticate anyone
yet; this section records what they asked for, not what the API does.

POST /auth/register {full_name, email, password, lang} -> 201 {user} / 409 email_taken / 422 {error:"validation", fields}

POST /auth/login {email, password} -> 200 {user} / 401 invalid_credentials

POST /auth/logout -> 204

GET /auth/me -> 200 {user} / 401

POST /chat: 401 when not signed in; 422 for empty or too-long message (max 1000 chars)

Session in an httpOnly cookie; CORS must allow credentials from http://localhost:3000 exactly, not *

Validation errors return short codes (e.g. password_too_short), not sentences, so the front end can translate them.

Not stated in that list, so not specified here: the fields of `user`, the `fields`
payload of the register 422, the cookie name and lifetime, and the exact shape of the
`/chat` 422 body (the implementation above uses `{"detail": "<code>"}`, while the
register 422 uses `{error, fields}` — worth agreeing on one shape before the auth work
starts).
