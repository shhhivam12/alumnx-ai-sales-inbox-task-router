"""List grader-visible tasks from our deployed backend without modifying them."""

import os

import httpx


base = os.environ.get("BACKEND_BASE_URL", "").rstrip("/")
candidate = "mahendrushivam123@gmail.com"
if not base:
    raise SystemExit("BACKEND_BASE_URL is required")
response = httpx.get(base + "/tasks", params={"candidate_id": candidate}, timeout=30)
response.raise_for_status()
print(response.json())
