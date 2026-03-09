import json
import docker
import os
import yaml
import logging
import time
from typing import Optional
from pydantic import BaseModel, ValidationError, model_validator
from db_handlers import start_log_deployment, update_log_status
from auth_utils.openstack_auth import get_keystone_token
from vault_utils import get_secrets
from ansible_agent import run_ansible_step
from destroy import run_destroy

# Configurazione Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("orchestrator.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# classi

class OpenPort(BaseModel):
    port: int
    protocol: str
    cidr: str

class AuthConfig(BaseModel):
    aai_token: Optional[str] = None
    sub: str
    group: str = "default"

class OpenStackInputs(BaseModel):
    flavor: str
    image: str
    network_type: str = "private"
    open_ports: list[OpenPort] = []

class AWSInputs(BaseModel):
    instance_type: str
    image: str
    network_type: str = "private"
    open_ports: list[OpenPort] = []

class OpenStackProvider(BaseModel):
    os_auth_url: str
    os_project_id: str
    region_name: str = "RegionOne"
    private_net_name: str = "private_net"
    public_net_name: str = "public_net"
    private_network_proxy_host: Optional[str] = None
    inputs: OpenStackInputs

class AWSProvider(BaseModel):
    region: str
    bastion_ip: Optional[str] = None
    inputs: AWSInputs

class CloudProviders(BaseModel):
    aws: Optional[AWSProvider] = None
    openstack: Optional[OpenStackProvider] = None

class Job(BaseModel):
    deployment_uuid: str
    auth: AuthConfig
    selected_provider: str
    cloud_providers: CloudProviders
    vm_ip: Optional[str] = None

# TERRAFORM ORCHESTRATION

def run_orchestration(job: Job):
    uuid = job.deployment_uuid
    provider = job.selected_provider.lower()
    group = job.auth.group
    tf_dir = os.path.abspath(f"terraform/{provider}")

    logger.info(f"[{uuid}] Avvio provisioning infrastruttura su {provider}...")
    start_log_deployment(uuid)
    update_log_status(uuid, "INFRASTRUCTURE_PROVISIONING_TERRAFORM")

    try:
        client = docker.from_env()
        
        # recupero segreti da vault
        secrets = get_secrets(f"SECRET/infrastructure/{provider}/{group}")
        if not secrets:
            raise Exception(f"Segreti non trovati in Vault per il gruppo: {group}")
        
        public_key = secrets.get('ssh_key_public')
        if not public_key:
            raise Exception("ERRORE: ssh_key_public non trovata nei segreti del Vault!")

        tf_vars = {
            "TF_VAR_deployment_uuid": str(uuid),
            "TF_VAR_ssh_public_key": str(public_key).strip()
        }

        #variabili specifiche per i diversi provider
        if provider == 'openstack':
            os_data = job.cloud_providers.openstack
            os_token = ""

            if job.auth.aai_token and job.auth.aai_token.strip():
                os_token = get_keystone_token(job.auth.aai_token, os_data.os_auth_url, os_data.os_project_id)
            
            tf_vars.update({
                "TF_VAR_os_auth_url": os_data.os_auth_url,
                "TF_VAR_os_tenant_id": os_data.os_project_id,
                "TF_VAR_os_token": os_token,
                "TF_VAR_os_app_cred_id": secrets.get('application_credential_id', ""),
                "TF_VAR_os_app_cred_secret": secrets.get('application_credential_secret', ""),
                "TF_VAR_os_region": os_data.region_name,
                "TF_VAR_private_network_name": os_data.private_net_name,
                "TF_VAR_public_network_name": os_data.public_net_name,
                "TF_VAR_flavor_name": os_data.inputs.flavor,
                "TF_VAR_image_name": os_data.inputs.image,
                "TF_VAR_network_type": os_data.inputs.network_type,
                "TF_VAR_bastion_ip": os_data.private_network_proxy_host or "0.0.0.0",
                "TF_VAR_open_ports": json.dumps([p.model_dump() for p in os_data.inputs.open_ports])
            })

        elif provider == 'aws':
            aws_data = job.cloud_providers.aws
            tf_vars.update({
                "TF_VAR_aws_access_key": secrets['aws_access_key'],
                "TF_VAR_aws_secret_key": secrets['aws_secret_key'],
                "TF_VAR_aws_region": aws_data.region,
                "TF_VAR_instance_type": aws_data.inputs.instance_type,
                "TF_VAR_image": aws_data.inputs.image,
                "TF_VAR_network_type": aws_data.inputs.network_type,
                "TF_VAR_bastion_ip": aws_data.private_network_proxy_host or "0.0.0.0",
                "TF_VAR_open_ports": json.dumps([p.model_dump() for p in aws_data.inputs.open_ports])
            })

        # esecuzione Terraform 
        logger.info(f"[{uuid}] Lancio container Terraform per {provider}...")

        client.containers.run(
            image="hashicorp/terraform:1.5",
            entrypoint="/bin/sh",
            command="-c 'terraform init -no-color && terraform apply -auto-approve -no-color'",
            volumes={tf_dir: {'bind': '/src', 'mode': 'rw'}},
            working_dir="/src",
            environment=tf_vars,
            remove=True
        )

        # recupero IP della vm creata
        logger.info(f"[{uuid}] Recupero output vm_ip...")

        vm_ip_bytes = client.containers.run(
            image="hashicorp/terraform:1.5",
            command="output -raw vm_ip",
            volumes={tf_dir: {'bind': '/src', 'mode': 'ro'}},   # qui read only 
            working_dir="/src",
            remove=True
        )
        vm_ip = vm_ip_bytes.decode('utf-8').strip()
        job.vm_ip = vm_ip
        
        # Wait the deployment to be completed
        logger.info(f"[{uuid}] Attesa di 30 secondi per l'avvio di SSH su Rocky...")
        time.sleep(30)

        # Fine task terraform
        update_log_status(uuid, "INFRASTRACTURE_READY", ip_address=vm_ip)
        logger.info(f"[{uuid}] Infrastruttura creata con successo. IP: {vm_ip}")

        ########### PARSING TEMPLATE YAML
        with open("repo_url_template.yml", "r") as yf:
            tpl = yaml.safe_load(yf)
        pb_url = tpl['resources']['ansible']['playbook']
        req_url = tpl['resources']['ansible']['requirements']

        # ANSIBLE STEP + FAIL-SAFE
        ansible_ok = run_ansible_step(job, pb_url, req_url)

        if not ansible_ok:
            logger.error(f"[{uuid}] Ansible fallito! Eseguo DESTROY di emergenza...")
            run_destroy(job) # Pulisce la VM su OpenStack/AWS
            update_log_status(uuid, "FAILED", logs="Ansible fallito. VM distrutta automaticamente.")
        else:
            update_log_status(uuid, "READY")
            logger.info(f"[{uuid}] Deployment completato con successo.")

    except Exception as e:
        logger.error(f"[{uuid}] Errore critico Terraform: {e}")
        run_destroy(job)
        update_log_status(uuid, "FAILED", logs=str(e))


# main block

if __name__ == "__main__":
    try:
        with open("deployment_info.json", "r") as f:
            raw_data = json.load(f)
        
        job_request = Job(**raw_data)
        run_orchestration(job_request)
    except Exception as e:
        logger.error(f"Errore caricamento Job: {e}")
