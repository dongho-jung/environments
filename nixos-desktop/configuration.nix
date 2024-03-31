# Edit this configuration file to define what should be installed on
# your system. Help is available in the configuration.nix(5) man page, on
# https://search.nixos.org/options and in the NixOS manual (`nixos-help`).

{ config, lib, pkgs, ... }:

let
  nur-no-pkgs = import (builtins.fetchTarball
    "https://github.com/nix-community/NUR/archive/master.tar.gz"
  ) {};
  unstable = import <nixos-unstable> { config = { allowUnfree = true; }; };
in {
  imports =
    [ # Include the results of the hardware scan.
      ./hardware-configuration.nix
      nur-no-pkgs.repos.LuisChDev.modules.nordvpn
    ];
  nix.settings.experimental-features = ["nix-command"];

  # Use the systemd-boot EFI boot loader.
  boot = {
    loader.systemd-boot.enable = true;
    loader.efi.canTouchEfiVariables = true;
  };

  networking.hostName = "dongho-nixos"; # Define your hostname.
  # Pick only one of the below networking options.
  networking.wireless.enable = false;  # Enables wireless support via wpa_supplicant.

  # Set your time zone.
  time.timeZone = "Asia/Seoul";


  i18n = {
    inputMethod = {
      enabled = "uim";
    };
  };
  fonts = {
    packages = with pkgs; [
      nanum-gothic-coding
      noto-fonts
      noto-fonts-cjk
      noto-fonts-emoji
      noto-fonts-extra
    ];
    fontconfig = {
      defaultFonts = {
        serif = ["NanumGothicCoding"];
        sansSerif = ["NanumGothicCoding"];
        monospace = ["NanumGothicCoding"];
      };
    };
  };

  # Enable the X11 windowing system.
  services.xserver = {
    enable = true;
    desktopManager = { xterm.enable = false; };
    displayManager = {
      defaultSession = "none+i3";
      sessionCommands = "${pkgs.xorg.xmodmap}/bin/xmodmap -e 'keycode 66 = Hangul' &";
    };
    windowManager.i3 = {
      enable = true;
      extraPackages = with pkgs; [
        dmenu
        i3status
        i3lock
        i3blocks
      ];
    };
    xkbOptions = "caps:none";
    videoDrivers = ["nvidia"];
  };

  nixpkgs.config = {
    allowUnfree = true;
  };

  nixpkgs.config.packageOverrides = pkgs: rec {
    nur = import (builtins.fetchTarball "https://github.com/nix-community/NUR/archive/master.tar.gz") {
      inherit pkgs;
    };
    nordvpn = nur.repos.LuisChDev.nordvpn;
  };

  networking.firewall = {
    checkReversePath = false;
    allowedTCPPorts = [ 443 ];
    allowedUDPPorts = [ 1194 ];
  };
  
  services.nordvpn.enable = true;

  # Enable sound.
  sound.enable = true;
  hardware.pulseaudio.enable = true;

  # Enable touchpad support (enabled default in most desktopManager).
  services.xserver.libinput.enable = false;

  # Define a user account. Don't forget to set a password with ‘passwd’.
  users.users.dongho = {
    isNormalUser = true;
    extraGroups = [ "wheel" "nordvpn" ]; # Enable ‘sudo’ for the user.
    shell = pkgs.fish;
  };

  # List packages installed in system profile. To search, run:
  # $ nix search wget
  environment.systemPackages = with pkgs; [
    atop
    awscli2
    bat
    bc
    bcc
    bpftrace
    dhcpcd
    docker
    dunst
    eza
    fcron
    feh
    flameshot
    fzf
    git
    google-chrome 
    helm
    htop
    i3
    imagemagick
    inetutils
    inotify-tools
    jetbrains.pycharm-community
    jq
    kubectl
    moreutils
    ncdu
    neofetch
    neovim
    peek
    powertop
    python311Packages.ipython
    python311Packages.jupyter-core
    rofi
    scrot
    slack
    terraform
    tldr
    trash-cli
    uim
    unstable.ffmpeg
    unstable.alacritty
    vscode
    wget 
    xclip
    xdotool
    xorg.xev
    xorg.xmodmap
    xfce.thunar
  ];
  
  environment.pathsToLink = [ "/libexec" ];

  programs = {
    fish = {
      enable = true;
    };
    command-not-found.enable = true;
  };

  # Copy the NixOS configuration file and link it from the resulting system
  # (/run/current-system/configuration.nix). This is useful in case you
  # accidentally delete configuration.nix.
  system.copySystemConfiguration = true;

  # This option defines the first version of NixOS you have installed on this particular machine,
  # and is used to maintain compatibility with application data (e.g. databases) created on older NixOS versions.
  #
  # Most users should NEVER change this value after the initial install, for any reason,
  # even if you've upgraded your system to a new NixOS release.
  #
  # This value does NOT affect the Nixpkgs version your packages and OS are pulled from,
  # so changing it will NOT upgrade your system.
  #
  # This value being lower than the current NixOS release does NOT mean your system is
  # out of date, out of support, or vulnerable.
  #
  # Do NOT change this value unless you have manually inspected all the changes it would make to your configuration,
  # and migrated your data accordingly.
  #
  # For more information, see `man configuration.nix` or https://nixos.org/manual/nixos/stable/options#opt-system.stateVersion .
  system.stateVersion = "23.11"; # Did you read the comment?

}

