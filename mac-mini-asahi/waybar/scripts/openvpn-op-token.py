#!/usr/bin/env python3

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pexpect


TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")


def load_password(key_file: str, key_var: str) -> str:
    cmd = f'source {shlex_quote(key_file)}; printf %s "${{{key_var}:-}}"'
    return subprocess.check_output(["bash", "-lc", cmd], text=True)


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def load_account_meta(config_path: Path, preferred_account: str) -> dict:
    config = json.loads(config_path.read_text())
    accounts = config.get("accounts", [])
    if not accounts:
        raise RuntimeError("No 1Password accounts found in ~/.config/op/config")

    if preferred_account:
        for account in accounts:
            if account.get("shorthand") == preferred_account:
                return account

    latest = config.get("latest_signin")
    for account in accounts:
        if account.get("shorthand") == latest:
            return account

    return accounts[0]


def account_exists(config_dir: str, shorthand: str) -> bool:
    proc = subprocess.run(
        ["op", "--config", config_dir, "account", "list", "--format=json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        return False

    try:
        accounts = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False

    return any(account.get("shorthand") == shorthand for account in accounts)


def run_signin(argv: list[str], password: str, secret_key: str | None) -> str:
    env = os.environ.copy()
    env["OP_BIOMETRIC_UNLOCK_ENABLED"] = "false"
    timeout = int(env.get("OPENVPN_OP_TIMEOUT", "30"))
    child = pexpect.spawn(argv[0], argv[1:], env=env, encoding="utf-8", timeout=timeout)
    transcript: list[str] = []
    child.logfile_read = _LogCollector(transcript)

    try:
        while True:
            idx = child.expect(
                [
                    r"Enter the Secret Key .*: ",
                    r"Secret Key .*: ",
                    r"Enter the password .*: ",
                    pexpect.EOF,
                    pexpect.TIMEOUT,
                ]
            )

            if idx in (0, 1):
                if not secret_key:
                    raise RuntimeError("Secret Key prompt received but none is available")
                child.sendline(secret_key)
            elif idx == 2:
                child.sendline(password)
            elif idx == 3:
                break
            else:
                raise RuntimeError("Timed out while waiting for 1Password CLI")
    finally:
        child.close(force=True)

    if child.exitstatus not in (0, None):
        raise RuntimeError("1Password CLI sign-in failed")

    for line in reversed("".join(transcript).splitlines()):
        candidate = line.strip()
        if TOKEN_RE.match(candidate):
            return candidate

    raise RuntimeError("1Password CLI did not return a session token")


class _LogCollector:
    def __init__(self, sink: list[str]) -> None:
        self.sink = sink

    def write(self, value: str) -> None:
        self.sink.append(value)

    def flush(self) -> None:
        return


def main() -> int:
    home = Path.home()
    config_path = Path(os.environ.get("OPENVPN_OP_SOURCE_CONFIG", str(home / ".config/op/config")))
    config_dir = os.environ.get(
        "OPENVPN_OP_MANUAL_CONFIG_DIR",
        str(home / ".local/state/waybar/op-cli-config"),
    )
    key_file = os.environ.get("OPENVPN_KEY_FILE", str(home / ".key"))
    key_var = os.environ.get("OPENVPN_KEY_OP_VAR", "OP")
    preferred_account = os.environ.get("OPENVPN_OP_ACCOUNT", "")

    os.makedirs(config_dir, exist_ok=True)
    os.chmod(config_dir, 0o700)

    password = load_password(key_file, key_var)
    if not password:
        raise RuntimeError(f"{key_var} is empty after sourcing {key_file}")

    account = load_account_meta(config_path, preferred_account)
    shorthand = account.get("shorthand") or preferred_account
    if not shorthand:
        raise RuntimeError("1Password account shorthand is unavailable")

    if account_exists(config_dir, shorthand):
        argv = ["op", "--config", config_dir, "signin", "--account", shorthand, "--raw"]
        token = run_signin(argv, password, None)
    else:
        address = account.get("server") or account.get("url")
        email = account.get("email")
        secret_key = account.get("accountKey")
        if not address or not email or not secret_key:
            raise RuntimeError("1Password account metadata is incomplete")

        argv = [
            "op",
            "--config",
            config_dir,
            "account",
            "add",
            "--address",
            address,
            "--email",
            email,
            "--shorthand",
            shorthand,
            "--signin",
            "--raw",
        ]
        token = run_signin(argv, password, secret_key)

    sys.stdout.write(token)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(1)
