import os,httpx
base=os.environ.get("TASK_API_BASE_URL","").rstrip("/");candidate="mahendrushivam123@gmail.com"
if not base:raise SystemExit("TASK_API_BASE_URL is required")
r=httpx.get(base+"/tasks",params={"candidate_id":candidate},timeout=30);r.raise_for_status();print(r.json())
