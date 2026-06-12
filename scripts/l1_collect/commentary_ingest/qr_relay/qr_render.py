from __future__ import annotations

from pathlib import Path


def render_qr_png(scan_url: str, output_path: Path) -> Path:
    """Render a scan URL as a QR PNG.

    Deployment should install either `qrcode[pil]` or `segno`. The function is
    deliberately pure: scan URL in, PNG path out, no wewe-rss or network calls.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if _render_with_qrcode(scan_url, output_path):
        return output_path
    if _render_with_segno(scan_url, output_path):
        return output_path
    raise RuntimeError("QR rendering requires qrcode[pil] or segno on the deployment host")


def _render_with_qrcode(scan_url: str, output_path: Path) -> bool:
    try:
        import qrcode
    except ImportError:
        return False
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(scan_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    img.save(output_path, format="PNG")
    return True


def _render_with_segno(scan_url: str, output_path: Path) -> bool:
    try:
        import segno
    except ImportError:
        return False
    qr = segno.make(scan_url, error="m")
    qr.save(output_path, kind="png", scale=8, border=4)
    return True
