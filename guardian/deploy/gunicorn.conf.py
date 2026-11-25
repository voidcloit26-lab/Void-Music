# Run from the repository root as the independent non-root service user.
# Reverse proxy must enforce TLS, per-IP limits and request-body limits.
import os

bind = os.environ.get("VOID_GUARDIAN_BIND", "127.0.0.1:8780")
workers = 1
threads = 4
timeout = 20
graceful_timeout = 15
keepalive = 2
limit_request_line = 2048
limit_request_fields = 24
limit_request_field_size = 2048
accesslog = None
errorlog = "-"
capture_output = False
# Required: one worker, because challenge state and global rate budgets are in memory.
