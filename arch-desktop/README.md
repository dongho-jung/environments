# environments
개발환경을 위한 개인 설정 파일들. 기기/OS에 종속적인 부분들은 브랜치별로 분리

일부 기능들은 [0xf4d3c0d3/scripts](https://github.com/0xF4D3C0D3/scripts)에 의존

환경파일들의 동기화는 `collect.sh`를 사용. 필요하다면 스크립트 내 entries 항목을 수정

# files
```shell
environments
├── configs
│  ├── dunstrc
│  ├── flameshot
│  ├── i3
│  ├── i3status
│  └── rofi
├── dotfiles
│  ├── gitconfig
│  ├── requirements
│  ├── vimrc
│  ├── xinitrc
│  ├── zprofile
│  └── zshrc
├── etc
├── services
│  └── init-keycode.service
└── spool
   └── cron
```
