"""Single source of truth for the application version.

Used by FastAPI metadata, /api/health and /api/ready. Release notes (CHANGELOG, README
badge) are written by hand, but tests/test_version.py fails if they drift from this."""
VERSION = '2.2.0'
