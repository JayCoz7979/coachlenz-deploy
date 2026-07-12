"""Shared slowapi limiter instance.

Lives in its own module so both main.py (which registers it on the app + error
handler) and the routers (which decorate individual endpoints) import the SAME
Limiter. Keyed by client IP.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
