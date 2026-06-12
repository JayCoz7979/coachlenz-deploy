#!/bin/sh
exec python -m backend.workers.$WORKER_NAME
