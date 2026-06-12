import sys
import types

from PIL import Image

from scripts.l1_collect.commentary_ingest.qr_relay.qr_render import render_qr_png


class FakeImage:
    def convert(self, mode):
        return self

    def save(self, output_path, format=None):
        output_path.write_bytes(b"\x89PNG\r\n\x1a\nfake-qr")


class FakeQRCode:
    received = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def add_data(self, data):
        self.received.append(data)

    def make(self, fit=True):
        self.fit = fit

    def make_image(self, fill_color=None, back_color=None):
        return FakeImage()


def test_render_qr_png_is_pure_text_to_png_wrapper(tmp_path, monkeypatch):
    fake_qrcode = types.SimpleNamespace(
        constants=types.SimpleNamespace(ERROR_CORRECT_M="M"),
        QRCode=FakeQRCode,
    )
    monkeypatch.setitem(sys.modules, "qrcode", fake_qrcode)

    out = render_qr_png("https://open.weixin.qq.com/connect/confirm?uuid=u", tmp_path / "qr.png")

    assert out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert FakeQRCode.received[-1] == "https://open.weixin.qq.com/connect/confirm?uuid=u"


def test_render_qr_png_writes_rgb_png_for_feishu_inline_preview(tmp_path):
    out = render_qr_png("https://open.weixin.qq.com/connect/confirm?uuid=u", tmp_path / "qr.png")

    with Image.open(out) as img:
        assert img.mode == "RGB"
