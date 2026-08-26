#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
frameshot — HTML 模板 → 分镜帧图（无头 Chrome 版）

移植自 Pixelle-Video (AIDC-AI, Apache-2.0) 的 pixelle_video/services/frame_html.py。
改动：用无头 Chrome 直接截图，替换原来的 Playwright；去掉 bs4/loguru 依赖，纯标准库。
上游许可与出处见 upstream/LICENSE、upstream/NOTICE。

用法：
  frameshot.py --list                                     列出所有模板
  frameshot.py -t 1080x1920/image_default.html --params   看这个模板认哪些参数
  frameshot.py -t 1080x1920/image_default.html \
      --title "标题" --text "这一帧的旁白" --image pic.png -o out.png
  额外参数用 --set key=value（可重复）
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
TPL_DIR = BASE / "templates"

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
]

# 与上游一致的占位符语法：{{name}} / {{name=默认}} / {{name:type}} / {{name:type=默认}}
PARAM_RE = re.compile(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)(?::([a-z]+))?(?:=([^}]+))?\}\}")
PRESET = {"title", "text", "image", "index"}
VALID_TYPES = {"text", "number", "color", "bool"}


def find_chrome():
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    for name in ("google-chrome", "chromium", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    sys.exit("找不到 Chrome/Chromium。装一个，或改 CHROME_CANDIDATES。")


def parse_template_size(template_path):
    """从路径里取画布尺寸，如 1080x1920/image_default.html -> (1080, 1920)"""
    for part in Path(template_path).parts:
        m = re.fullmatch(r"(\d{3,5})x(\d{3,5})", part)
        if m:
            return int(m.group(1)), int(m.group(2))
    return 1080, 1920


def parse_media_size(html):
    """读 <meta name="template:media-width|height"> —— 配图该生成多大"""
    def grab(key):
        m = re.search(
            r'<meta[^>]*name=["\']template:%s["\'][^>]*content=["\'](\d+)["\']' % key,
            html, re.I)
        if not m:
            m = re.search(
                r'<meta[^>]*content=["\'](\d+)["\'][^>]*name=["\']template:%s["\']' % key,
                html, re.I)
        return int(m.group(1)) if m else None
    w, h = grab("media-width"), grab("media-height")
    return (w, h) if w and h else (1024, 1024)


def parse_params(html):
    """列出模板里的自定义参数（不含预置的 title/text/image/index）"""
    out = {}
    for m in PARAM_RE.finditer(html):
        name, ptype, default = m.group(1), m.group(2) or "text", m.group(3)
        if name in PRESET or name in out:
            continue
        if ptype not in VALID_TYPES:
            ptype = "text"
        if default is None:
            default = {"text": "", "number": 0, "color": "#000000", "bool": False}[ptype]
        elif ptype == "number":
            try:
                default = float(default) if "." in default else int(default)
            except ValueError:
                default = 0
        elif ptype == "bool":
            default = default.lower() in {"true", "1", "yes", "on"}
        elif ptype == "color" and not str(default).startswith("#"):
            default = "#" + str(default)
        out[name] = {"type": ptype, "default": default}
    return out


def substitute(html, values):
    def rep(m):
        name, default = m.group(1), m.group(3)
        if name in values and values[name] is not None:
            v = values[name]
            if isinstance(v, bool):
                return "true" if v else "false"
            return str(v)
        return default if default else ""
    return PARAM_RE.sub(rep, html)


def to_uri(image):
    """本地路径转 file:// —— 否则 Chrome 在 file: 源下读不到"""
    if not image:
        return ""
    if image.startswith(("http://", "https://", "data:", "file://")):
        return image
    p = Path(image)
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        print("⚠️  配图不存在：%s" % p, file=sys.stderr)
        return image
    return p.as_uri()


def render(template, out_path, values, transparent=False, wait_ms=3000, scale=1):
    tpl_file = TPL_DIR / template
    if not tpl_file.exists():
        tpl_file = Path(template)
    if not tpl_file.exists():
        sys.exit("模板不存在：%s" % template)

    html = tpl_file.read_text(encoding="utf-8")

    # 护栏：模板里埋了上游品牌默认值（如 signature=@Pixelle.AI），
    # 调用方没覆盖就会把别人的水印印进成片 —— 出图前先喊一声。
    for k, v in parse_params(html).items():
        if k in values and values[k] not in (None, ""):
            continue
        d = str(v.get("default", ""))
        if "pixelle" in d.lower():
            print("⚠️  参数 %s 用了上游默认水印 %r —— 加 --set %s=你的署名"
                  % (k, d, k), file=sys.stderr)

    w, h = parse_template_size(str(tpl_file.relative_to(TPL_DIR))
                               if str(tpl_file).startswith(str(TPL_DIR)) else str(tpl_file))
    values = dict(values)
    values["image"] = to_uri(values.get("image", ""))
    final = substitute(html, values)

    out_path = Path(out_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp = tempfile.mkstemp(suffix=".html", prefix="frameshot_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(final)
        cmd = [
            find_chrome(),
            "--headless", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
            "--disable-dev-shm-usage", "--disable-extensions",
            "--force-device-scale-factor=%d" % scale,
            "--window-size=%d,%d" % (w, h),
            # 等图片/字体真正加载完 —— 等价于 Playwright 的 networkidle
            "--virtual-time-budget=%d" % wait_ms,
            "--screenshot=%s" % out_path,
        ]
        if transparent:
            cmd.append("--default-background-color=00000000")
        cmd.append(Path(tmp).as_uri())

        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if not out_path.exists() or out_path.stat().st_size == 0:
            sys.stderr.write(r.stderr.decode("utf-8", "ignore")[-2000:] + "\n")
            sys.exit("渲染失败，没有产出图片。")
        return out_path, (w, h)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser(description="HTML 模板 → 分镜帧图（无头 Chrome）")
    ap.add_argument("-t", "--template", help="模板路径，如 1080x1920/image_default.html")
    ap.add_argument("-o", "--out", default="frame.png", help="输出 PNG")
    ap.add_argument("--title", default="", help="标题")
    ap.add_argument("--text", default="", help="这一帧的旁白/字幕")
    ap.add_argument("--image", default="", help="配图（本地路径或 http URL）")
    ap.add_argument("--index", default="", help="帧序号")
    ap.add_argument("--set", action="append", default=[], metavar="K=V", help="额外参数，可重复")
    ap.add_argument("--transparent", action="store_true", help="透明底")
    ap.add_argument("--scale", type=int, default=1, help="设备像素比，2 出 2 倍图")
    ap.add_argument("--wait", type=int, default=3000, help="等待毫秒数")
    ap.add_argument("--list", action="store_true", help="列出所有模板")
    ap.add_argument("--params", action="store_true", help="列出该模板的参数")
    a = ap.parse_args()

    if a.list:
        for f in sorted(TPL_DIR.rglob("*.html")):
            rel = f.relative_to(TPL_DIR)
            w, h = parse_template_size(str(rel))
            mw, mh = parse_media_size(f.read_text(encoding="utf-8"))
            print("%-46s 画布 %dx%d  配图 %dx%d" % (rel, w, h, mw, mh))
        return

    if not a.template:
        ap.error("要么 --list，要么给 -t 模板")

    tpl = TPL_DIR / a.template
    if not tpl.exists():
        tpl = Path(a.template)
    if not tpl.exists():
        sys.exit("模板不存在：%s" % a.template)

    if a.params:
        html = tpl.read_text(encoding="utf-8")
        w, h = parse_template_size(a.template)
        mw, mh = parse_media_size(html)
        print("模板：%s" % a.template)
        print("画布：%dx%d    建议配图：%dx%d" % (w, h, mw, mh))
        print("预置参数：title / text / image / index")
        extra = parse_params(html)
        if extra:
            print("自定义参数：")
            for k, v in extra.items():
                print("  --set %-22s %-7s 默认 %r" % (k + "=…", v["type"], v["default"]))
        else:
            print("自定义参数：无")
        return

    values = {"title": a.title, "text": a.text, "image": a.image, "index": a.index}
    for kv in a.set:
        if "=" not in kv:
            sys.exit("--set 要写成 key=value：%s" % kv)
        k, v = kv.split("=", 1)
        values[k] = v

    out, size = render(a.template, a.out, values,
                       transparent=a.transparent, wait_ms=a.wait, scale=a.scale)
    print("✅ %s  (%dx%d, %.0f KB)" % (out, size[0] * a.scale, size[1] * a.scale,
                                       out.stat().st_size / 1024))


if __name__ == "__main__":
    main()
