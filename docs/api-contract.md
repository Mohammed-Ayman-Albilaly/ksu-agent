# Chat API contract

POST /chat

request:  { message, session_id }
response: { answer, citations: [ { title, article, url } ] }

Implemented today: 422 with a short code as the body — `{"detail": "message_empty"}` for a
missing, empty or whitespace-only message, `{"detail": "message_too_long"}` for one over
1000 characters, and the codes in the table below for a body that does not fit the model.
CORS allows credentials from `http://localhost:3000` exactly, never `*`.

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

## Phase 2 — implemented

Everything in this section is agreed in
[ADR 0001](adr/0001-phase2-data-access.md) and planned in
[the Phase 2 page map](phase2-page-map.md). All of it is built: the three `/chat`
response shapes and the catalogue in `backend/app/main.py` and `backend/app/tools.py`,
`/chat/with-data` in `backend/app/main.py` and `backend/app/with_data.py`, and the
consent card in the front end. [The reasoning step](phase2-reasoning.md) describes the
flow end to end, the questions the router recognises and the card's wording.

### POST /chat — three response shapes, chosen by `type`

The response gains a `type` field; nothing else about Phase 1 changes.

```json
{ "type": "answer", "answer": "...", "citations": [ { "title": "...", "article": "...", "url": "..." } ] }
```

```json
{ "type": "tool", "tool": "get_gpa", "args": {} }
```

```json
{ "type": "reason", "tools": [ "get_plan_progress", "get_gpa" ], "route_token": "eyJ... .9f..." }
```

- `answer` — the Phase 1 shape, unchanged apart from the added `type`.
- `tool` — asks the website to run `tool` through the extension (see the catalogue
  below) and answer from the result in the browser. The backend sends no personal data
  in this response and receives none in the request; `args` is empty for every tool in
  the catalogue.
- `reason` — the question needs reasoning over the student's own values, for example
  "can I graduate next term?". `tools` names one to three tools from the catalogue
  and carries no data and no args. `route_token` is what binds this reply to the
  question it answered: see [the route token](#the-route-token) below. The website runs
  those tools, shows the student exactly what would be sent, and posts
  `/chat/with-data` only if they approve this one question.
- **Backward compatibility:** a response without `type` must be treated as
  `"answer"`. A client that does not know `reason` shows its generic error for that
  message; it never treats `tools` as data and never posts `/chat/with-data`.

The request is `{ message, session_id, history }`, with the same 401 and 422 codes.
`history` is optional and carries the conversation so far:

```json
{ "message": "...", "session_id": "...", "history": [ { "role": "user", "content": "..." }, { "role": "assistant", "content": "..." } ] }
```

The website holds the conversation and sends the last six turns (three exchanges) with
every question; the server keeps none of it — no session, no history file, and no log line
carrying its text, only the number of turns. `role` is `user` or `assistant`, and `content`
is at most 1000 characters like the message. The turns are context for this answer, never a
source of a fact: every claim still rests on the articles retrieved for the current question,
so a number from an earlier answer is not repeated unless this question's articles or the
student's computed facts carry it. A history of more than six turns, a role other than `user`
or `assistant`, or a blank or too-long content is `history_invalid`.

A 503 answers a failure of the answer service itself: a missing index, a missing API key,
or a model call that fails. Only the exception's type is logged, never its message, so a
question or a value in it cannot reach a log line.

### POST /chat/with-data — reasoning questions only

Used only when a question needs reasoning over the student's own values, for example
"can I graduate next term?". Factual questions (GPA, grades, schedule, deadlines) are
answered in the browser from the tool result and never reach this endpoint.

```json
request:  {
  "message": "...",
  "session_id": "...",
  "route_token": "eyJ... .9f...",
  "data": {
    "get_gpa": { "cumulative_gpa": "4.21", "scale": "5", "earned_hours": 96, "registered_hours": 99, "as_of_term": "الفصل الأول 1448/1449" },
    "get_plan_progress": { "completed_hours": 96, "remaining_hours": 3, "remaining_courses": [] }
  }
}
response: { "type": "answer", "answer": "...", "citations": [ { "title": "...", "article": "...", "url": "..." } ], "basis": "regulation" }
```

There is no `tool` field: the tool names are the keys of `data`, and `route_token` is the
one the reasoning reply carried, unchanged.

### The route token

A reasoning question is routed once, by `/chat`: the regex first, and the classifier when
the regex does not recognise the wording. The route decides the kind the answer is computed
from. `/chat/with-data` therefore cannot decide it again: a question only the classifier
routed would be refused there, because the regex alone does not know it.

`route_token` closes that gap. It is issued with every `reason` reply and binds the reply to
the question it answered:

- It is an HMAC-SHA256, under a server secret, over the user id, the SHA-256 of the
  message, the kind, the tools and the issue time, written as
  `base64url(payload).base64url(mac)`. It carries no student data and no text of the
  question.
- `/chat/with-data` checks the signature, the expiry, the student and the question, in that
  order, and then uses the token's kind and tools in place of the regex. A failure is 422
  `route_invalid`.
- It lives 15 minutes and is used once. The website keeps it in memory with the consent
  card and sends it back with the approved values; it is never stored and never logged.
- The secret is `KSU_ROUTE_SECRET` in `backend/.env`, read the way the other secrets are.
  Without it the process signs with a random secret and logs a warning that names no value,
  so the tokens of that process do not survive a restart.

`basis` says what the answer rests on: `"regulation"` when the regulation answers
the question, `"student_data"` when the student's own numbers are all there is (an
exam clash, for example) and the answer then ends with a sentence saying so. A
response without `basis` is a regulation answer.

- The keys of `data` must equal the tools the `route_token` names, which are the tools
  the `/chat` reply named in `tools`, one entry each. A missing entry is `data_missing`; a
  key the token did not name is `unknown_tool`.
- Each value carries exactly the fields the catalogue below lists for that tool, with
  the listed types — nothing more.

Rules:

- Sent only after the student approves **this one question** in the consent step.
  There is no standing approval and no batching.
- A verdict question — absences, academic warning, graduation, a GPA target, an exam
  clash — is answered from the computed numbers and a fixed template, with **no model
  call**: the numbers and the sentences are the same every time, so no reply can add a
  number of its own. Retrieval still runs, for the citations: an article the template
  states is cited from the retrieved chunk, and, when retrieval missed it, from the
  regulation's own title and URL in `backend/config/sources.toml`. A question no rule
  answers (`plan_week`) still goes to the model, which phrases the computed plan.
- The backend uses `data` in memory for this one answer only: never stored, never
  logged (see Privacy guarantees below).
- 401 without login.
- 422 with a short code, never a sentence:

| Code | Meaning |
| :--- | :--- |
| `message_empty` | The message is absent, empty or whitespace only. |
| `message_too_long` | The message is over 1000 characters. |
| `history_invalid` | `history` holds more than six turns, a role other than `user` or `assistant`, or a blank or over-1000-character content. |
| `route_invalid` | `route_token` is absent, or does not bind this question to this student: a wrong signature, an expired token, another student's token, or another question's. |
| `data_missing` | `data` is absent, empty, or lacks a tool the token names. |
| `data_too_large` | The whole request body is over 20 KB. |
| `unknown_tool` | A key of `data` is not a catalogue tool, or is a tool the token did not name. |
| `data_invalid` | A value does not match its tool's catalogue shape: an extra key, a missing key or a wrong type. |
| `bad_request` | The body is not a JSON object, or a field other than `message`, `route_token` and `data` does not fit. |

No 422 body repeats the request. FastAPI's own validation body carries the offending
input, which on this endpoint is a value the student approved for one answer, so `/chat`
and `/chat/with-data` always answer with one of these codes and nothing else
(`backend/tests/test_privacy_audit.py` drives every path with a sentinel in every field).

### Tool catalogue

Each tool reads one Edugate or LMS page in the student's own browser session. The
consent category is what the student allows or withdraws; the source page is the entry
for that tool in the [Phase 2 page map](phase2-page-map.md).

| Tool | Consent category | Source page | Returns exactly |
| :--- | :--- | :--- | :--- |
| `get_gpa` | `grades` | [Academic record](phase2-page-map.md#academic-record-get_gpa) | `{ "cumulative_gpa": "4.21", "scale": "5", "earned_hours": 96, "registered_hours": 99, "as_of_term": "الفصل الأول 1448/1449" }` |
| `get_grades` | `grades` | [Course results](phase2-page-map.md#course-results-get_grades) | `{ "term": "...", "courses": [ { "code": "...", "name": "...", "grade": "..." } ] }` — `grade` may be `null` |
| `get_lms_grades` | `grades` | [LMS grades](phase2-page-map.md#lms-blackboard-ultra) | `{ "courses": [ { "code": "SWE 483", "name": "...", "items": [ { "title": "...", "score": 8.5, "possible": 10, "status": "graded" } ] } ] }` — `code`, `score` and `possible` may be `null`, `status` is `graded`, `needs_grading` or `none` |
| `get_schedule` | `schedule` | [Class schedule](phase2-page-map.md#class-schedule-get_schedule) | `{ "term": "...", "classes": [ { "code": "...", "name": "...", "activity": "...", "section": "...", "days": [1, 3], "start": "08:00", "end": "08:50" } ] }` |
| `get_final_exams` | `schedule` | [Final exams](phase2-page-map.md#final-exams-get_final_exams) | `{ "exams": [ { "code": "...", "name": "...", "day": "الثلاثاء", "date": "6-07-1448", "time": "08:00", "location": "..." } ] }` — `day`, `date` and `location` may be `null` |
| `get_absences` | `attendance` | [Absences](phase2-page-map.md#absences-get_absences) | `{ "courses": [ { "code": "...", "name": "...", "absence_percent": 12.5, "absences": 3, "lates": 1 } ] }` |
| `get_plan_progress` | `plan` | [Study plan](phase2-page-map.md#study-plan-get_plan_progress) | `{ "completed_hours": 0, "remaining_hours": 0, "remaining_courses": [ { "code": "...", "name": "...", "hours": 3, "group": "...", "type": "...", "level": "..." } ] }` — `group` is the requirement group's title and `type` its نوع المجموعة as shown |
| `get_courses` | `lms` | [LMS course list](phase2-page-map.md#lms-blackboard-ultra) | `{ "courses": [ { "name": "...", "code": "SWE 999", "sections": [ "1", "2" ] } ] }` — `code` may be `null`, `sections` may be empty |
| `get_assignments` | `lms` | [LMS due dates](phase2-page-map.md#lms-blackboard-ultra) | `{ "items": [ { "title": "...", "course": "...", "due_at": "2026-11-21T23:59:00+03:00" } ] }` |

Consent categories: `grades`, `schedule`, `attendance`, `plan`, `lms`. The student
allows or withdraws each one separately, and Disconnect deletes everything the
extension stored.

Reading rules:

- `days` uses `1` = Sunday … `7` = Saturday. Edugate uses 1–5 (Sunday–Thursday); 6 and 7
  are allowed so other sources fit the same format. **Confirmed on a real Edugate page:
  1 = Sunday … 5 = Thursday** — a date is matched to a schedule day by
  `facts.contract_day(date)` (`isoweekday() % 7 + 1`), never by `isoweekday()` alone.
- Numbers that Edugate shows as text stay strings (`cumulative_gpa`, `scale`); counts,
  hours and percentages are numbers. The absences page prints `نسبة الغياب` without the
  % sign (`11.86`); the number is returned as shown, between 0 and 100.
- `due_at` is an ISO 8601 timestamp with the KSU offset (`+03:00`).
- `get_grades`: the page opens on the current term, where every grade is still empty;
  `term` is the option the selector shows. An empty grade cell and the not-recorded mark
  `ت` are both `null`, and the answer says the grades for that term are not recorded yet
  when all of them are `null`. The selector is never submitted: only the shown term is read.
- `get_schedule`: the page shows 12-hour times with ص/م; `start` and `end` are converted
  to 24-hour `HH:MM` (`01:00 م` -> `13:00`, `12:00 م` -> `12:00`, `12:05 ص` -> `00:05`).
  One `classes` entry per slot: a course that meets twice is two entries. The lecturer and
  the room are never read.
- `get_final_exams`: `day` is the Arabic weekday as shown, `date` the Hijri date as shown
  (`6-07-1448`, never converted), and `time` is 24-hour `HH:MM`. `day` and `date` are
  `null` while the exam is not scheduled yet. `location` joins the non-empty parts of
  الوحدة/المبنى/الطابق/الجناح/القاعة with ` - `, and is `null` when every part is empty
  or `---`.
- `get_plan_progress`: the two plan pages are split per requirement group, and the remaining
  page lists **every option** of each elective group (a six-hour group can list about twenty
  courses), so its rows are never summed. `completed_hours` is the sum of الساعات over the
  completed rows. Per group, matched by title across the two pages, the hours still needed are
  `max(the hours of its إجباري rows on the remaining page, N - completed)` where N is the
  group's `عدد الساعات` and `completed` the hours of that group on the completed page;
  `remaining_hours` is the sum over the groups. A student can exceed N with electives while a
  mandatory course is still missing (a four-hour group with six elective hours completed and a
  two-hour إجباري course still remaining needs two more hours, not zero). `group` is the group
  title as shown and `type` its نوع المجموعة as shown; both pages are fetched in the same
  session, and either one failing is the matching error.
- The three LMS tools read Blackboard Ultra's own JSON API in the student's session, not
  HTML (see [the page map](phase2-page-map.md#lms-blackboard-ultra)). Ultra lists a lecture
  and each lab or tutorial as separate memberships, so the sections of one subject are
  merged into one course and `sections` holds their numbers; `code` is `SWE 999` from the
  course id, or `null` when the id does not match the pattern.
- `get_assignments`: `due_at` is the item's `endDate` in Riyadh time (`+03:00`) and the
  items are soonest first. `course` is the student's merged current course when the item's
  `calendarId` is one of its ids, and otherwise the course name the calendar prints in
  `calendarNameLocalizable.rawValue` (`SWE483_77947_1_481: <name>` → `<name>`). An item
  without a title or without an end date is skipped, and only an answer whose `results` is
  not an array is `page_unreadable`. The item's description, source and calendar id are
  never returned.
- `get_lms_grades`: this LMS has **no overall or total column**, so the answer lists the
  gradebook columns instead: `visible` and `gradesReleased` and not `deleted`, in `position`
  order, titled by `effectiveColumnName`. Each item joins the column with the student's own
  grade row of it (`columnId`, and `userId` equal to the signed-in id): `score` is
  `displayGrade.score` when it is a number and `null` otherwise, `possible` is the column's
  `possible` (or the row's `pointsPossible`), and `status` is `GRADED` → `graded`,
  `NEEDS_GRADING` → `needs_grading`, and `none` when the row is absent or carries no
  status. Sections of one subject are merged under one course entry and a course with no
  items is left out. `instructorFeedback`, `averageScore`, `effectiveScore`, `manualGrade`,
  `manualScore` and the attempt URLs are never read, and an unknown key in a row is ignored.
  A row of another student is never taken.
- Five Edugate pages (final exams, schedule, course results, both study plan pages) answer a
  GET with a forward stub. The extension replays that stub's own form once, to the same
  URL; see [Forward pages](phase2-page-map.md#forward-pages). A page that is still a stub
  after that one replay is `page_unreadable`.
- A missing table or heading is reported as `page_unreadable`; no value is ever
  guessed.

### Website ↔ extension messages

The website talks to the extension with `chrome.runtime.sendMessage` under
`externally_connectable`. No other channel is used.

Website → extension:

```json
{ "kind": "ping" }
{ "kind": "run_tool", "request_id": "<uuid>", "tool": "<tool name>", "args": { } }
```

Extension → website:

```json
{ "kind": "pong", "version": "0.1.0", "categories_allowed": ["grades", "..."] }
{ "kind": "tool_result", "request_id": "<same uuid>", "ok": true, "data": { }, "read_at": "<ISO time>" }
{ "kind": "tool_result", "request_id": "<same uuid>", "ok": false, "error": "<code>" }
```

`data` holds exactly the fields the catalogue lists for `tool`, nothing more.
`read_at` is when the page was read, as ISO 8601.

Error codes (`error`, snake_case):

| Code | Meaning |
| :--- | :--- |
| `no_consent` | The student has not allowed this category. |
| `not_logged_in` | The student is not signed in to Edugate or LMS in this browser. |
| `page_unreadable` | The expected table or heading was not found, or the page could not be reached in the session. |
| `unknown_tool` | No such tool. |
| `timeout` | No result within 20 seconds. |
| `bad_request` | The message is malformed or missing a required field. |

Security rules:

- The extension accepts messages only from the listed origins — `http://localhost:3000`
  and the deployed site — and checks `sender.origin` on every message.
- The extension never returns cookies, page HTML, or any field a tool does not list.
- `categories_allowed` lists category names only, never data.
- The website shows "open the extension to allow <category>" on `no_consent`, and
  "log in to Edugate/LMS in this browser" on `not_logged_in`.
- The extension sends no request to KSU other than GET page reads and the replay of
  Edugate's own auto-submitted navigation form, to the same URL, once.

### Privacy guarantees

From the fixed rules of [ADR 0001](adr/0001-phase2-data-access.md); relaxing one needs
a new ADR.

1. KSU passwords are never collected, stored or transmitted by KSU Agent.
2. Personal academic values are never stored on the server and never written to logs.
3. Extension permissions stay minimal: the Edugate and LMS hosts and `storage` only;
   no `cookies`, no `webRequest`, no access to all sites.
4. Nothing is read without the student's consent for that data type; consent can be
   withdrawn at any time, and Disconnect deletes everything the extension stored.
5. Page content (announcements, files, emails) is data, never instructions to the AI.
6. Phase 3: every action is confirmed by the student in the extension's own screen, one
   action per confirmation, never batched or scheduled.
7. The LMS ids — the signed-in user id and the membership ids — are used to build the
   request and are never returned, stored or logged; only the fields the catalogue lists
   leave the extension. The gradebook's feedback, class average, effective score and manual
   grade never leave it either.

What the backend may log:

- `/chat` — may log the message length, the chosen tool name and the latency. Never the
  message text as personal data, never the `route_token`, and never any value the tool
  returned.
- `/chat/with-data` — may log the tool name, the byte size of `data` and the latency.
  Never `data` itself, never a field of it, never the message alongside it, and never the
  `route_token`.
- Neither endpoint may log a field of `data` in an error report or a traceback.
