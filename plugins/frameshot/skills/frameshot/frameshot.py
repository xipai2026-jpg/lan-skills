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

# 上游（Pixelle-Video）埋在模板默认值里的品牌字样。命中即告警。
# 注意 describe 那条不含 "pixelle"，只匹配 pixelle 会漏掉 13 个模板。
UPSTREAM_BRAND_WORDS = ("pixelle", "omnimodal ai creative agent")
# --brand 一次性覆盖的署名类参数（分散在 4 个参数名上）
BRAND_PARAMS = ("author", "signature", "brand")
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


def inject_base(html, tpl_dir):
    """
    临时 HTML 落在 /tmp，模板里的相对路径（../../fonts/*.ttf）会指错地方。
    注入 <base> 让相对路径按模板原位置解析。
    """
    base = '<base href="%s/">' % tpl_dir.as_uri().rstrip("/")
    m = re.search(r"<head[^>]*>", html, re.I)
    if m:
        return html[:m.end()] + "\n    " + base + html[m.end():]
    return base + html


def warn_missing_fonts(html, tpl_dir):
    """模板要的本地字体没下载 → 浏览器会静默回退，版式跑掉还不报错。先喊一声。"""
    missing = []
    for src in re.findall(r"url\(['\"]?([^)'\"]+\.ttf)['\"]?\)", html):
        if not (tpl_dir / src).exists():
            missing.append(Path(src).name)
    if missing:
        print("⚠️  缺字体 %s —— 会静默回退到系统字体、版式跑掉。"
              "跑 `python3 fetch-fonts.py` 下载" % ", ".join(sorted(set(missing))),
              file=sys.stderr)


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


def resolve_template(template):
    tpl_file = TPL_DIR / template
    if not tpl_file.exists():
        tpl_file = Path(template)
    if not tpl_file.exists():
        raise SystemExit("模板不存在：%s" % template)
    return tpl_file


def check_upstream_defaults(html, values):
    """模板里埋了上游品牌默认值或外链素材，调用方没覆盖就会烤进成片。先喊一声。"""
    for k, v in parse_params(html).items():
        # 键存在就算显式覆盖 —— 把 describe 主动置空也是一种覆盖，不该再告警
        if k in values:
            continue
        d = str(v.get("default", ""))
        if any(w in d.lower() for w in UPSTREAM_BRAND_WORDS):
            print("⚠️  参数 %s 仍是上游品牌默认值 %r —— 用 --brand 或 --set %s=…"
                  % (k, d, k), file=sys.stderr)
        elif d.startswith(("http://", "https://")):
            print("⚠️  参数 %s 默认值是外链素材 %s —— 版权不明，"
                  "商用前务必 --set %s=你自己的图" % (k, d[:60], k), file=sys.stderr)


def prepare(tpl_file, values):
    """替换占位符、注入 <base>、算出画布尺寸。单帧与批量共用。"""
    html = tpl_file.read_text(encoding="utf-8")
    # parse_template_size 按路径分段找 WxH，直接给全路径即可。
    # （早先用字符串前缀判断是否在 TPL_DIR 内，会被 templates.bak 这类同前缀目录坑到）
    w, h = parse_template_size(str(tpl_file))
    values = dict(values)
    values["image"] = to_uri(values.get("image", ""))
    warn_missing_fonts(html, tpl_file.parent)
    check_upstream_defaults(html, values)
    return inject_base(substitute(html, values), tpl_file.parent), w, h


def render(template, out_path, values, transparent=False, wait_ms=3000, scale=1):
    """单帧：起一个 Chrome 出一张图。冷启动约 2.2 秒，批量请用 render_batch。"""
    tpl_file = resolve_template(template)
    final, w, h = prepare(tpl_file, values)

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


def render_batch(jobs, settle_ms=250, on_done=None):
    """
    批量：复用同一个 Chrome 实例。

    单帧模式每帧都要付 ~2.2 秒的 Chrome 冷启动，批量只付一次。
    内存恒定（始终一个 tab），不会像「把 N 帧堆进一个超高页面」那样撑爆小内存机器。

    jobs: [{template, out, values, transparent?, scale?}, ...]
    """
    from cdp import Chrome

    tmp_files = []
    results = []
    try:
        with Chrome(find_chrome()) as chrome:
            for i, job in enumerate(jobs, 1):
                tpl_file = resolve_template(job["template"])
                final, w, h = prepare(tpl_file, job.get("values", {}))

                fd, tmp = tempfile.mkstemp(suffix=".html", prefix="frameshot_")
                tmp_files.append(tmp)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(final)

                png = chrome.shoot(Path(tmp).as_uri(), w, h,
                                   scale=job.get("scale", 1),
                                   settle_ms=settle_ms,
                                   transparent=job.get("transparent", False))
                out = Path(job["out"]).resolve()
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(png)
                results.append(out)
                if on_done:
                    on_done(i, len(jobs), out, (w, h))
    finally:
        for t in tmp_files:
            if os.path.exists(t):
                os.unlink(t)
    return results


def main():
    ap = argparse.ArgumentParser(description="HTML 模板 → 分镜帧图（无头 Chrome）")
    ap.add_argument("-t", "--template", help="模板路径，如 1080x1920/image_default.html")
    ap.add_argument("-o", "--out", default="frame.png", help="输出 PNG")
    ap.add_argument("--title", default="", help="标题")
    ap.add_argument("--text", default="", help="这一帧的旁白/字幕")
    ap.add_argument("--image", default="", help="配图（本地路径或 http URL）")
    ap.add_argument("--index", default="", help="帧序号")
    ap.add_argument("--brand", help="一次性把 author/signature/brand 全设成你的署名")
    ap.add_argument("--tagline", default=None, help="副标语，覆盖 describe（默认清空）")
    ap.add_argument("--set", action="append", default=[], metavar="K=V", help="额外参数，可重复")
    ap.add_argument("--transparent", action="store_true", help="透明底")
    ap.add_argument("--scale", type=int, default=1, help="设备像素比，2 出 2 倍图")
    ap.add_argument("--wait", type=int, default=3000, help="等待毫秒数")
    ap.add_argument("--batch", metavar="JOBS.jsonl",
                    help="批量模式：复用一个 Chrome 跑完整批，每帧省 ~2.2s 冷启动")
    ap.add_argument("--settle", type=int, default=250,
                    help="批量模式下 load 事件后的排版落定余量(ms)，默认 250")
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

    if a.batch:
        import json, time
        jobs = []
        for ln, line in enumerate(Path(a.batch).read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                j = json.loads(line)
            except ValueError as e:
                sys.exit("第 %d 行不是合法 JSON：%s" % (ln, e))
            tpl = j.get("template") or a.template
            if not tpl:
                sys.exit("第 %d 行没有 template，命令行也没给 -t" % ln)
            vals = {"title": j.get("title", a.title), "text": j.get("text", a.text),
                    "image": j.get("image", a.image), "index": j.get("index", a.index)}
            brand = j.get("brand", a.brand)
            if brand:
                for k in BRAND_PARAMS:
                    vals[k] = brand
                vals["describe"] = j.get("tagline", a.tagline) or ""
            vals.update(j.get("set", {}))
            jobs.append({"template": tpl, "out": j["out"], "values": vals,
                         "transparent": j.get("transparent", a.transparent),
                         "scale": j.get("scale", a.scale)})
        if not jobs:
            sys.exit("%s 里没有任务" % a.batch)

        t0 = time.time()
        def progress(i, n, out, size):
            print("  [%d/%d] %s (%dx%d)" % (i, n, out.name, size[0], size[1]))
        render_batch(jobs, settle_ms=a.settle, on_done=progress)
        dt = time.time() - t0
        print("✅ %d 帧，共 %.1fs，平均 %.2fs/帧（复用同一个 Chrome）"
              % (len(jobs), dt, dt / len(jobs)))
        return

    if not a.template:
        ap.error("要么 --list，要么 --batch，要么给 -t 模板")

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
    if a.brand:
        for k in BRAND_PARAMS:
            values[k] = a.brand
        values["describe"] = a.tagline if a.tagline is not None else ""
    elif a.tagline is not None:
        values["describe"] = a.tagline
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
