#!/usr/bin/env python3
"""Set the local WebRobotTools administrator password."""

from __future__ import annotations

import argparse
from getpass import getpass
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.auth import write_credentials  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="设置 WebRobotTools 管理员密码")
    parser.add_argument("--username", default="admin", help="管理员用户名（默认：admin）")
    args = parser.parse_args()
    username = args.username.strip()
    if not username or len(username) > 64:
        parser.error("用户名长度必须为 1 到 64 个字符")

    password = getpass("新密码（至少 10 个字符）：")
    confirmation = getpass("再次输入新密码：")
    if password != confirmation:
        print("两次输入的密码不一致。", file=sys.stderr)
        return 1
    if len(password) < 10:
        print("密码至少需要 10 个字符。", file=sys.stderr)
        return 1

    path = PROJECT_ROOT / "backend" / "config" / "auth.local.json"
    write_credentials(path, username, password)
    print(f"管理员凭据已更新：{path}")
    print("已存在的登录会话仍然有效；重启后端可立即使旧会话失效。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
