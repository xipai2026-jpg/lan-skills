---
name: frameshot
description: 分镜帧渲染：把旁白文字 + 配图渲成短视频的一帧帧成品图（带标题、字幕、版式、署名），再用 ffmpeg 拼成片子。当用户要做口播/知识科普/书摘/金句类短视频、要给视频批量生成带字幕的画面、要做视频封面图、问「文案怎么变成视频画面」「字幕怎么压进画面」「有没有现成的竖屏版式」时使用。自带 31 个成品版式，用 HTML/CSS 排版 + 无头 Chrome 截图，改 CSS 就能改样式，不用写 ffmpeg drawtext 滤镜，也不用 PIL 画字。纯标准库，不需要 Playwright。
---

# frameshot · 分镜帧渲染

**一句话：短视频的每一帧画面 = 一张 HTML 页面的截图。**

排版用 CSS 写（你本来就会），不用跟 `drawtext` 的转义地狱较劲，也不用 PIL 一个像素一个像素算文字位置。

## 什么时候用

- 做**口播 / 知识科普 / 书摘 / 金句 / 心理卡片**类短视频：一句旁白配一张图，图上压标题和字幕
- 已经有了文案和配图，**缺的是把它们排成画面**这一步
- 要**批量**出几十上百帧，每帧内容不同、版式统一
- 做**视频封面图**（单帧也一样用）

不适合：需要角色连续一致的剧情动画、需要镜头运动的实拍剪辑。那些是视频模型和 NLE 的活。

## 环境

- Python 3（标准库即可，**不装任何 pip 包**）
- Google Chrome 或 Chromium
- ffmpeg（只有拼片那一步需要）

### 首次使用先下字体（必做）

15/31 个版式要用中文美术字（马善政楷体、站酷快乐体、刘建毛草等）。
字体共 59MB，**不随技能分发**，第一次用先拉下来：

```bash
python3 fetch-fonts.py            # 下载缺失的（走 api.github.com）
python3 fetch-fonts.py --check    # 只看缺哪些
```

不下也能跑，但那 15 个版式会**静默回退到系统字体、版式跑掉**——工具会在 stderr 告警。
7 个字体全是 **SIL OFL 1.1**，可商用、可自托管，随包保留 `fonts/OFL-*.txt` 即可。

## 用法

技能目录下就是工具本体，`cd` 到 `skills/frameshot/` 再跑，或者用绝对路径。

```bash
python3 frameshot.py --list                                     # 列出全部 31 个版式
python3 frameshot.py -t 1080x1920/image_healing.html --params   # 看这个版式认哪些参数
```

`--params` 会告诉你三件事：**画布多大、配图该生成多大、有哪些自定义参数及其默认值**。
「配图该生成多大」很有用——你去调 AI 生图时按这个尺寸出，落进版式里才不会被裁掉主体。

渲一帧：

```bash
python3 frameshot.py -t 1080x1920/image_healing.html \
    --title "标题" \
    --text  "这一帧的旁白文字" \
    --image pic.png \
    --brand @你的署名 \
    -o frames/001.png
```

预置参数四个：`title` / `text` / `image` / `index`。
其余版式自带的参数用 `--set key=value`，可以重复写多个。

**`--brand` 是必须用的**：上游署名分散在 4 个参数上，手动 `--set` 必漏（见坑①）。
`--tagline "你的副标语"` 覆盖副标，不给就清空。

其他开关：`--transparent` 透明底、`--scale 2` 出 2 倍图、`--wait 3000` 调等待毫秒。

### 透明叠加层（推荐做法）
`--transparent` 且**不传 `--image`**，出来的是**只有文字与装饰的透明 PNG**（实测 alpha 均值 5/255，
98% 透明）。把它交给 ffmpeg 叠在背景之上，背景就能做推拉摇移（Ken Burns），
而不是一张死图——比把背景烤进帧里灵活得多。

```bash
ffmpeg -loop 1 -t 4 -i bg.png -i overlay.png -filter_complex \
  "[0:v]scale=1188:2112,zoompan=z='min(zoom+0.0008,1.1)':d=100:s=1080x1920[bg];[bg][1:v]overlay" \
  -c:v libx264 -pix_fmt yuv420p shot.mp4
```

## 批量 + 拼片

```bash
# shots.tsv：每行 "旁白<TAB>配图路径"
i=0
while IFS=$'\t' read -r narration pic; do
  i=$((i+1))
  python3 frameshot.py -t 1080x1920/image_healing.html \
    --title "$TITLE" --text "$narration" --image "$pic" \
    --set signature=@你的署名 \
    -o "frames/$(printf '%03d' $i).png"
done < shots.tsv

# 每帧停 4 秒
ffmpeg -y -framerate 1/4 -i frames/%03d.png -c:v libx264 -pix_fmt yuv420p out.mp4
```

### ⚡ 批量用 `--batch`，别用 shell 循环

单帧模式**每帧都要付一次 Chrome 冷启动（实测 2.2 秒）**。批量模式复用同一个
浏览器实例，这 2.2 秒只付一次：

```bash
python3 frameshot.py --batch jobs.jsonl
```

`jobs.jsonl` 每行一个任务，字段缺省时回落到命令行参数：

```json
{"template":"1080x1920/image_healing.html","title":"标题","text":"第一句旁白","image":"1.png","brand":"@你的署名","out":"frames/001.png"}
{"template":"1080x1920/image_healing.html","title":"标题","text":"第二句旁白","image":"2.png","brand":"@你的署名","out":"frames/002.png"}
```

实测对比（同一批 10 帧，同一台机器）：

| 方式 | 每帧耗时 |
|---|---|
| 单帧模式 + Google Fonts CDN（改造前） | **6.5s** |
| 单帧模式 + 自托管字体 | **2.9s** |
| **`--batch` 复用 Chrome** | **0.54s** |

**合计快 12 倍。** 且批量模式产出与单帧模式**逐像素相同**（实测 PSNR = inf），
不是用画质换速度。

内存也恒定——始终只有一个 tab，不像「把 N 帧堆进一个超高页面截一次再切」
那样会把 2G 小机器撑爆。

## 31 个版式

| 画布 | 数量 | 用在哪 |
|---|---|---|
| `1080x1920` | 25 | 竖屏 — 抖音 / 视频号 / 小红书 |
| `1920x1080` | 5 | 横屏 — B站 / YouTube / 官网 |
| `1080x1080` | 1 | 方屏 — 朋友圈 / 公众号 |

风格覆盖：治愈系、心理卡片、书摘、人生感悟（深/浅两版）、养生、现代、优雅、霓虹、
复古时尚、卡通、讽刺漫画、简笔线描、纯黑极简、紫色、模糊卡片、长文、电影感、
暗黑科技、超宽极简等。**跑 `--list` 看全部。**

要自己的版式：复制一个现成 HTML 改 CSS 即可，放进对应尺寸的目录。
占位符语法 `{{参数名}}` / `{{参数名=默认值}}` / `{{参数名:类型=默认值}}`，类型支持
`text` / `number` / `color` / `bool`。工具会自动把新参数认出来，`--params` 就能看到。

## ⚠️ 三个必须知道的坑

### 🔴 上游署名分散在 4 个参数上，只盖一个必漏
| 参数 | 默认值 | 覆盖版式数 |
|---|---|---|
| `author` | `@Pixelle.AI` | **17** |
| `describe` | `Open Source Omnimodal AI Creative Agent` | **13** |
| `brand` | `Pixelle-Video` | 13 |
| `signature` | `@Pixelle.AI` | 5 |

注意 `describe` 那条**不含 "Pixelle" 字样**，靠关键词搜是搜不出来的。
**一律用 `--brand 你的署名`**，它把三个署名位一次盖掉并清空副标。

Apache-2.0 **不授予商标权**（§6），所以商用前必须把这些字样清干净——
这不是版权问题，是商标问题，跟代码可不可以抄是两回事。

护栏会在 stderr 告警，**但只告警不中断，照样出图** —— 批量跑要盯 stderr。

### 🔴 有个版式的背景图是第三方外链
`static_default.html` 的 `background` 默认值指向阿里 CDN 上一张来路不明的图，
不覆盖就会把它烤进你的成片。护栏已会对**任何 http(s) 开头的默认值**告警。

（另一个 `image_cartoon.html` 原本硬编码了 jj20.com 的壁纸，本技能已替换为等效 CSS 渐变。）

### 🔴 别删 `--virtual-time-budget`
无头 Chrome 没有「等网络空闲」这个概念，`--virtual-time-budget` 是它的等价物。
去掉或调太小，**会随机出白图 / 缺图，而且不报错、退出码还是 0**。
批量跑一百帧混进去几张空的，不逐张看根本发现不了。默认 3000ms，慢的机器调大。

### 🔴 没下字体就渲，会静默跑版
版式已改成引用本地 `fonts/*.ttf`（原先是从 `fonts.googleapis.com` 现拉，
每帧多花 ~4.3 秒，且**大陆机房该域名被墙**）。

但字体不随包分发。**没跑 `fetch-fonts.py` 就渲，浏览器会静默回退到系统字体**——
出图成功、退出码 0、版式却不对。工具会在 stderr 告警，但**不中断**。

批量跑之前先 `python3 fetch-fonts.py --check` 确认一遍。

### 🔴 配图不存在时照样出图
Chrome 在 `file:` 源下读不到裸相对路径，工具的 `to_uri()` 负责转成 `file://`。
但**配图路径写错时只警告不中断**，那一帧就是没有图的空版式。
批量跑完建议核一下产出张数和文件大小分布。

## 出处与许可

版式与渲染思路移植自 **[AIDC-AI/Pixelle-Video](https://github.com/AIDC-AI/Pixelle-Video)**（Apache-2.0）
的 `pixelle_video/services/frame_html.py` 与 `templates/`。

**改动**（Apache-2.0 §4(b) 要求标明，各文件内亦有注释）：
- Playwright → 无头 Chrome；去掉 bs4 / loguru 及上游内部依赖，改为纯标准库
- 15 个版式的 Google Fonts 外链 → 本地 `@font-face`（`fetch-fonts.py` 按需下载）
- `image_cartoon.html` 硬编码的 jj20.com 外链壁纸 → 等效 CSS 渐变
- 新增：品牌署名护栏、`--brand`/`--tagline`、`cdp.py`（复用浏览器的批量模式）

本技能目录下的 `frameshot.py`、`templates/` 依 **Apache License 2.0** 分发，
许可全文见 `LICENSE-Apache-2.0`，第三方声明见 `NOTICE`。
**可商用**，再分发时保留这两个文件即可。
