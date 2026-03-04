variable "aws_region" {
  default = "eu-south-1"
}

variable "aws_access_key" {}
variable "aws_secret_key" {}

variable "public_ssh_key" {
  type        = string
  description = "Your SSH public key"
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "open_ports" {
  description = "List of ports to open"
  type = list(object({
    port     = number
    protocol = string
    cidr     = string
  }))
}

variable "deployment_uuid" {
  type = string
}

variable "network_type" {
  type        = string
  description = "Tipo di rete: 'public' o 'private'"
  default     = "private"
}

variable "deployment_uuid" {
  type = string
}
