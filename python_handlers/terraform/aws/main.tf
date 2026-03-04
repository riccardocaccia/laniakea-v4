terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0" # Usiamo una versione stabile 5.x
    }
  }
}

provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key
  secret_key = var.aws_secret_key
}

# --- DATA SOURCES ---

# Recupero VPC di default
data "aws_vpc" "default" {
  default = true
}

# Recupero Subnet della VPC di default
data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Recupero AMI Ubuntu 22.04 più recente
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# --- RESOURCES ---

# Chiave SSH
resource "aws_key_pair" "vm_key" {
  key_name   = "key-${var.deployment_uuid}"
  public_key = var.public_ssh_key
}

# Security Group Dinamico (Porte dal JSON)
resource "aws_security_group" "galaxy_sg" {
  name        = "galaxy-sg-${var.deployment_uuid}"
  description = "Security group gestito dall'orchestratore"
  vpc_id      = data.aws_vpc.default.id

  dynamic "ingress" {
    for_each = var.open_ports
    content {
      from_port   = ingress.value.port
      to_port     = ingress.value.port
      protocol    = ingress.value.protocol
      cidr_blocks = [ingress.value.cidr]
    }
  }

  # Regola SSH standard (Opzionale, se non passata nel JSON)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # In produzione meglio limitare al tuo IP
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Istanza EC2
resource "aws_instance" "galaxy_vm" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = data.aws_subnets.default.ids[0]
  vpc_security_group_ids      = [aws_security_group.galaxy_sg.id]
  key_name                    = aws_key_pair.vm_key.key_name
  
  # LOGICA DINAMICA RETE
  associate_public_ip_address = var.network_type == "public" ? true : false

  # Cloud-init per installare Galaxy
  user_data = templatefile("${path.module}/cloudinit.sh", {
    bastion_priv_ip = "127.0.0.1" # Placeholder per compatibilità col template
  })

  tags = {
    Name = "galaxy-aws-${var.deployment_uuid}"
  }
}

# --- OUTPUT ---

output "vm_ip" {
  # Se pubblica, restituisce l'IP pubblico, altrimenti quello privato della VPC
  value = var.network_type == "public" ? aws_instance.galaxy_vm.public_ip : aws_instance.galaxy_vm.private_ip
  description = "IP dell'istanza AWS"
}
