# environments
개발환경을 위한 개인 설정 파일들

일부 기능들은 [dongho-jung/scripts](https://github.com/dongho-jung/scripts)에 의존

## mac-desktop

새로 민 맥에서는 `bootstrap.sh` 하나면 된다.

```sh
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/dongho-jung/environments/main/bootstrap.sh)"
```

체크아웃이 이미 있으면 그냥 `./bootstrap.sh`. Command Line Tools, Homebrew,
Terraform, 클론, `terraform init`/`apply`까지 알아서 간다. 여러 번 돌려도
안전하고, 사람이 낄 자리는 맨 앞 두 군데뿐이다.

- sudo 비밀번호 한 번. 그 뒤로는 백그라운드에서 timestamp를 갱신하므로
  Homebrew도 cask 설치도 프로바이더도 다시 묻지 않는다.
- 만들어진 `~/.ssh/id_ed25519.pub`를 GitHub에 붙여넣기 한 번. 클립보드에
  복사해주고 브라우저도 열어주며, 등록될 때까지 기다렸다가 이어서 진행한다.
  private repo(`shell-history`, `vault`)와 거기로 HISTFILE을 넘기는
  `~/.zshrc`가 이 키에 걸려 있다.

`github.com` 호스트 키는 미리 박아두니 authenticity yes/no는 나오지 않는다.
앱이 깔린 뒤 macOS가 직접 띄우는 승인(Karabiner 드라이버 확장, BlackHole
오디오 드라이버, Hammerspoon·KeyCastr·Shottr·BetterTouchTool 손쉬운 사용 및
입력 모니터링, Docker Desktop 권한 도우미)은 스크립트가 대신 눌러줄 수 없다.
허용한 다음 `./bootstrap.sh`를 다시 돌리면 나머지가 수렴한다.

`--plan`은 apply 대신 plan에서 멈추고, 나머지 옵션은 `./bootstrap.sh --help`.

## arch-desktop

`dongho` 사용자로 `sudo -v && terraform apply`. 출력된 `github_ssh_key`를
GitHub에 등록하면 private repo(`shell-history`)까지 붙는다.
