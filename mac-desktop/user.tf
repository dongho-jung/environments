resource "host_user" "dongho" {
  name = "dongho"

  lifecycle {
    ignore_changes  = [groups]
    prevent_destroy = true
  }
}
