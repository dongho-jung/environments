# Adopt resources that already exist on this machine so `apply` reconciles them
# instead of trying to recreate. Safe to delete these blocks after the first apply.

import {
  to = host_package_pacman.networkmanager
  id = "networkmanager"
}

import {
  to = host_systemd_service.networkmanager
  id = "NetworkManager.service"
}

import {
  to = host_package_pacman.firefox
  id = "firefox"
}

import {
  to = host_package_pacman.chromium
  id = "chromium"
}

import {
  to = host_hostname.this
  id = "arch"
}

import {
  to = host_timezone.this
  id = "Asia/Seoul"
}

import {
  to = host_locale.this
  id = "en_US.UTF-8"
}
