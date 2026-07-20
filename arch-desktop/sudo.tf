# Privileged host resources require sudo to be present. A fresh base system must
# still bootstrap sudo out of band before Terraform can install other packages.
resource "host_package_pacman" "sudo" {
  name = "sudo"
}
