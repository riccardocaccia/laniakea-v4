from redis import Redis
from rq import Queue

r = Redis(host='212.189.205.167', port=6379, username='agente1' ,password='secret_agente1')
queues = Queue.all(connection=r)
for q in queues:
    print(f"Coda: {q.name} - Job in attesa: {q.count}")
