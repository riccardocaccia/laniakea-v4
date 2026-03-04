import psycopg2
from psycopg2.extras import RealDictCursor
import datetime

def get_db_connection():
    return psycopg2.connect(
        host="localhost",
        database="test_orchestrator_db",
        user="admin",
        password="admin"
    )

def start_log_deployment(deployment_uuid, status="IN_PROGRESS"):
    conn = get_db_connection()
    cur = conn.cursor()
    # Usiamo creation_time e update_time come nel tuo schema
    cur.execute(
        """
        INSERT INTO deployments (uuid, status, creation_time, update_time) 
        VALUES (%s, %s, %s, %s) 
        ON CONFLICT (uuid) 
        DO UPDATE SET status=%s, update_time=%s
        """,
        (deployment_uuid, status, datetime.datetime.now(), datetime.datetime.now(), status, datetime.datetime.now())
    )
    conn.commit()
    cur.close()
    conn.close()

def update_log_status(deployment_uuid, status, logs=None, ip_address=None):
    conn = get_db_connection()
    cur = conn.cursor()
    # Usiamo status_reason (TEXT) per i log e outputs per l'IP
    # come definito nel tuo schema.sql
    cur.execute(
        """
        UPDATE deployments 
        SET status=%s, status_reason=%s, update_time=%s, outputs=%s 
        WHERE uuid=%s
        """,
        (status, logs, datetime.datetime.now(), ip_address, deployment_uuid)
    )
    conn.commit()
    cur.close()
    conn.close()
