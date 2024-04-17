{ config, pkgs, unstablePkgs, ... }:
let
  fcitx-vim-server = pkgs.vimUtils.buildVimPlugin {
    name = "fcitx-vim";
    src = pkgs.fetchFromGitHub {
      owner = "lilydjwg";
      repo = "fcitx.vim";
      rev = "fcitx5-server";
      sha256 = "sha256-0FcgOuM+T3C47BqVl1/kk+tedFfkRF+tFa66uDXbJ3o=";
    };
  };
in
{
  home.username = "dongho";
  home.homeDirectory = "/home/dongho";

  home.packages = with pkgs; [
    atop
    btop
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
    viAlias = true;
    vimAlias = true;
    plugins = with pkgs.vimPlugins; [
      vim-airline
      vim-startify
      vim-nix
      copilot-vim
      fcitx-vim-server
    ];
    extraConfig = ''
      " Disable all bell sounds
      set belloff=all

      " Convert tabs to spaces
      set expandtab

      " Show line numbers
      set number

      " Indentation settings
      set shiftwidth=4
      set tabstop=4

      " Enable auto-indentation
      set autoindent

      " Enable true color support
      set termguicolors

      set mouse=
      set clipboard+=unnamedplus
    '';
  };

  programs.i3status = {
    enable = true;
    enableDefault = false;
    general = {
      interval = 1;
      colors = true;
      output_format = "i3bar";
    };
    modules = {
      "ethernet eno1" = {
        position = 1;
        settings = {
          format_up = "eth: %speed";
          format_down = "eth: down";
        };
      };
      "disk /" = {
        position = 2;
        settings = {
          format = "/ %percentage_used used";
        };
      };
      "cpu_usage" = {
        position = 3;
        settings = {
          format = "cpu: %usage";
        };
      };
      "cpu_temperature 0" = {
        position = 4;
        settings = {
          format = "temp: %degrees °C";
        };
      };
      "memory" = {
        position = 5;
        settings = {
          format = "mem: %percentage_used used";
        };
      };
      "volume master" = {
        position = 6;
        settings = {
          format = "vol: %volume";
          format_muted = "vol: %volume (muted)";
          device = "pulse";
        };
      };
      "time" = {
        position = 7;
        settings = {
          format = "%Y/%m/%d %a %H:%M:%S";
        };
      };
    };
  };

  xsession.windowManager.i3 = {
    enable = true;
    extraConfig = ''
      set $refresh_i3status killall -SIGUSR1 i3status
    '';
    config = {
      fonts = {
        names = [ "NanumGothicCoding" ];
        size = 10.0;
      };
      gaps.inner = 5;
      window.titlebar = false;
      modes = { };
      floating = {
        modifier = "Mod4";
      };
      window.commands = [
        {
          criteria = {
            class = ".*";
          };
          command = "border pixel 3";
        }
        {
          criteria = {
            class = "Picture in picture";
          };
          command = "border none";
        }
        {
          criteria = {
            class = "__text_scratchpad";
          };
          command = "floating enable";
        }
      ];
      startup = [
        {
          command = "xsetroot -solid \"#666666\"";
          always = true;
          notification = false;
        }
      ];
      bars = [
        {
          fonts = {
            names = [ "NanumGothicCoding" ];
            size = 10.0;
          };
          statusCommand = "${pkgs.i3status}/bin/i3status";
          extraConfig = ''
            wheel_up_cmd exec --no-startup-id i3status-wheel up
            wheel_down_cmd exec --no-startup-id i3status-wheel down
          '';
        }
      ];
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
          # focus
          "${mod}+space" = "focus mode_toggle";
          "${mod}+a" = "focus parent";
          "${mod}+Escape" = "focus child";

          # floating
          "${mod}+Shift+space" = "floating toggle";

          # resize
          "${mod}+Ctrl+Left" = "resize shrink width 10 px or 10 ppt";
          "${mod}+Ctrl+Down" = "resize grow height 10 px or 10 ppt";
          "${mod}+Ctrl+Up" = "resize shrink height 10 px or 10 ppt";
          "${mod}+Ctrl+Right" = "resize grow width 10 px or 10 ppt";
          "${mod}+f" = "fullscreen toggle";

          # layouts & splits
          "${mod}+t" = "layout tabbed";
          "${mod}+e" = "layout toggle split";
          "${mod}+h" = "split h";
          "${mod}+v" = "split v";

          # i3
          "${mod}+Shift+q" = "kill";
          "${mod}+Shift+r" = "restart";
          "${mod}+Shift+e" = confirm-and-do { command = "i3-msg exit"; commandAbbr = "exit"; };

          # power
          "${mod}+l" = "exec --no-startup-id i3lock -u -c 000000";
          "${mod}+Shift+s" = "exec --no-startup-id systemctl suspend";
          "${mod}+Shift+h" = confirm-and-do { command = "systemctl hibernate"; commandAbbr = "hibernate"; };

          # workspaces
          "${mod}+Tab" = "workspace next";
          "${mod}+Shift+Tab" = "workspace prev";

          # shortcuts
          "${mod}+Return" = "exec --no-startup-id alacritty --config-file=$(find ${alacritty-theme-location} -type f| shuf -n1)";
          "${mod}+d" = "exec --no-startup-id rofi -show d -no-tokenize";
          "${mod}+s" = "exec --no-startup-id scratch_pad";

          # volume
          "Control+KP_Up" = "exec --no-startup-id pactl set-sink-volume @DEFAULT_SINK@ +5% && $refresh_i3status";
          "Control+KP_Down" = "exec --no-startup-id pactl set-sink-volume @DEFAULT_SINK@ -5% && $refresh_i3status";
          "Control+KP_Begin" = "exec --no-startup-id pactl set-sink-mute @DEFAULT_SINK@ toggle && $refresh_i3status";

          # sendkey
          "Pause" = ''exec --no-startup-id "ID=`xdotool getwindowfocus`; echo $ID>/tmp/focused-window; notify-send \\"$ID[$(xdotool getwindowname $ID)] is focused\\"; paplay ${pkgs.pop-gtk-theme}/share/sounds/Pop/stereo/action/bell.oga"'';
          "--release KP_Left" = "exec --no-startup-id send_key `cat /tmp/focused-window` Left";
          "--release KP_Begin" = "exec --no-startup-id send_key `cat /tmp/focused-window` space";
          "--release KP_Right" = "exec --no-startup-id send_key `cat /tmp/focused-window` Right";
          "--release KP_Up" = "exec --no-startup-id send_key `cat /tmp/focused-window` Up";
          "--release KP_Down" = "exec --no-startup-id send_key `cat /tmp/focused-window` Down";
          "--release KP_Home" = "exec --no-startup-id send_key `cat /tmp/focused-window` Shift+P";
          "--release KP_Prior" = "exec --no-startup-id send_key `cat /tmp/focused-window` Shift+N";

          # misc
          "Print" = "exec --no-startup-id flameshot gui";

          # for yuha top-right corner
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

  programs.autojump = {
    enable = true;
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

  i18n.inputMethod = {
    enabled = "fcitx5";
    fcitx5.addons = with pkgs; [ fcitx5-mozc fcitx5-hangul ];
  };

  home.stateVersion = "23.11";
  programs.home-manager.enable = true;
}
