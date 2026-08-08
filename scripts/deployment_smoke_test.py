import os,httpx
base=os.environ.get("BACKEND_URL","").rstrip("/")
if not base:raise SystemExit("BACKEND_URL is required")
for path in ("/health","/ready","/api/config"):
    response=httpx.get(base+path,timeout=90);response.raise_for_status();print(path,response.status_code)
