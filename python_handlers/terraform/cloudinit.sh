#!/bin/bash
# N.B. Questo script gira come ROOT sulla VM privata
exec > >(tee /var/log/user-data.log|logger -t user-data -s 2>/dev/console) 2>&1
set -x

echo "Configurazione accesso internet via Bastione..."

export BASTION_PRIV_IP="${bastion_priv_ip}"

# Configurazione Proxy (dando per assodato che sul bastione ci sia proxy tipo TinyProxy o Squid sulla porta 8888)
export http_proxy="http://$BASTION_PRIV_IP:8888"
export https_proxy="http://$BASTION_PRIV_IP:8888"

echo "Installazione dipendenze..."
dnf install -y epel-release
dnf install -y ansible-core git python3-pip

echo "Clonazione repository Laniakea Nebula..."
git clone https://github.com/Laniakea-elixir-it/laniakea-nebula.git /root/laniakea-nebula

echo "Setup Ansible Galaxy..."
export ANSIBLEPATH="/root/laniakea-nebula/ansible/ansible_galaxy"
export ROLESPATH="$ANSIBLEPATH/roles"
mkdir -p "$ROLESPATH"

# Installazione ruoli necessari
ansible-galaxy role install -p "$ROLESPATH" -r "$ANSIBLEPATH/requirements.yml"

echo "Esecuzione Playbook Galaxy..."
ansible-playbook "$ANSIBLEPATH/deploy-galaxy.yml" -e @"$ANSIBLEPATH/group_vars/galaxy.yml"

echo "DEPLOYMENT COMPLETATO!"
