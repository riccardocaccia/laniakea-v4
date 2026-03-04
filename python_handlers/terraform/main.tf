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
  auth_url  = "https://keystone.recas.ba.infn.it/v3"
  region    = "RegionOne"
  token     = var.os_token
  tenant_id = var.os_tenant_id

  endpoint_overrides = {
    "network"  = "https://neutron.recas.ba.infn.it/v2.0/"
    "volumev3" = "https://cinder.recas.ba.infn.it/v3/"
    "image"    = "https://glance.recas.ba.infn.it/v2/"
  }
}

# --- RESOURCES ---

# SSH key definition
resource "openstack_compute_keypair_v2" "vm_key" {
  name       = "rcaccia_key_terraform"
  public_key = var.ssh_public_key
}

# Private network definition
data "openstack_networking_network_v2" "private_net" {
  name = "private_net"
}

data "openstack_networking_subnet_v2" "private_subnet" {
  name = "private_subnet"
}

# Security group allowing internal SSH from Bastion only
resource "openstack_networking_secgroup_v2" "ssh_internal" {
  name        = "ssh-internal"
  description = "[tf] Allow SSH from Bastion only"
}

# Rule: Allow SSH only from Bastion private IP (aggiunto /32 per sicurezza)
resource "openstack_networking_secgroup_rule_v2" "ssh_from_bastion" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 22
  port_range_max    = 22
  remote_ip_prefix  = "${var.bastion_ip}/32"
  security_group_id = openstack_networking_secgroup_v2.ssh_internal.id
}

# Security group for HTTP (port 80)
resource "openstack_networking_secgroup_v2" "http_access" {
  name        = "http-access"
  description = "[tf] Allow HTTP traffic on port 80"
}

# Rule: Allow ingress on port 80 (Limitata al bastione/proxy per sicurezza)
resource "openstack_networking_secgroup_rule_v2" "http_in" {
  direction         = "ingress"
  ethertype         = "IPv4"
  protocol          = "tcp"
  port_range_min    = 80
  port_range_max    = 80
  remote_ip_prefix  = "${var.bastion_ip}/32"
  security_group_id = openstack_networking_secgroup_v2.http_access.id
}

# Galaxy VM configuration
resource "openstack_compute_instance_v2" "galaxy_vm" {
  name            = "galaxy-private"
  image_name      = var.image_name
  flavor_name     = var.flavor_name
  key_pair        = openstack_compute_keypair_v2.vm_key.name
  
  security_groups = [
    "default",
    openstack_networking_secgroup_v2.ssh_internal.name,
    openstack_networking_secgroup_v2.http_access.name
  ]

  network {
    uuid = data.openstack_networking_network_v2.private_net.id
  }

  user_data = templatefile("${path.module}/cloudinit.sh", {
    bastion_priv_ip = var.bastion_ip
  })
}

# --- OUTPUTS ---

output "vm_ip" {
  value       = openstack_compute_instance_v2.galaxy_vm.access_ip_v4
  description = "The private IP of the Galaxy VM"
}
