"""Security Layer — permission verification, authentication, encryption, privacy protection.

Encryption has a real, if narrowly scoped, implementation as of Sprint
6.20 (Permission & Encryption Audit): secret_store.py's SecretStore
wraps OS-level credential storage (keyring) for API keys and the
VTube Studio auth token — the two highest-risk plaintext secrets this
codebase held, per that sprint's own research. The SQLite databases
remain plaintext at rest, a separate, larger, deliberately deferred
decision (the user's own direct choice, not an oversight) — see
docs/backlog/technical_debt.md.
"""
