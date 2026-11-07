# Decisions log — KSU Agent

Two sources only: the Sprint 0 report (`Sprint0_Ksu_Agent.pdf`, document version 1.0) and the change message of 2026-11-07.

The Sprint 0 report states that its vision, backlog, team and technical readiness, and release plan were established during Sprint 0 (Sunday 11 October – Thursday 22 October 2026). It gives no individual decision dates, so every Sprint 0 row below is dated **not stated** and sourced to the section that contains it. Fields the source does not cover are recorded as **not stated**; nothing is inferred.

Sprint 0 IDs use the `SD-nn` prefix so they do not collide with the report's own `D-01`–`D-05` (dependency IDs) or with the `D1`–`D4` change records below.

## Sprint 0 decisions

| ID | Date | Decision | Reason | Alternatives | Approved by | Source section |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| SD-01 | not stated | Product vision: a bilingual (Arabic/English) AI student helper that gives cited answers about KSU and, in later phases, reads and acts on the student's own Edugate/LMS data. | not stated | not stated | not stated | §1.1 |
| SD-02 | not stated | Deliver in three phases — Phase 1 knowledge (public documents, RAG), Phase 2 personal read (own Edugate/LMS data, read-only), Phase 3 personal actions (write, per action, student confirms). | not stated | not stated | not stated | §1.1 |
| SD-03 | not stated | Phase 1 success measures: ≥85% correct on a 100-question evaluation set, 100% of answers cited, median response time <5 s. | not stated | not stated | not stated | §1.1 |
| SD-04 | not stated | First usable release at the end of Sprint 2 = complete Phase 1 knowledge assistant over a responsive web chat, Arabic and English. | not stated | not stated | not stated | §1.1, §8 |
| SD-05 | not stated | Backlog priority scale is MoSCoW from 1 to 4 (Must / Should / Could / Would). | not stated | not stated | Project supervisor (Product Owner) and all three team members (backlog review, §2) | §2.1 |
| SD-06 | 22 Oct 2026 | Sprint 1 baseline: US-01, US-03, US-05, US-07, US-10; TF-13; KA-01–KA-07, KA-10; NFR-01–NFR-04, NFR-09, NFR-11, NFR-12. | not stated | not stated | Project supervisor (Product Owner) and team | §2.6 |
| SD-07 | 22 Oct 2026 | Sprint 2 baseline: US-02, US-04, US-06, US-08, US-09; TF-15, TF-16; KA-08, KA-09; all Phase 1 NFRs plus NFR-05 and NFR-10. | not stated | not stated | Project supervisor (Product Owner) and team | §2.6 |
| SD-08 | not stated | Four development sprints; Phase 1 released to students at end of Sprint 2 (19 Nov 2026), final release 17 Dec 2026 with Phase 2 and Phase 3 to the extent KSU access allows. | not stated | not stated | not stated (roadmap reviewed with the Project supervisor / Product Owner, §8.2; review date not stated) | §8 |
| SD-09 | not stated | Phase 1 is built before Phase 2 and 3 because it uses only public documents and has no external dependency; Sprint 1 builds the foundations every later story needs. | not stated | not stated | not stated | §8.1 |
| SD-10 | not stated | Must-have stories are scheduled before Should and Could items; US-16 and US-17 (Could) are stretch goals and move out first if capacity is short. | not stated | not stated | not stated | §8.1 |
| SD-11 | not stated | Capacity plan: Sprint 0 holds 37 points of set-up work, Sprint 1 is planned at 31 points, Sprint 2 at 18 points plus two technical tasks; Sprint 1 velocity adjusts Sprints 3 and 4, with lighter sprints in exam weeks. | not stated | not stated | not stated | §8.1 |
| SD-12 | not stated | Front end: Next.js 15 (React, TypeScript) with Tailwind CSS. | Built-in RTL and Arabic/English support for the chat (SF-07). | not stated | not stated | §4 |
| SD-13 | not stated | Back end: Python 3.12 with FastAPI. | Fast to build, and the team controls the agent loop and guardrails. | not stated | not stated | §4 |
| SD-14 | not stated | AI: a hosted LLM API with tool use, chosen in Sprint 1 (TF-13). | Strong Arabic and reliable tool calling matter most; cost and external dependency are accepted and capped by NFR-12 (100 SAR/month). | not stated (candidates compared in TF-13) | not stated | §4, §7.1 |
| SD-15 | not stated | Embeddings: BGE-M3 or multilingual-E5, decided by spike TF-06; one index for Arabic and English. | Multilingual embeddings keep Arabic and English in one index. | not stated (the two candidates are the open comparison) | not stated | §4, §7.4 |
| SD-16 | not stated | A reranker is part of the AI and retrieval stack (specific reranker to be chosen by 29 Oct 2026). | not stated | not stated | not stated | §4, §7.4 |
| SD-17 | not stated | Database: PostgreSQL 16 with pgvector as the single store for vectors, BM25-style full-text search, structured calendar and study plan tables, ratings and logs. | Keeps the stack small for a three-person team. | not stated | not stated | §4, §7.1 |
| SD-18 | not stated | Chunking by regulation article or study plan level. | Keeps citations precise. | not stated | not stated | §7.1 |
| SD-19 | not stated | Dates and prerequisites are served from structured SQL tables, not from similarity search. | These need exact answers. | similarity search | not stated | §7.1 |
| SD-20 | not stated | One agent core with a plain tool-calling loop; each phase only adds tools. | One code path for all three phases so later phases do not rewrite earlier work; slightly more code than an agent framework but full control over guardrails and confirmation. | an agent framework (to be recorded in the ADR, TF-10) | not stated | §7.1 |
| SD-21 | not stated | Edugate/LMS access goes through a KSU adapter: a Chrome extension (Manifest V3) in the student's own session now, an official OAuth/API adapter if KSU approves; swapping it changes only the adapter. | Passwords never reach the server; the extension can break when pages change (R-06). | official OAuth/API | not stated | §4, §7.1 |
| SD-22 | not stated | Data migration: Alembic for schema migrations and a Python ingestion pipeline for PDF/HTML sources; no legacy data to migrate. | Versioned schema changes and repeatable ingestion/re-ingestion (SF-09). | not stated | not stated | §4 |
| SD-23 | not stated | Development and version control: Git and GitHub with branch protection and PRs, VS Code, Docker Desktop / Docker Compose v2, Trello. | Same environment for all three members; reviewed changes only; task tracking. | not stated | not stated | §4 |
| SD-24 | not stated | Testing and deployment: pytest, Playwright, evaluation-set runner, GitHub Actions, Docker. | Unit, end-to-end and answer-quality tests on every PR; container-based deployment to staging. | not stated | not stated | §4 |
| SD-25 | not stated | Roles: project supervisor as Product Owner; Ahmed Ali Alqahtani Scrum Master and agent-core/backend owner; Sannad Alkhemali Product Owner proxy and RAG/data owner; Mohannad Alblali QA/DevOps lead and front-end owner. | Each technical area has one owner and one backup so work continues if someone is unavailable. | not stated | not stated | §5 |
| SD-26 | not stated | Working agreements: every task lives on the Trello board; one card per person in In Progress; PRs reviewed within 24 hours; blockers raised in the stand-up the same day. | not stated | not stated | not stated | §2.7 |
| SD-27 | not stated | Backlog change process: add the change, discuss priority, check sprint impact, check effort, decide current or later sprint, then update Trello and the plan; scope decisions go in the repository decision log. | Keeps changes from affecting the current sprint without a clear reason. | not stated | not stated | §2.6 |
| SD-28 | not stated | Definition of Ready: "As a… I want… so that…" form, 2–5 testable acceptance criteria, estimated by the whole team at ≤8 points, sources available, dependencies named. | not stated | not stated | not stated | §2.6 |
| SD-29 | not stated | Out of scope: KSU passwords on KSU Agent servers, automated/batch/scheduled actions without confirmation, native iOS/Android apps, voice interaction, faculty/staff features, universities other than KSU, an official Edugate/LMS integration unless KSU approves. | not stated | not stated | not stated | §9.1 |
| SD-30 | not stated | Cost plan: free/open-source tooling (0 SAR), LLM API capped at 100 SAR/month for about three months (up to 300 SAR), free-tier hosting (0 SAR), no paid external security assessment (0 SAR). | not stated | not stated | not stated | §9.2, NFR-12 |
| SD-31 | not stated | Hosting must be inside the Kingdom if personal data is stored (Phase 2), per PDPL. | PDPL. | not stated | not stated | §3 |
| SD-32 | not stated | Sprints are two weeks, Sunday to Thursday, with dates adjusted to the official KSU academic calendar (exams and breaks). | not stated | not stated | not stated | §8.2 |
| SD-33 | not stated | Test approach: pytest unit tests for tools, agent loop and endpoints; integration tests against PostgreSQL in Docker; Playwright end-to-end tests at phone and desktop sizes in Arabic and English; evaluation set on every change; UAT on staging from Sprint 2; a mock KSU adapter with fake student records, no real personal data in tests. | not stated | not stated | not stated | §9.7 |
| SD-34 | not stated | Definition of Done: PR reviewed by one other member, unit tests pass in CI, evaluation score does not drop, answers cite their source, both languages tested, no secrets/passwords/student data committed or logged, feature demoed at the Sprint Review, docs updated. | not stated | not stated | not stated | §9.7 |
| SD-35 | not stated | Defect handling: Trello Bug cards with reproduction steps, expected/actual and severity; Critical and High fixed in the current sprint before new work; every fix gets a regression test and is retested by someone other than the developer. | not stated | not stated | not stated | §9.7 |
| SD-36 | not stated | Status reporting: weekly report plus one at the end of each sprint, prepared by the Scrum Master, shared with team and instructor via Trello and the project channel. | not stated | not stated | not stated | §9.6 |
| SD-37 | not stated | Project documents are kept in the repository `/docs` folder; training material under `docs/training`; the ADR under `docs/adr`. | Keeps documents shared and in one place. | not stated | not stated | §3, §6, §10.2 |
| SD-38 | not stated | Reference REF-01 is the KSU "Regulations of Study and Examinations" PDF hosted on cba.ksu.edu.sa. | not stated | not stated | not stated | §10.1 (superseded by D2 below) |

### Open items in the Sprint 0 report — not decisions

Section 7.4 lists five items still open at Sprint 0: the LLM provider/model (TF-13), the embedding model and reranker (TF-06), agent framework vs plain loop (TF-10), the Phase 2 access route (depends on KSU's reply, D-02), and the hosting location for personal data. They are recorded here as open, not as decisions.

## Changes of 2026-11-07

Approved by the team and the supervisor.

| ID | Date | Decision | Reason | Alternatives | Approved by | Source section |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| D1 | 2026-11-07 | Scope narrowed from all KSU majors to CCIS undergraduates. | Time; sources must be verifiable. | not stated | Team and supervisor | Change message, 2026-11-07 (narrows §1.1, §9.1) |
| D2 | 2026-11-07 | REF-01 replaced by the current undergraduate regulation with executive rules, version 2, on dar.ksu.edu.sa. | The 1436H copy is outdated. | not stated | Team and supervisor | Change message, 2026-11-07 (replaces REF-01, §10.1) |
| D3 | 2026-11-07 | The repository is public. | not stated | not stated | Team and supervisor | Change message, 2026-11-07 (affects TF-01, §2.2) |
| D4 | 2026-11-07 | DevAI Desktop builds the code; VS Code is used only for reading and review. | not stated | not stated | Team and supervisor | Change message, 2026-11-07 (affects §4 development tools) |
