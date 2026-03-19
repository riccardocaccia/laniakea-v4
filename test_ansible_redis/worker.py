from redis import Redis
from rq import Worker, Queue

r = Redis()
q = Queue(connection=r)

worker = Worker([q], connection=r)
worker.work()
