"""Shared slowapi limiter instance.

Lives in its own module so both main.py (which registers it on the app + error
handler) and the routers (which decorate individual endpoints) import the SAME
Limiter. Keyed by client IP.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

# Keyed by client IP. get_remote_address reads request.client.host, which is the
# REAL caller only because uvicorn runs with --proxy-headers --forwarded-allow-ips
# (see backend/Dockerfile / railway.toml) and rewrites it from Railway's
# X-Forwarded-For. We deliberately do NOT parse X-Forwarded-For ourselves here: a
# hand-rolled key_func that trusts the raw header is spoofable (an attacker rotating
# the header would mint unlimited buckets and bypass every limit). Trusting the
# platform proxy to set it is the safe path.
limiter = Limiter(key_func=get_remote_address)
