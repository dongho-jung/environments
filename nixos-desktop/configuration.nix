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
    kernel.sysctl."kernel.sysrq" = 1;
  };

  networking.hostName = "dongho-nixos"; # Define your hostname.
  # Pick only one of the below networking options.
  networking.wireless.enable = false;  # Enables wireless support via wpa_supplicant.

  # Set your time zone.
  time.timeZone = "Asia/Seoul";


  i18n = {
    inputMethod = {
      enabled = "kime";
    };
    supportedLocales = [
      "en_US.UTF-8/UTF-8"
      "ko_KR.UTF-8/UTF-8"
    ];
  };
  fonts = {
    packages = with pkgs; [
      nanum-gothic-coding
      nerdfonts
      noto-fonts
      noto-fonts-cjk
      noto-fonts-emoji
      noto-fonts-extra
    ];
    fontconfig = {
      defaultFonts = {
        serif = ["Noto Sans Mono CJK KR"];
        sansSerif = ["Noto Sans Mono CJK KR"];
        monospace = ["Noto Sans Mono CJK KR"];
        # serif = ["NanumGothicCoding"];
        # sansSerif = ["NanumGothicCoding"];
        # monospace = ["NanumGothicCoding"];
      };
    };
  };

  # Enable the X11 windowing system.
  #  services.xserver = {
  #    enable = true;
  #    desktopManager = { xterm.enable = false; };
  #    displayManager = {
  #      defaultSession = "none+i3";
  #      sessionCommands = "${pkgs.xorg.xmodmap}/bin/xmodmap -e 'keycode 66 = Hangul' &";
  #    };
  #    windowManager.i3 = {
  #      enable = true;
  #      extraPackages = with pkgs; [
  #        dmenu
  #        i3status
  #        i3lock
  #        i3blocks
  #      ];
  #    };
  #    xkbOptions = "caps:none";
  #    videoDrivers = ["nvidia"];
  #  };

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
  
  services.pipewire.enable = true;
  services.nordvpn.enable = true;
  services.fcron = {
    enable = true;
    allow = [ "all" ];
    systab = ''
      @mail(no),nolog(true) 30s export export XDG_RUNTIME_DIR=/run/user/1000; ${unstable.swww}/bin/swww img --resize fit --transition-type random --transition-duration 1 $(find /home/dongho/images/wallpapers/ -type f | shuf -n1)
    '';
  };

  services.keyd = {
    enable = true;
    keyboards.default.settings = {
      main = {
        capslock = "hangeul";
      };
    };
  };

  services.greetd = {
    enable = true;
    settings = rec {
      initial_session = {
        command = "Hyprland";
	user = "dongho";
      };
      default_session = initial_session;
    };
  };

  # Enable sound.
  sound.enable = true;
  hardware.pulseaudio.enable = true;

  hardware = {
    opengl.enable = true;
    nvidia.modesetting.enable = true;
    nvidia.open = true;  # https://askubuntu.com/q/1420777, nouveau error spam
  };

  # Enable touchpad support (enabled default in most desktopManager).
  # services.xserver.libinput.enable = false;

  programs = {
    fish = {
      enable = true;
    };
    hyprland = {
      enable = true;
      enableNvidiaPatches = true;
      xwayland.enable = true;
    };
    autojump.enable = true;
    command-not-found.enable = true;
  };

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
    cairo
    cairomm
    cool-retro-term
    dhcpcd
    docker
    dunst
    eza
    eww
    fcron
    fd
    feh
    ffmpeg_5-full
    flameshot
    fzf
    gcc
    git
    gnome.gnome-terminal
    google-chrome 
    gtk4
    gtk4-layer-shell
    gtkmm4
    helm
    htop
    ibus
    imagemagick
    inetutils
    inotify-tools
    jetbrains.pycharm-community
    jq
    killall
    kubectl
    libnotify
    libwebp
    moreutils
    ncdu
    neofetch
    neovim
    nix-index
    peek
    pipewire
    powertop
    python3
    python311Packages.ipython
    python311Packages.jupyter-core
    ripgrep
    rofi-wayland
    scrot
    slack
    unstable.swww
    terraform
    tldr
    trash-cli
    unstable.ffmpeg
    unstable.alacritty
    virtualenv
    vscode
    waybar
    wget 
    wl-clipboard
    xdg-desktop-portal-hyprland
    xfce.tumbler
    xorg.xev
    xorg.xmodmap
    xfce.thunar

    (pkgs.waybar.overrideAttrs (oldAttrs: {
      mesonFlags = oldAttrs.mesonFlags ++ [ "-Dexperimental=true" ];
    }))
  ];
  
  environment.pathsToLink = [ "/libexec" ];
  environment.sessionVariables = {
    WLR_NO_HARDWARE_CURSORS = "1";
    NIXOS_OZONE_WL = "1";
  };

  system.copySystemConfiguration = true;

  system.stateVersion = "23.11"; # Did you read the comment?

}

