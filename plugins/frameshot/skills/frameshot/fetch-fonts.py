#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch-fonts — 把模板要用的 7 个字体下到本地 fonts/，供 @font-face 引用。

为什么要自托管：
  · 模板原本从 fonts.googleapis.com 现拉字体，每帧多花 ~4.3 秒
  · 大陆机房该域名被墙 → 静默回退系统字体，版式跑掉且不报错
  · 7 个字体全是 SIL OFL 1.1，允许自托管与商用（随包保留 OFL.txt）

下载走 GitHub git-blobs API（api.github.com），
因为 raw.githubusercontent.com 在部分网络下不可达。
需要 gh CLI 且已登录；没有 gh 时回退到匿名 API（有速率限制）。

用法：  python3 fetch-fonts.py          下载缺失的
        python3 fetch-fonts.py --check  只检查不下载
        python3 fetch-fonts.py --force  全部重下
"""

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
FONT_DIR = BASE / "fonts"
REPO = "google/fonts"

# (google/fonts 里的目录, 仓库内文件名, 落地文件名)
# 变体字体原名带方括号，URL 里不好写，落地时改名。
FONTS = [
    ("notosanssc",    "NotoSansSC[wght].ttf",      "NotoSansSC-VF.ttf"),
    ("notoserifsc",   "NotoSerifSC[wght].ttf",     "NotoSerifSC-VF.ttf"),
    ("mashanzheng",   "MaShanZheng-Regular.ttf",   "MaShanZheng-Regular.ttf"),
    ("zcoolxiaowei",  "ZCOOLXiaoWei-Regular.ttf",  "ZCOOLXiaoWei-Regular.ttf"),
    ("zcoolkuaile",   "ZCOOLKuaiLe-Regular.ttf",   "ZCOOLKuaiLe-Regular.ttf"),
    ("liujianmaocao", "LiuJianMaoCao-Regular.ttf", "LiuJianMaoCao-Regular.ttf"),
    ("dancingscript", "DancingScript[wght].ttf",   "DancingScript-VF.ttf"),
]


def api(path):
    """优先用 gh CLI（带认证、额度高），否则匿名 HTTP。"""
    if shutil.which("gh") or (Path.home() / "bin" / "gh").exists():
        gh = shutil.which("gh") or str(Path.home() / "bin" / "gh")
        r = subprocess.run([gh, "api", path], capture_output=True, timeout=300)
        if r.returncode == 0:
            return json.loads(r.stdout)
        sys.stderr.write(r.stderr.decode("utf-8", "ignore")[:300] + "\n")
    req = urllib.request.Request("https://api.github.com/" + path,
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "frameshot-fetch-fonts"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def listing(folder):
    """取某字体目录的文件清单（名字 → sha, size）。"""
    items = api("repos/%s/contents/ofl/%s" % (REPO, folder))
    return {i["name"]: (i["sha"], i["size"]) for i in items if i["type"] == "file"}


def fetch_blob(sha):
    """git-blobs API 支持到 100MB，contents API 只到 1MB —— 字体必须走这个。"""
    d = api("repos/%s/git/blobs/%s" % (REPO, sha))
    if d.get("encoding") != "base64":
        raise RuntimeError("意外的编码: %s" % d.get("encoding"))
    return base64.b64decode(d["content"])


def main():
    ap = argparse.ArgumentParser(description="下载模板所需字体到 fonts/")
    ap.add_argument("--check", action="store_true", help="只检查缺哪些，不下载")
    ap.add_argument("--force", action="store_true", help="已存在也重新下载")
    a = ap.parse_args()

    FONT_DIR.mkdir(exist_ok=True)
    missing = [f for f in FONTS if a.force or not (FONT_DIR / f[2]).exists()]

    if a.check or not missing:
        for folder, _, local in FONTS:
            p = FONT_DIR / local
            print("%-30s %s" % (local,
                  "✅ %.1f MB" % (p.stat().st_size / 1048576) if p.exists() else "❌ 缺失"))
        if not missing:
            print("\n字体齐全。")
        elif a.check:
            print("\n缺 %d 个，跑 `python3 fetch-fonts.py` 下载。" % len(missing))
        return 0 if not missing else 1

    print("要下载 %d 个字体（共约 %.0f MB），走 api.github.com …\n" % (len(missing), 58.8))
    total = 0
    for folder, remote, local in missing:
        try:
            files = listing(folder)
            if remote not in files:
                print("⚠️  %s 在仓库里找不到 %s，跳过" % (folder, remote))
                continue
            sha, size = files[remote]
            print("  ↓ %-30s %5.1f MB …" % (local, size / 1048576), end="", flush=True)
            (FONT_DIR / local).write_bytes(fetch_blob(sha))
            total += size
            print(" ok")
            # OFL 许可必须随字体保留
            if "OFL.txt" in files and not (FONT_DIR / ("OFL-%s.txt" % folder)).exists():
                (FONT_DIR / ("OFL-%s.txt" % folder)).write_bytes(fetch_blob(files["OFL.txt"][0]))
        except Exception as e:
            print(" 失败: %s" % e)

    print("\n完成，共 %.1f MB。字体许可为 SIL OFL 1.1，OFL-*.txt 已一并保存，"
          "再分发时请保留。" % (total / 1048576))
    return 0


if __name__ == "__main__":
    sys.exit(main())
