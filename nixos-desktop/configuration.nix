{ config, lib, pkgs, ... }:
let
  nur-no-pkgs = import
    (
      builtins.fetchTarball {
        url = "https://github.com/nix-community/NUR/archive/master.tar.gz";
        # sha256 = "12wi8gkq6cyfwb86hk4z8rn55wp83c1ql3zp1jdph9mmw7fjfl2c";
      }
    )
    { };
  unstable = import <nixos-unstable> { config = { allowUnfree = true; }; };
in
{
  imports =
    [
      ./hardware-configuration.nix
      nur-no-pkgs.repos.LuisChDev.modules.nordvpn
    ];
  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  services.xserver = {
    enable = true;
    displayManager = {
      defaultSession = "none+i3";
      sessionCommands = ''
        ${pkgs.xorg.xmodmap}/bin/xmodmap -e 'keycode 66 = Hangul' &
      '';
    };
    windowManager.i3 = {
      enable = true;
      extraPackages = with pkgs; [
        i3lock
        i3status
      ];
    };
    xkbOptions = "caps:none";
    videoDrivers = ["nvidia"];
  };

  boot = {
    loader.systemd-boot.enable = true;
    loader.efi.canTouchEfiVariables = true;
    kernel.sysctl."kernel.sysrq" = 1;
  };

  networking.hostName = "dongho-nixos";

  time.timeZone = "Asia/Seoul";

  i18n = {
    inputMethod = {
      enabled = "uim";
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
        serif = [ "Noto Sans Mono CJK KR" ];
        sansSerif = [ "Noto Sans Mono CJK KR" ];
        monospace = [ "Noto Sans Mono CJK KR" ];
      };
    };
  };

  nixpkgs.config = {
    allowUnfree = true;
  };

  nixpkgs.config.packageOverrides = pkgs: rec {
    nur = import
      (
        builtins.fetchTarball {
          url = "https://github.com/nix-community/NUR/archive/master.tar.gz";
          # sha256 = "12wi8gkq6cyfwb86hk4z8rn55wp83c1ql3zp1jdph9mmw7fjfl2c";
        })
      {
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

  sound.enable = true;
  hardware.pulseaudio.enable = true;

  hardware = {
    opengl.enable = true;
    nvidia.modesetting.enable = true;
  };

  programs = {
    fish = {
      enable = true;
    };
    autojump.enable = true;
    command-not-found.enable = true;
  };

  users.users.dongho = {
    isNormalUser = true;
    extraGroups = [ "wheel" "nordvpn" ];
    shell = pkgs.fish;
  };

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
    nixpkgs-fmt
    pamixer
    peek
    pipewire
    powertop
    python3
    python311Packages.ipython
    ripgrep
    rofi
    scrot
    terraform
    tldr
    trash-cli
    unstable.ffmpeg
    unstable.alacritty
    virtualenv
    vscode
    wget
    xclip
    xdotool
    xfce.tumbler
    xorg.xev
    xorg.xmodmap
    xfce.thunar
  ];

  environment.pathsToLink = [ "/libexec" ];
  environment.sessionVariables = rec {
    PATH = [
      "$HOME/projects/scripts/scripts"
    ];
  };

  system.copySystemConfiguration = true;
  system.stateVersion = "23.11"; 
}

