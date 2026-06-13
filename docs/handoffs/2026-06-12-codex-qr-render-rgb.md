# Codex 交接：QR 渲染改 RGB（本地代码侧，微改）

**背景**：微信读书登录二维码经 `openclaw message send --media` 发到 Feishu 时显示成**文件附件(文件名)**而非内联图片。已实测确认根因:`qr_render.py` 用 qrcode 默认 `make_image` 产出 **1-bit 灰度 PNG**(mode "1"),Feishu 图片上传 API 不接受该位深→退化成文件。把同一张图 `convert("RGB")`(8-bit RGB)后,Feishu 正常内联渲染(已在服务器端用真实推送验证)。

**修复**:`scripts/l1_collect/commentary_ingest/qr_relay/qr_render.py` 渲染后转 RGB 再存。当前(约 line 34):
```python
img = qr.make_image(fill_color="black", back_color="white")
```
改为(保留黑白外观,仅改色彩模式):
```python
img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
```
（`img.save(...)` 等其余不动；若已有变量复用,确保保存的对象是 RGB。）

**纪律(红线)**:TDD 红绿分 commit;只许改 `qr_render.py` + `tests/` 下对应测试;既有未跟踪文件不碰;不合 main 不 push;不碰 vault。

**分支**:`qr/render-rgb`(从 main 最新起)。

## 测试(红先行)

在 `tests/commentary_qr_relay/`(或既有 qr_render 测试文件)加/改:渲染一张 QR 到 tmp 路径,用 `PIL.Image.open(path).mode == "RGB"` 断言(红:现状是 "1"→失败;绿:改后通过)。保持既有 qr_render 测试(若有)不破。

## 验证

`python3 -m pytest tests/commentary_qr_relay/ -q` 全绿;`python3 -c "from PIL import Image; ..."` 确认产出 RGB。

## 回报

stdout:分支、红绿 commit、pytest 数字、改动行。无需 report 文件。
