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
            with open(self.playbook_path, "wb") as f:
                f.write(requests.get(self.playbook_url).content)
            with open(self.requirements_path, "wb") as f:
                f.write(requests.get(self.requirements_url).content)
            return True, "OK"
        except Exception as e:
            return False, str(e)

    def execute_deployment(self, target_ip, ssh_key_path, bastion_ip=None):
        ssh_base = (
            f"ssh -i {ssh_key_path} "
            f"-o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
        )
        scp_base = (
            f"scp -i {ssh_key_path} "
            f"-o StrictHostKeyChecking=no "
            f"-o UserKnownHostsFile=/dev/null "
        )

        if bastion_ip and bastion_ip != "0.0.0.0":
            proxy = (
                f"-o ProxyCommand='ssh -i {ssh_key_path} "
                f"-o StrictHostKeyChecking=no -W %h:%p rocky@{bastion_ip}'"
            )
            ssh_base += proxy + " "
            scp_base += proxy + " "

        remote = f"rocky@{target_ip}"

        steps = [
            f"{ssh_base} {remote} 'sudo mkdir -p /tmp/galaxy-deploy && sudo chown rocky /tmp/galaxy-deploy'",
            f"{scp_base} {self.playbook_path} {remote}:/tmp/galaxy-deploy/deploy.yml",
            f"{scp_base} {self.requirements_path} {remote}:/tmp/galaxy-deploy/requirements.yml",
            f"{ssh_base} {remote} 'sudo dnf install -y python3-pip && sudo pip3 install ansible'",
            f"{ssh_base} {remote} 'sudo /usr/local/bin/ansible-galaxy install -r /tmp/galaxy-deploy/requirements.yml -p /tmp/galaxy-deploy/roles'",
            (
                f"{ssh_base} {remote} "
                f"'sudo ANSIBLE_ROLES_PATH=/tmp/galaxy-deploy/roles "
                f"/usr/local/bin/ansible-playbook "
                f"-i localhost, -c local "
                f"/tmp/galaxy-deploy/deploy.yml "
                f"2>&1 | sudo tee /tmp/galaxy-deploy/ansible.log; "
                f"exit ${{PIPESTATUS[0]}}'"
            ),
        ]

        for i, step in enumerate(steps):
            logger.info(f"[{self.uuid}] Step {i+1}/{len(steps)}: {step[:80]}...")
            res = subprocess.run(step, shell=True)
            if res.returncode != 0:
                logger.error(f"[{self.uuid}] Step {i+1} fallito.")
                return False

        return True

    def cleanup(self):
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
            logger.info(f"[{self.uuid}] Pulizia cartella temporanea completata.")
