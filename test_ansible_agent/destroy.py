import os
import json
import docker
import logging
from vault_utils import get_secrets
from auth_utils.openstack_auth import get_keystone_token # Importiamo lo scambiatore

logger = logging.getLogger(__name__)

def run_destroy(job):
    uuid = job.deployment_uuid
    provider = job.selected_provider.lower()
    group = job.auth.group
    tf_dir = os.path.abspath(f"terraform/{provider}")

    logger.info(f"[{uuid}] Avvio DISTRUZIONE con TOKEN su {provider}...")

    try:
        client = docker.from_env()
        secrets = get_secrets(f"SECRET/infrastructure/{provider}/{group}")
        os_data = job.cloud_providers.openstack

        os_token = ""
        if job.auth.aai_token and job.auth.aai_token.strip():
            logger.info(f"[{uuid}] Scambio token AAI per il destroy...")
            os_token = get_keystone_token(
                job.auth.aai_token, 
                os_data.os_auth_url, 
                os_data.os_project_id
            )


        tf_vars = {
            "TF_VAR_deployment_uuid": str(uuid),
            "TF_VAR_os_auth_url": os_data.os_auth_url,
            "TF_VAR_os_region": os_data.region_name,
            "TF_VAR_os_tenant_id": os_data.os_project_id,
            "TF_VAR_os_token": os_token,
            "TF_VAR_os_app_cred_id": secrets.get('application_credential_id', ""),
            "TF_VAR_os_app_cred_secret": secrets.get('application_credential_secret', ""),
            "TF_VAR_ssh_public_key": "dummy",
            "TF_VAR_private_network_name": os_data.private_net_name,
            "TF_VAR_public_network_name": os_data.public_net_name,
            "TF_VAR_flavor_name": "dummy",
            "TF_VAR_image_name": "dummy",
            "TF_VAR_network_type": "public",
            "TF_VAR_bastion_ip": "0.0.0.0",
            "TF_VAR_open_ports": json.dumps([])
        }

        client.containers.run(
            image="hashicorp/terraform:1.5",
            entrypoint="/bin/sh",
            command="-c 'terraform init -no-color && terraform destroy -auto-approve -no-color'",
            volumes={tf_dir: {'bind': '/src', 'mode': 'rw'}},
            working_dir="/src",
            environment=tf_vars,
            remove=True
        )
        logger.info(f"[{uuid}] Risorse distrutte con successo.")

    except Exception as e:
        logger.error(f"Errore critico durante il destroy: {e}")
