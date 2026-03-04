import json
import docker
import os
import logging
from auth_utils.openstack_auth import get_keystone_token
from db_handlers import update_log_status

# Configurazione logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

def destroy():
    tf_dir = os.path.abspath("terraform")

    # Caricamento configurazione dal JSON
    if not os.path.exists("deployment_info.json"):
        logger.error("File deployment_info.json non trovato!")
        return

    with open("deployment_info.json", "r") as f:
        data = json.load(f)

    uuid = data['deployment_uuid']
    os_data = data['cloud_providers']['openstack']

    logger.info(f"Avvio distruzione infrastruttura per il job: {uuid}...")

    try:
        # 1. Ottenimento Token OpenStack (fresco)
        logger.info("Richiesta nuovo token Keystone...")
        token = get_keystone_token(
            data['auth']['aai_token'], 
            os_data['os_auth_url'], 
            os_data['os_project_id']
        )
        
        if not token:
            raise Exception("Impossibile ottenere il token per il destroy.")

        # 2. Configurazione variabili ambiente per Terraform
        # Passiamo tutte le variabili obbligatorie definite nel variables.tf
        tf_vars = {
            "TF_VAR_os_auth_url": os_data['os_auth_url'],
            "TF_VAR_os_token": token,
            "TF_VAR_os_tenant_id": os_data['os_project_id'],
            "TF_VAR_os_app_cred_id": "",     # Placeholder per evitare errori
            "TF_VAR_os_app_cred_secret": "", # Placeholder per evitare errori
            "TF_VAR_bastion_ip": os_data.get('private_network_proxy_host', '127.0.0.1'),
            "TF_VAR_image_name": "dummy",    # Non serve per il destroy ma è obbligatoria nel file .tf
            "TF_VAR_flavor_name": "dummy",   # Idem
            "TF_VAR_ssh_public_key": "dummy",# Idem
            "TF_VAR_deployment_uuid": uuid
        }

        # 3. Lancio Container Docker
        logger.info("Lancio container Terraform per il destroy...")
        client = docker.from_env()
        
        # Usiamo /bin/sh per concatenare init e destroy
        client.containers.run(
            image="hashicorp/terraform:1.5",
            entrypoint="/bin/sh",
            command="-c 'terraform init -no-color && terraform destroy -auto-approve -no-color'",
            volumes={tf_dir: {'bind': '/src', 'mode': 'rw'}},
            working_dir="/src",
            environment=tf_vars,
            remove=True,
            detach=False
        )

        logger.info("--- RISORSE ELIMINATE CON SUCCESSO ---")
        update_log_status(uuid, "DESTROYED", logs="Infrastruttura rimossa correttamente tramite script di emergenza.")

    except Exception as e:
        logger.error(f"Errore critico durante il destroy: {e}")
        # Se possibile, proviamo a loggare il fallimento sul DB
        try:
            update_log_status(uuid, "FAILED_DESTROY", logs=str(e))
        except:
            pass

if __name__ == "__main__":
    destroy()
