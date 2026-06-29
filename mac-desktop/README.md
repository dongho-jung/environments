# mac-desktop

This directory uses the local development build of `registry.terraform.io/dongho-jung/host`.

Global Terraform CLI configuration in `~/.terraformrc` points Terraform at the local provider build, so normal Terraform commands work:

```shell
terraform init
terraform plan
terraform apply
```

The provider binary lives at `/Users/dongho/go/bin/terraform-provider-host`. The `terraform-local` wrapper is still available as a fallback; if that binary is missing, it builds it with local `go` or Docker.
