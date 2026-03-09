#!/bin/bash
set -euo pipefail
set -x

# 1. Attendiamo che il sistema sia pronto (fondamentale per AWS)
echo "Attendiamo che i lock di sistema siano rilasciati..."
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 ; do sleep 5; done

# 2. Installazione dipendenze minime
echo "Installazione dipendenze..."
apt-get update
apt-get install -y ansible git python3-pip

# 3. Preparazione ambiente Laniakea
echo "Clonazione repository..."
rm -rf /root/laniakea-nebula # Pulizia per sicurezza
git clone https://github.com/Laniakea-elixir-it/laniakea-nebula.git /root/laniakea-nebula

ANSIBLEPATH="/root/laniakea-nebula/ansible/ansible_galaxy"
ROLESPATH="$ANSIBLEPATH/roles"

mkdir -p "$ROLESPATH"

# 4. Download dei ruoli Ansible
ansible-galaxy role install -p "$ROLESPATH" -r "$ANSIBLEPATH/requirements.yml"

# 5. Esecuzione del Playbook
# Usiamo localhost perché Ansible gira "on-board" sulla VM appena creata
ansible-playbook -i "localhost," -c local "$ANSIBLEPATH/deploy-galaxy.yml" -e @"$ANSIBLEPATH/group_vars/galaxy.yml"

echo "DEPLOYMENT COMPLETATO CON SUCCESSO!"
