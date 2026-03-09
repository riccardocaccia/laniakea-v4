import os
import subprocess
import shutil
import requests
import logging

logger = logging.getLogger(__name__)

class AnsibleWorker:
    def __init__(self, playbook_url, requirements_url, uuid):
        self.playbook_url = playbook_url
        self.requirements_url = requirements_url
        self.uuid = uuid
        self.base_dir = f"/tmp/{uuid}"
        self.playbook_path = os.path.join(self.base_dir, "deploy.yml")
        self.requirements_path = os.path.join(self.base_dir, "requirements.yml")

    def prepare_environment(self):
        try:
            os.makedirs(self.base_dir, exist_ok=True)
            logger.info(f"[{self.uuid}] Scaricamento file template in {self.base_dir}...")

            # Download Playbook e Requirements
#            with open(self.playbook_path, "wb") as f:
#                f.write(requests.get(self.playbook_url).content)
            with open(self.requirements_path, "wb") as f:
                f.write(requests.get(self.requirements_url).content)

            # Installazione Ruoli Ansible localmente nell'orchestratore
            roles_path = os.path.join(self.base_dir, "roles")
            subprocess.run([
                "ansible-galaxy", "install", "-r", self.requirements_path, "-p", roles_path
            ], check=True)

            return True, "OK"
        except Exception as e:
            return False, str(e)

    def execute_deployment(self, target_ip, ssh_key_path, bastion_ip=None):
        roles_path = os.path.join(self.base_dir, "roles")
        ssh_args = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

        if bastion_ip and bastion_ip != "0.0.0.0":
            ssh_args += f" -o ProxyCommand='ssh -i {ssh_key_path} -o StrictHostKeyChecking=no -W %h:%p rocky@{bastion_ip}'"
        
        cmd = (
            f"ANSIBLE_ROLES_PATH={roles_path} "
            f"ansible-playbook -i {target_ip}, -u rocky "
            f"--private-key {ssh_key_path} "
            f"--ssh-common-args \"{ssh_args}\" "
            f"{self.playbook_path}"
        )

        logger.info(f"[{self.uuid}] Esecuzione Ansible su {target_ip} (mappato come localhost)...")
        res = subprocess.run(cmd, shell=True)
        return res.returncode == 0

    def cleanup(self):
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
            logger.info(f"[{self.uuid}] Pulizia cartella temporanea completata.")
