from redis import Redis
from rq import Worker, Queue

r = Redis(host='212.189.205.167', port=6379, password='admin')
# autenticato come agente1, vede solo coda_agente1
q = Queue('coda_agente1', connection=r)
worker = Worker([q], connection=r)
worker.work()
