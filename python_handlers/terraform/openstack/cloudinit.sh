#!/bin/bash
set -euo pipefail
set -x

echo "Aggiornamento pacchetti..."
apt update

echo "Installazione dipendenze..."
apt install -y ansible git python3-pip

echo "Clonazione repository..."
git clone https://github.com/Laniakea-elixir-it/laniakea-nebula.git /root/laniakea-nebula

ANSIBLEPATH="/root/laniakea-nebula/ansible/ansible_galaxy"
ROLESPATH="$ANSIBLEPATH/roles"

mkdir -p "$ROLESPATH"

ansible-galaxy role install -p "$ROLESPATH" -r "$ANSIBLEPATH/requirements.yml"

ansible-playbook "$ANSIBLEPATH/deploy-galaxy.yml" -e @"$ANSIBLEPATH/group_vars/galaxy.yml"

echo "DEPLOYMENT COMPLETATO!"
