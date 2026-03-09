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
    app_cred_id: Optional[str] = None
    app_cred_secret: Optional[str] = None
    sub: str
    group: str = "default"

    @model_validator(mode="after")
    def validate_auth_method(self):
        if not self.aai_token and not (self.app_cred_id and self.app_cred_secret):
            raise ValueError("Fornire aai_token oppure app credentials")
        return self

class OpenStackInputs(BaseModel):
    flavor: str
    image: str
    network_type: str = "private" ##############
    storage_size: Optional[str] = None
    open_ports: Optional[list[OpenPort]] = []
    model_config = {"extra": "ignore"}

class AWSInputs(BaseModel):
    instance_type: str
    image: str
    network_type: str = "private" ##############
    storage_size: Optional[str] = None
    open_ports: Optional[list[OpenPort]] = []
    model_config = {"extra": "ignore"}

class OpenStackProvider(BaseModel):
    os_auth_url: str
    os_project_id: str
    os_region_name: str
    ssh_key: str
    private_network_proxy_host: Optional[str] = None
    inputs: OpenStackInputs
    model_config = {"extra": "ignore"}

class AWSProvider(BaseModel):
    region: str
    ssh_key: str
    aws_access_key: str
    aws_secret_key: str
    bastion_ip: Optional[str] = None
    inputs: AWSInputs
    model_config = {"extra": "ignore"}

class CloudProviders(BaseModel):
    aws: Optional[AWSProvider] = None
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
    provider = job.selected_provider.lower()
    tf_dir = os.path.abspath(f"terraform/{provider}")

    logger.info(f"Ricevuto Job {uuid} per {provider}. Inizializzazione...")
    start_log_deployment(uuid)

    try:
        client = docker.from_env()
        tf_vars = {}

        if provider == 'openstack':
            os_data = job.cloud_providers.openstack
            current_inputs = os_data.inputs
            token_os = None

            if job.auth.aai_token:
                logger.info(f"[{uuid}] Metodo: OIDC Token. Scambio in corso...")
                token_os = get_keystone_token(job.auth.aai_token, os_data.os_auth_url, os_data.os_project_id)
                if not token_os:
                    raise Exception("Scambio token fallito: verifica aai_token o permessi Keystone")
            elif job.auth.app_cred_id:
                logger.info(f"[{uuid}] Metodo: Application Credentials. Salto lo scambio token.")

            ports_json = json.dumps([p.dict() for p in current_inputs.open_ports])

            tf_vars = {
                "TF_VAR_os_auth_url": os_data.os_auth_url,
                "TF_VAR_os_tenant_id": os_data.os_project_id,
                "TF_VAR_os_token": token_os if token_os else "",
                "TF_VAR_os_app_cred_id": job.auth.app_cred_id or "",
                "TF_VAR_os_app_cred_secret": job.auth.app_cred_secret or "",
                "TF_VAR_flavor_name": os_data.inputs.flavor,
                "TF_VAR_image_name": os_data.inputs.image,
                "TF_VAR_ssh_public_key": os_data.ssh_key,
                "TF_VAR_bastion_ip": os_data.private_network_proxy_host or "127.0.0.1",
                "TF_VAR_deployment_uuid": uuid,
                "TF_VAR_network_type": current_inputs.network_type,
                "TF_VAR_open_ports": ports_json
            }

        elif provider == 'aws':
            aws_data = job.cloud_providers.aws
            current_inputs = aws_data.inputs
            ports_json = json.dumps([p.dict() for p in current_inputs.open_ports])

            logger.info(f"[{uuid}] Configurazione variabili AWS...")
            tf_vars = {
                "TF_VAR_aws_access_key": aws_data.aws_access_key,
                "TF_VAR_aws_secret_key": aws_data.aws_secret_key,
                "TF_VAR_aws_region": aws_data.region,
                "TF_VAR_instance_type": aws_data.inputs.instance_type,
                "TF_VAR_image": aws_data.inputs.image,
                "TF_VAR_deployment_uuid": uuid,
                "TF_VAR_open_ports": ports_json,
                "TF_VAR_network_type": current_inputs.network_type,
                "TF_VAR_public_ssh_key": aws_data.ssh_key
            }

        logger.info(f"[{uuid}] Lancio container Terraform per {provider}...")
        client.containers.run(
            image="hashicorp/terraform:1.5",
            entrypoint="/bin/sh",
            command="-c 'terraform init -no-color && terraform apply -auto-approve -no-color'",
            volumes={tf_dir: {'bind': '/src', 'mode': 'rw'}},
            working_dir="/src",
            environment=tf_vars,
            remove=True    # eliminate the container once finished
        )

        vm_ip_bytes = client.containers.run(
            image="hashicorp/terraform:1.5",
            command="output -raw vm_ip",
            volumes={tf_dir: {'bind': '/src', 'mode': 'ro'}},
            working_dir="/src",
            remove=True
        )
        vm_ip = vm_ip_bytes.decode('utf-8').strip()
        
        update_log_status(uuid, "SUCCESS", logs=f"Deployed on {provider}", ip_address=vm_ip)

    except Exception as e:
        logger.error(f"Errore: {e}")
        update_log_status(uuid, "FAILED", logs=str(e))

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
