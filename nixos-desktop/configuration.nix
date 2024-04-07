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
  
  services.nordvpn.enable = true;
  services.fcron = {
    enable = true;
    allow = [ "all" ];
    systab = ''
      @mail(no) 30s export export XDG_RUNTIME_DIR=/run/user/1000; ${unstable.swww}/bin/swww img --resize fit --transition-type random --transition-duration 1 $(find /home/dongho/images/wallpapers/ -type f | shuf -n1)
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
    dhcpcd
    docker
    dunst
    eza
    eww
    fcron
    feh
    flameshot
    fzf
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
    kubectl
    libnotify
    moreutils
    ncdu
    neofetch
    neovim
    peek
    powertop
    python311Packages.ipython
    python311Packages.jupyter-core
    rofi-wayland
    scrot
    slack
    unstable.swww
    terraform
    tldr
    trash-cli
    unstable.ffmpeg
    unstable.alacritty
    vscode
    waybar
    wget 
    wl-clipboard
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

