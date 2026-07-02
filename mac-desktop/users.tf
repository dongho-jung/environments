data "host_group" "admin" {
  role = "admin"
}

resource "host_user" "dongho" {
  username = "dongho"

  groups = [
    data.host_group.admin.name,
  ]

  lifecycle {
    prevent_destroy = true
  }
}
