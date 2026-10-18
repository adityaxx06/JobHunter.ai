"""Database package: psycopg access to Supabase PostgreSQL (Phase 3).

Only the backend and worker import this. Never import from frontend code
(frontend is a separate Next.js app and must not receive any secrets).
All queries here are parameterized — no SQL string interpolation of values.
"""
