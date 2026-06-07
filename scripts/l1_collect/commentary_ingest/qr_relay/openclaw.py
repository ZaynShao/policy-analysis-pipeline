from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import requests


class DiscordBotAdapter:
    """Push QR images to the OpenClaw Discord control channel.

    OpenClaw currently routes IM through Discord. `oc-ctl notify` is a reliable
    text path, but the documented live path does not prove image attachment
    support, so this adapter uses Discord's Bot API for the QR image.
    """

    def __init__(
        self,
        bot_token: str,
        *,
        api_base: str = "https://discord.com/api/v10",
        session: Any | None = None,
        timeout: int = 20,
    ) -> None:
        self.bot_token = bot_token
        self.api_base = api_base.rstrip("/")
        self.session = session if session is not None else requests.Session()
        self.timeout = timeout

    def push_qr(self, image_path: Path, caption: str, target: str) -> bool:
        image_path = Path(image_path)
        channel_id = self._resolve_channel_id(target)
        with image_path.open("rb") as fh:
            resp = self.session.post(
                f"{self.api_base}/channels/{channel_id}/messages",
                headers={"Authorization": f"Bot {self.bot_token}"},
                data={"payload_json": json.dumps({"content": caption}, ensure_ascii=False)},
                files={"files[0]": (image_path.name, fh, "image/png")},
                timeout=self.timeout,
            )
        return bool(getattr(resp, "ok", False))

    def _resolve_channel_id(self, target: str) -> str:
        if not target.startswith("user:"):
            return target
        user_id = target.removeprefix("user:")
        resp = self.session.post(
            f"{self.api_base}/users/@me/channels",
            headers={"Authorization": f"Bot {self.bot_token}"},
            data={"payload_json": json.dumps({"recipient_id": user_id}, ensure_ascii=False)},
            timeout=self.timeout,
        )
        if not getattr(resp, "ok", False):
            raise RuntimeError(f"failed to create Discord DM channel for user:{user_id}")
        channel_id = resp.json().get("id")
        if not channel_id:
            raise RuntimeError(f"Discord DM channel response missing id for user:{user_id}")
        return str(channel_id)


class OpenClawMessageAdapter:
    """Push QR images through `openclaw message send`.

    Credentials and targets stay outside git: the adapter only receives channel,
    account, and target values from env/CLI config.
    """

    def __init__(
        self,
        *,
        channel: str,
        account: str = "",
        command: str = "openclaw",
        runner: Any | None = None,
        timeout: int = 30,
    ) -> None:
        self.channel = channel
        self.account = account
        self.command = command
        self.runner = runner if runner is not None else subprocess.run
        self.timeout = timeout

    def push_qr(self, image_path: Path, caption: str, target: str) -> bool:
        args = [
            self.command,
            "message",
            "send",
            "--channel",
            self.channel,
        ]
        if self.account:
            args.extend(["--account", self.account])
        args.extend(
            [
                "--target",
                target,
                "--message",
                caption,
                "--media",
                str(Path(image_path)),
                "--json",
            ]
        )
        try:
            completed = self.runner(
                args,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0

    def push_text(self, message: str, target: str) -> bool:
        args = [
            self.command,
            "message",
            "send",
            "--channel",
            self.channel,
        ]
        if self.account:
            args.extend(["--account", self.account])
        args.extend(["--target", target, "--message", message, "--json"])
        try:
            completed = self.runner(
                args,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=self.timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0


class OpenClawNotifyFallback:
    """Text-only fallback through the existing oc-ctl notify command."""

    def __init__(self, command: str = "oc-ctl") -> None:
        self.command = command

    def notify(self, message: str) -> bool:
        try:
            completed = subprocess.run(
                [self.command, "notify", message],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=20,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0
