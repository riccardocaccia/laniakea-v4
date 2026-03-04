import json
import subprocess
import docker
import os
import logging
from typing import Optional
from pydantic import BaseModel, ValidationError, model_validator
from db_handlers import start_log_deployment, update_log_status
from auth_utils.openstack_auth import get_keystone_token

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("orchestrator.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

########################################################

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
    storage_size: Optional[str] = None
    model_config = {"extra": "ignore"}

class OpenStackProvider(BaseModel):
    os_auth_url: str
    os_project_id: str
    os_region_name: str
    ssh_key: str
    private_network_proxy_host: Optional[str] = None
    inputs: OpenStackInputs
    model_config = {"extra": "ignore"}

class CloudProviders(BaseModel):
    aws: Optional[dict] = None
    openstack: Optional[OpenStackProvider] = None
    model_config = {"extra": "forbid"}

class OrchestratorConfig(BaseModel):
    target_provider: str
    desired_orchestrator: str = "terraform"
    model_config = {"extra": "ignore"}

class Job(BaseModel):
    deployment_uuid: str
    auth: AuthConfig
    selected_provider: str
    orchestrator: OrchestratorConfig
    cloud_providers: CloudProviders

    @model_validator(mode="after")
    def validate_provider_selection(self):
        provider = self.selected_provider.lower()
        self.orchestrator.target_provider = provider

        if provider == "aws":
            if not self.cloud_providers.aws:
                raise ValueError("AWS selezionato ma configurazione aws mancante")
        elif provider == "openstack":
            if not self.cloud_providers.openstack:
                raise ValueError("OpenStack selezionato ma configurazione mancante")
        else:
            raise ValueError(f"Provider non supportato: {provider}")

        return self

###################################################################################

def run_orchestration(job: Job):
    uuid = job.deployment_uuid
    provider = job.orchestrator.target_provider
    tf_dir = os.path.abspath("terraform")

    logger.info(f"Ricevuto Job {uuid}. Inizializzazione su Database...")
    start_log_deployment(uuid)

    try:
        # 1. Autenticazione OpenStack
        token_os = ""
        if provider == "openstack":
            os_data = job.cloud_providers.openstack
            logger.info(f"[{uuid}] Scambio token AAI con Keystone...")
            token_os = get_keystone_token(job.auth.aai_token, os_data.os_auth_url, os_data.os_project_id)
            if not token_os:
                raise Exception("Scambio token fallito: verifica aai_token o permessi Keystone")

        # 2. Terraform via Docker
        logger.info(f"[{uuid}] Lancio container Terraform Docker...")
        client = docker.from_env()

        # variabili Terraform
        tf_vars = {
            "TF_VAR_os_token": token_os,
            "TF_VAR_os_tenant_id": os_data.os_project_id,           
            "TF_VAR_bastion_ip": os_data.private_network_proxy_host, 
            "TF_VAR_flavor_name": os_data.inputs.flavor,            
            "TF_VAR_image_name": os_data.inputs.image,              
            "TF_VAR_ssh_public_key": os_data.ssh_key,               
            "TF_VAR_deployment_uuid": uuid
        }

        # Esecuzione del container
        client.containers.run(
            image="hashicorp/terraform:1.5",
            command="apply -auto-approve",
            volumes={tf_dir: {'bind': '/src', 'mode': 'rw'}},
            working_dir="/src",
            environment=tf_vars,
            remove=True,
            detach=False
        )

        # 3. Recupero IP
        logger.info(f"[{uuid}] Recupero IP della risorsa creata...")
        vm_ip = client.containers.run(
            image="hashicorp/terraform:1.5",
            command="output -raw vm_ip",
            volumes={tf_dir: {'bind': '/src', 'mode': 'ro'}},
            working_dir="/src",
            remove=True
        ).decode('utf-8').strip()
        
        # 4. Chiusura Job
        logger.info(f"[{uuid}] Orchestrazione completata. IP: {vm_ip}. Cloud-init in esecuzione sulla VM.")
        update_log_status(uuid, "SUCCESS", logs="Infrastructure deployed. Cloud-init is installing Galaxy.", ip_address=vm_ip)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{uuid}] Errore durante l'orchestrazione: {error_msg}")
        update_log_status(uuid, "FAILED", logs=error_msg)

#################################################################################################

if __name__ == "__main__":
    logger.info("Avvio Python Infra Orchestrator...")
    
    try:
        with open("deployment_info.json", "r") as f:
            raw_data = json.load(f)

        job_request = Job(**raw_data)
        run_orchestration(job_request)

    except ValidationError as ve:
        logger.error(f"Errore validazione JSON: {ve}")
    except FileNotFoundError:
        logger.error("File json non trovato.")
    except Exception as e:
        logger.error(f"Errore imprevisto nel main: {e}")
