terraform {
  required_providers {
    host = {
      source = "dongho-jung/host"
    }
  }
}

module "directories" {
  source = "./directories"
}

module "packages" {
  source = "./packages"

  shell_history_path_resolved = module.directories.shell_history_path_resolved
}

module "mac" {
  source = "./mac"
}
