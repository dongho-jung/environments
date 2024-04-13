{ config, pkgs, unstablePkgs, ... }:
{
  home.username = "dongho";
  home.homeDirectory = "/home/dongho";

  home.packages = with pkgs; [
    atop
    awscli2
    bat
    bc
    bcc
    bpftrace
    docker
    dunst
    eza
    fd
    feh
    flameshot
    fzf
    i3lock
    gcc
    git
    gnome.gnome-terminal
    google-chrome
    helm
    htop
    jetbrains.pycharm-community
    jq
    killall
    kubectl
    ncdu
    neofetch
    nix-index
    nixpkgs-fmt
    pamixer
    peek
    python311Packages.ipython
    ripgrep
    rofi
    scrot
    terraform
    tldr
    trash-cli
    vscode
    wget
    xclip
    xdotool
    xidlehook
    xfce.tumbler
    xfce.thunar
  ];

  programs.git = {
    enable = true;
    userName = "Dongho Jung";
    userEmail = "dongho971220@gmail.com";
  };

  programs.starship = {
    enable = true;
  };

  programs.alacritty = {
    enable = true;
    package = unstablePkgs.alacritty;
  };

  programs.fish = {
    enable = true;
    interactiveShellInit = ''
      set fish_greeting ""
    '';
    functions = {
      tmp = ''
        set TMP ~/tmp/(date +%Y)/(date +%m)/(date +%d)
        mkdir -p $TMP
        cd $TMP
      '';
    };
    shellAliases = rec {
      vi = "nvim";
      cat = "bat";
      ls = "eza";
      l = "${ls} -lh";
      ll = "${ls} -alh";
      ga = "git add";
      gc = "git commit -v";
      gl = "git pull";
      gp = "git push";
      gg = "git gui";
      gst = "git status";
      gd = "git diff";
      gds = "git diff --staged";
      gco = "git checkout";
      tf = "terraform";
      tfp = "${tf} plan";
      tfa = "${tf} apply";
      tfi = "${tf} init";
      y = "xclip -selection clipboard";
      yi = "${y} -t image/png -i";
      p = "xclip -selection clipboard -o";
      open = "xdg-open";
      np = "nix-shell -p";
    };
  };

  programs.neovim = {
    enable = true;
    defaultEditor = true;
  };

  programs.i3status = {
    enable = true;
  };

  xsession.windowManager.i3 = {
    enable = true;
    config = {
      fonts = {
        names = [ "NanumGothicCoding" ];
        size = 10.0;
      };
      gaps.inner = 5;
      modes = { };

      keybindings =
        let
          mod = "Mod4";
          alacritty-theme-location = "/home/dongho/projects/alacritty-theme/computed-themes";
          confirm-and-do = { command, commandAbbr ? command }:
            "exec --no-startup-id \"i3-nagbar -t warning -m 'You pressed ${commandAbbr} shorcut. Do you really want it?' -B 'Yes, ${commandAbbr}' '${command}'\"";
          bind-generator = bindPrefix: commandPrefix: list: builtins.listToAttrs (
            builtins.map
              (i: {
                name = "${bindPrefix}+${toString i}";
                value = "${commandPrefix} ${toString i}";
              })
              list);
        in
        {
          "${mod}+space" = "focus mode_toggle";
          "${mod}+a" = "focus parent";
          "${mod}+Escape" = "focus child";

          "${mod}+Shift+space" = "floating toggle";

          "${mod}+Ctrl+Left" = "resize shrink width 10 px or 10 ppt";
          "${mod}+Ctrl+Down" = "resize grow height 10 px or 10 ppt";
          "${mod}+Ctrl+Up" = "resize shrink height 10 px or 10 ppt";
          "${mod}+Ctrl+Right" = "resize grow width 10 px or 10 ppt";
          "${mod}+f" = "fullscreen toggle";

          "${mod}+t" = "layout tabbed";
          "${mod}+e" = "layout toggle split";

          "${mod}+Shift+q" = "kill";
          "${mod}+Shift+r" = "reload";
          "${mod}+Shift+e" = confirm-and-do { command = "i3-msg exit"; commandAbbr = "exit"; };
          "${mod}+l" = "exec --no-startup-id i3lock -u -c 000000";

          "${mod}+Shift+s" = confirm-and-do { command = "systemctl suspend"; commandAbbr = "suspend"; };
          "${mod}+Shift+h" = confirm-and-do { command = "systemctl hibernate"; commandAbbr = "hibernate"; };

          "${mod}+Return" = "exec --no-startup-id alacritty --config-file=$(find ${alacritty-theme-location} -type f| shuf -n1)";
          "${mod}+d" = "exec --no-startup-id rofi -show d -no-tokenize";

          "--release Shift+KP_Left" = "exec --no-startup-id xdotool mousemove 1130 280 click 1 sleep 0.01 mousemove restore";
          "--release Shift+KP_Begin" = "exec --no-startup-id xdotool mousemove 1460 280 click 1 sleep 0.01 mousemove restore";
          "--release Shift+KP_Right" = "exec --no-startup-id xdotool mousemove 1790 280 click 1 sleep 0.01 mousemove restore";
        } //
        bind-generator "${mod}" "workspace number" (pkgs.lib.lists.range 1 9) //
        bind-generator "${mod}+Shift" "move container to workspace number" (pkgs.lib.lists.range 1 9) //
        bind-generator "${mod}" "focus" [ "Left" "Down" "Up" "Right" ] //
        bind-generator "${mod}+Shift" "move container" [ "Left" "Down" "Up" "Right" ];
    };
  };

  services.xidlehook = {
    enable = true;
    not-when-audio = true;
    timers = [
      {
        command = "i3lock -u -c 000000";
        delay = 600;
      }
      {
        command = "systemctl suspend";
        delay = 7200;
      }
    ];
  };

  home.stateVersion = "23.11";
  programs.home-manager.enable = true;
}
