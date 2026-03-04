terraform {
  required_version = ">= 1.4.0"
  required_providers {
    openstack = {
      source  = "terraform-provider-openstack/openstack"
      version = "~> 1.53.0"
    }
  }
}

provider "openstack" {
  auth_url                      = var.os_auth_url
  region                        = var.os_region
  tenant_id                     = var.os_tenant_id
  token                         = var.os_token
  application_credential_id     = var.os_app_cred_id
  application_credential_secret = var.os_app_cred_secret

  endpoint_overrides = {
    "network"  = "https://neutron.recas.ba.infn.it/v2.0/"
    "volumev3" = "https://cinder.recas.ba.infn.it/v3/"
    "image"    = "https://glance.recas.ba.infn.it/v2/"
  }
}

# --- DATA SOURCES ---

# Rete Privata interna (Dallo screenshot: private_net)
data "openstack_networking_network_v2" "private_net" {
  name = "private_net"
}

# Rete Pubblica esterna (Dallo screenshot: public_net)
data "openstack_networking_network_v2" "public_net" {
  name = "public_net"
}

# --- RESOURCES ---

# 1. Chiave SSH
resource "openstack_compute_keypair_v2" "vm_key" {
  name       = "rcaccia_key_${var.deployment_uuid}"
  public_key = var.ssh_public_key
}

# 2. Security Group: SSH dal Bastion (Sempre presente)
resource "openstack_networking_secgroup_v2" "ssh_internal" {
  name        = "ssh-internal-${var.deployment_uuid}"
  description = "Accesso SSH limitato all'IP del Bastion"
}

resource "openstack_networking_secgroup_rule_v2" "ssh_from_bastion" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = "${var.bastion_ip}/32"
  security_group_id = openstack_networking_secgroup_v2.ssh_internal.id
}

# 3. Security Group: Porte dinamiche passate dal JSON
resource "openstack_networking_secgroup_v2" "dynamic_sg" {
  name        = "sg-dynamic-${var.deployment_uuid}"
  description = "Porte aperte dinamicamente dall'orchestratore"
}

resource "openstack_networking_secgroup_rule_v2" "rules" {
  for_each          = { for idx, p in var.open_ports : idx => p }
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = each.value.protocol
  port_range_min    = each.value.port
  port_range_max    = each.value.port
  remote_ip_prefix  = each.value.cidr
  security_group_id = openstack_networking_secgroup_v2.dynamic_sg.id
}

# 4. Istanza Virtual Machine
resource "openstack_compute_instance_v2" "galaxy_vm" {
  name            = "galaxy-${var.deployment_uuid}"
  image_name      = var.image_name
  flavor_name     = var.flavor_name
  key_pair        = openstack_compute_keypair_v2.vm_key.name

  security_groups = [
    "default",
    openstack_networking_secgroup_v2.ssh_internal.name,
    openstack_networking_secgroup_v2.dynamic_sg.name
  ]

  network {
    uuid = data.openstack_networking_network_v2.private_net.id
  }

  user_data = templatefile("${path.module}/cloudinit.sh", {
    bastion_priv_ip = var.bastion_ip
  })
}

# --- GESTIONE FLOATING IP (CONDIZIONALE) ---

# Crea il Floating IP solo se network_type == "public"
resource "openstack_networking_floatingip_v2" "fip" {
  count = var.network_type == "public" ? 1 : 0
  pool  = data.openstack_networking_network_v2.public_net.name
}

# Associa il Floating IP all'istanza solo se creato
resource "openstack_compute_floatingip_associate_v2" "fip_assoc" {
  count       = var.network_type == "public" ? 1 : 0
  floating_ip = openstack_networking_floatingip_v2.fip[0].address
  instance_id = openstack_compute_instance_v2.galaxy_vm.id
}

# --- OUTPUT ---

output "vm_ip" {
  # Se pubblica restituisce l'IP pubblico (Floating), altrimenti l'IP privato fisso
  value = var.network_type == "public" ? (length(openstack_networking_floatingip_v2.fip) > 0 ? openstack_networking_floatingip_v2.fip[0].address : "N/A") : openstack_compute_instance_v2.galaxy_vm.access_ip_v4
  description = "IP finale della risorsa"
}
