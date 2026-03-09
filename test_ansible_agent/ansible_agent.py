import os
import stat
import logging
from ansible_worker import AnsibleWorker

logger = logging.getLogger(__name__)

def run_ansible_step(job, playbook_url, requirements_url):
    uuid = job.deployment_uuid
    key_path = f"keys/{uuid}.pem"
    
    worker = AnsibleWorker(playbook_url, requirements_url, uuid)
    
    try:
        success_prep, msg = worker.prepare_environment()
        if not success_prep:
            logger.error(f"[{uuid}] Errore preparazione Ansible: {msg}")
            return False

        # Identificazione Bastion
        bastion = "0.0.0.0"
        if job.selected_provider == 'openstack':
            bastion = job.cloud_providers.openstack.private_network_proxy_host or "0.0.0.0"

        success = worker.execute_deployment(
            target_ip=job.vm_ip,
            ssh_key_path=key_path,
            bastion_ip=bastion
        )
        
        #worker.cleanup() # Pulisce /tmp/uuid
        return success

    except Exception as e:
        logger.error(f"[{uuid}] Eccezione in Ansible Step: {e}")
        worker.cleanup()
        return False
