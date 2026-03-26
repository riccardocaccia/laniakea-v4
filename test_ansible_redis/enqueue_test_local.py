from redis import Redis
from rq import Queue
import json

r = Redis()
q = Queue(connection=r)

with open("deployment_info.json", "r") as f:
    job1 = json.load(f)

import copy
job2 = copy.deepcopy(job1)
job2["deployment_uuid"] = "deploy-2"

from terraform_agent import Job, run_orchestration

result1 = q.enqueue(run_orchestration, Job(**job1), job_timeout=7200)
result2 = q.enqueue(run_orchestration, Job(**job2), job_timeout=7200)

print(f"Job 1 enqueued: {result1.id}")
print(f"Job 2 enqueued: {result2.id}")
