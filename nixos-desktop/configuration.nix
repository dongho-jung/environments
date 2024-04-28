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
  fcitx-status-script = pkgs.fetchurl {
    url="https://raw.githubusercontent.com/lilydjwg/fcitx.vim/fcitx5-server/fcitx-status";
    sha256="1hgcyb0gsmlj8n1kz0dw0s48zsbykvm5r5k92jrxx8np2fg0gh5i";
  };
  fcitx-status-python = pkgs.python311.withPackages (ps: with ps; [ dbus-python]);
in
{
  imports =
    [
      ./hardware-configuration.nix
      nur-no-pkgs.repos.LuisChDev.modules.nordvpn
    ];
  nix.settings.experimental-features = [ "nix-command" "flakes" ];

  services.keyd = {
    enable = true;
    keyboards.default.settings = {
      main = {
        capslock = "hangeul";
      };
    };
  };

  services.xserver = {
    enable = true;
    displayManager.lightdm.enable = true;
    displayManager.autoLogin = { enable = true; user = "dongho"; };
    displayManager.defaultSession = "i3";
    displayManager.session = [{
      manage = "desktop";
      name = "i3";
      start = ''
        export GTK_IM_MODULE="fcitx"
        export QT_IM_MODULE="fcitx"
        export XMODIFIERS="@im=fcitx"
        exec i3 &>> $HOME/.logs/i3
      '';
    }];
    xkbOptions = "caps:none";
    videoDrivers = [ "nvidia" ];
  };

  boot = {
    loader.systemd-boot.enable = true;
    loader.efi.canTouchEfiVariables = true;
    kernel.sysctl."kernel.sysrq" = 1;
  };

  networking.hostName = "dongho-nixos";

  time.timeZone = "Asia/Seoul";

  i18n = {
    supportedLocales = [
      "en_US.UTF-8/UTF-8"
      "ko_KR.UTF-8/UTF-8"
      "ja_JP.UTF-8/UTF-8"
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

  services.pipewire = {
    enable = true;
    audio.enable = true;
    pulse.enable = true;
    alsa = {
      enable = true;
      support32Bit = true;
    };
  };
  services.nordvpn.enable = true;

  sound.enable = true;
  # hardware.pulseaudio.enable = true;

  hardware = {
    opengl.enable = true;
    nvidia.modesetting.enable = true;
  };

  programs = {
    autojump.enable = true;
    command-not-found.enable = true;
  };

  users.users.dongho = {
    isNormalUser = true;
    extraGroups = [ "wheel" "nordvpn" ];
    shell = pkgs.fish;
    ignoreShellProgramCheck = true;
  };

  environment.systemPackages = with pkgs; [
    dhcpcd
    fcron
    ffmpeg_5-full
    git
    gitg
    inetutils
    inotify-tools
    libnotify
    libwebp
    moreutils
    nodejs_21 # for copilot vim
    neovim
    python3
    xorg.xev
    xorg.xmodmap
  ];

  systemd.user.services.fcitx-status-server = {
    wantedBy = [ "default.target" ];
    after = [ "dbus.service" ];
    serviceConfig = {
      ExecStart = "${fcitx-status-python}/bin/python ${fcitx-status-script}";
      Restart = "always";
    };
  };

  environment.pathsToLink = [ "/libexec" ];
  environment.sessionVariables = rec {
    PATH = [
      "$HOME/projects/scripts/scripts"
    ];
  };

  system.copySystemConfiguration = true;
  system.stateVersion = "23.11";
}

