from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from .resend import resend_wewe_qr as _resend_wewe_qr


mcp = FastMCP("wewe-qr-relay")


@mcp.tool(
    description=(
        "当用户提到微信/读书/RSS 的二维码/码/扫码 过期、失效、扫不上、没反应、要求重发/再发一张 时调用。"
        "会检查登录态:仍有效则告知无需重发;已失效则立即重新推送一张新二维码。"
    )
)
def resend_wewe_qr() -> str:
    db_path = os.environ["WEWE_DB_PATH"]
    result = _resend_wewe_qr(db_path)
    return str(result["message"])


if __name__ == "__main__":
    mcp.run()
