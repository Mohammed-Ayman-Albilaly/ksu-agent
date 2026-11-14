"""Accounts for KSU Agent: register, login, logout, me and email verification.

Routes live in routes.py and follow docs/api-contract.md ("Planned" section).
Email verification by one-time code is built in but switched off by
`email_verification = false` in backend/config/auth.toml.
"""
