import os
import subprocess
import shutil
import requests
import logging

# create a logging istance (for the ansible_worker -> __name__) used for the debugging
logger = logging.getLogger(__name__)

class AnsibleWorker:
    """
    Class that describe an Ansible Worker that prepare the enviroment by downloading, in the 
    local enviroment: 
    
    - the playbooks 
    - the requirements 
    - writes the Ansible configuaration file

    And then run the real execution on the remote machine with the execute deployment function.

    Cleanup is used to have and run always the most recent version of requirements and playbook.
    """
    def __init__(self, playbook_url, requirements_url, uuid):
        self.playbook_url = playbook_url
        self.requirements_url = requirements_url
        self.uuid = uuid
        self.base_dir = f"/tmp/{uuid}"
        # Paths for deploy and playbook here
        self.playbook_path = os.path.join(self.base_dir, "deploy.yml")
        self.requirements_path = os.path.join(self.base_dir, "requirements.yml")

    def prepare_environment(self):
        """
        Sets up the local execution environment.
        1. Creates a unique temporary directory.
        2. Downloads playbooks and role requirements from remote URLs.
        3. Generates a custom ansible.cfg to tune performance and bypass interactive prompts.
        4. Installs necessary Ansible Roles via ansible-galaxy.
        """
        try:
            os.makedirs(self.base_dir, exist_ok=True)

            with open(self.playbook_path, "wb") as f:
                f.write(requests.get(self.playbook_url).content)
            with open(self.requirements_path, "wb") as f:
                f.write(requests.get(self.requirements_url).content)

            ansible_cfg = os.path.join(self.base_dir, "ansible.cfg")

            with open(ansible_cfg, "w") as f:
                f.write("[defaults]\n")
                f.write("pipelining = True\n")
                f.write(f"roles_path = {os.path.join(self.base_dir, 'roles')}\n")
                f.write("host_key_checking = False\n")
                f.write("[privilege_escalation]\n")
                f.write("become = True\n")
                f.write("become_method = sudo\n")
                f.write("become_user = root\n")
                f.write("become_ask_pass = False\n")


            roles_path = os.path.join(self.base_dir, "roles")
            # RUN the Ansible command on the cli
            subprocess.run([
                "ansible-galaxy", "install", "-r", self.requirements_path, "-p", roles_path
            ], check=True)
            return True, "OK"
            
        except Exception as e:
            return False, str(e)

    def execute_deployment(self, target_ip, ssh_key_path, bastion_ip=None):
        """
        Triggers the actual Ansible playbook execution.
        
        It constructs a complex shell command that includes:
        - SSH ProxyCommand for Bastion host traversal (if required).
        - Environment overrides for role paths and configuration.
        - Privilege escalation settings to ensure the user has root access.
        
        Args:
            target_ip (str): IP of the destination VM.
            ssh_key_path (str): Local path to the private key for authentication.
            bastion_ip (str, optional): IP of the jump host for private network access.
        """
        roles_path = os.path.join(self.base_dir, "roles")
        ssh_args = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
        # if the user specify the will of using a bastion host the proxy connection is essential
        if bastion_ip and bastion_ip != "0.0.0.0":
            ssh_args += (
                f" -o ProxyCommand='ssh -i {ssh_key_path} "
                f"-o StrictHostKeyChecking=no -W %h:%p rocky@{bastion_ip}'"
            )
        # complete command to run ansible on the target machine
        cmd = (
            f"ANSIBLE_CONFIG={os.path.join(self.base_dir, 'ansible.cfg')} "
            f"ANSIBLE_ROLES_PATH={roles_path} "
            f"ansible-playbook -i {target_ip}, -u rocky "
            f"--private-key {ssh_key_path} "
            f"--ssh-common-args \"{ssh_args}\" "
            f"-e \"ansible_remote_tmp=/tmp/.ansible-rocky "
            f"ansible_become=true "
            f"ansible_become_method=sudo "
            f"ansible_become_user=root\" "
            f"{self.playbook_path}"
            )

        logger.info(f"[{self.uuid}] Esecuzione Ansible su {target_ip}...")
        res = subprocess.run(cmd, shell=True)
        
        return res.returncode == 0

    def cleanup(self):
        """
        Checks for duplicates path for the playbook and requirements installation.
        """
        if os.path.exists(self.base_dir):
            shutil.rmtree(self.base_dir)
            logger.info(f"[{self.uuid}] Pulizia cartella temporanea completata.")
