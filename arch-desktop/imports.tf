# Adopt resources that already exist on this machine so `apply` reconciles them
# instead of trying to recreate. Safe to delete these blocks after the first apply.

import {
  to = host_user.dongho
  id = "dongho"
}

import {
  to = host_package_pacman.zsh
  id = "zsh"
}

import {
  to = host_package_pacman.wl_clipboard
  id = "wl-clipboard"
}

import {
  to = host_package_pacman.git
  id = "git"
}

import {
  to = host_package_pacman.openssh
  id = "openssh"
}

import {
  to = host_package_pacman.neovim
  id = "neovim"
}

import {
  to = host_package_pacman.terraform
  id = "terraform"
}

import {
  to = host_package_pacman.claude_code
  id = "claude-code"
}

import {
  to = host_ssh_key.github
  id = "~/.ssh/id_ed25519"
}

import {
  to = host_git_repo.environments
  id = "/home/dongho/projects/environments"
}

# --- Hyprland desktop packages (already installed on this machine) ---

import {
  to = host_package_pacman.hyprland
  id = "hyprland"
}

import {
  to = host_package_pacman.hyprlauncher
  id = "hyprlauncher"
}

import {
  to = host_package_pacman.hypridle
  id = "hypridle"
}

import {
  to = host_package_pacman.hyprlock
  id = "hyprlock"
}

import {
  to = host_package_pacman.waybar
  id = "waybar"
}

import {
  to = host_package_pacman.wofi
  id = "wofi"
}

import {
  to = host_package_pacman.mako
  id = "mako"
}

import {
  to = host_package_pacman.kitty
  id = "kitty"
}

import {
  to = host_package_pacman.pipewire
  id = "pipewire"
}

import {
  to = host_package_pacman.pipewire_pulse
  id = "pipewire-pulse"
}

import {
  to = host_package_pacman.wireplumber
  id = "wireplumber"
}

import {
  to = host_package_pacman.fcitx5
  id = "fcitx5"
}

import {
  to = host_package_pacman.fcitx5_hangul
  id = "fcitx5-hangul"
}

import {
  to = host_package_pacman.fcitx5_gtk
  id = "fcitx5-gtk"
}

import {
  to = host_package_pacman.fcitx5_qt
  id = "fcitx5-qt"
}

import {
  to = host_package_pacman.fcitx5_configtool
  id = "fcitx5-configtool"
}

import {
  to = host_package_pacman.xdg_desktop_portal_hyprland
  id = "xdg-desktop-portal-hyprland"
}

import {
  to = host_package_pacman.polkit_kde_agent
  id = "polkit-kde-agent"
}

import {
  to = host_package_pacman.qt5_wayland
  id = "qt5-wayland"
}

import {
  to = host_package_pacman.qt6_wayland
  id = "qt6-wayland"
}

import {
  to = host_package_pacman.grim
  id = "grim"
}

import {
  to = host_package_pacman.slurp
  id = "slurp"
}

import {
  to = host_package_pacman.dolphin
  id = "dolphin"
}

import {
  to = host_package_pacman.playerctl
  id = "playerctl"
}
