import json
import docker
import os
import logging
from auth_utils.openstack_auth import get_keystone_token
from db_handlers import update_log_status

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def destroy():
    tf_dir = os.path.abspath("terraform")
    
    with open("deployment_info.json", "r") as f:
        data = json.load(f)
    
    uuid = data['deployment_uuid']
    os_data = data['cloud_providers']['openstack']
    
    logger.info(f"Avvio distruzione infrastruttura per {uuid}...")
    
    # 1. Ottieni Token fresco
    token = get_keystone_token(data['auth']['aai_token'], os_data['os_auth_url'], os_data['os_project_id'])
    
    # 2. Lancio Destroy via Docker
    client = docker.from_env()
    tf_vars = {
        "TF_VAR_os_token": token,
        "TF_VAR_os_tenant_id": os_data['os_project_id'],
        "TF_VAR_bastion_ip": os_data.get('private_network_proxy_host', '127.0.0.1'),
        "TF_VAR_image_name": "dummy",
        "TF_VAR_flavor_name": "dummy",
        "TF_VAR_ssh_public_key": "dummy",
        "TF_VAR_deployment_uuid": uuid
    }

    try:
        client.containers.run(
            image="hashicorp/terraform:1.5",
            command="destroy -auto-approve",
            volumes={tf_dir: {'bind': '/src', 'mode': 'rw'}},
            working_dir="/src",
            environment=tf_vars,
            remove=True
        )
        logger.info("Infrastruttura distrutta con successo.")
        update_log_status(uuid, "DESTROYED", logs="Infrastruttura rimossa correttamente.")
    except Exception as e:
        logger.error(f"Errore durante il destroy: {e}")

if __name__ == "__main__":
    destroy()
