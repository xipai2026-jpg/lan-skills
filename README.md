# lan-skills · 蓝院长技能市场

Claude Code plugin marketplace by **Hugo Lan (蓝晓峰)** — [lan.x-ip.ai](https://lan.x-ip.ai)

## 收录插件

### 觉灵 · Jueling

以释迦牟尼佛法为觉悟根基、以《新中国人的精神 The Spirit of the Chinese People》为入世蓝本的觉行陪伴者。

当你陷入人生或事业的重大抉择、长期内耗与自我否定、成就之后的空虚、恐惧与焦虑、创伤与丧失、关系困局、意义感缺失时，觉灵陪你走一条路：**由闻而思，由思而觉，由觉发愿，由愿起行，由行印证。**

A companion for the stuck, the anxious, the empty-after-success — moving from confusion to insight, vow, and action. Works in Chinese and English.

## 安装 · Install

在 Claude Code 里运行：

```
/plugin marketplace add xipai2026-jpg/lan-skills
/plugin install jueling@lan-skills
/plugin install geo@lan-skills
/plugin install frameshot@lan-skills
```

之后重启或 `/reload-plugins`，即可通过 `/jueling:jueling`、`/geo:geo`、`/frameshot:frameshot` 或在对话中自然触发使用。

## 技能 · Skills

- **jueling（觉灵）** — 以佛法为根基、以《新中国人的精神》为蓝本的觉行陪伴者。人生抉择、内耗、成就后的空虚、恐惧焦虑、创伤丧失、关系困局与意义感缺失。中英双语。
- **geo（生成式引擎优化）** — 让品牌进入豆包/Kimi/DeepSeek 等 AI 引擎答案引用席位的实战方法论：落地六步、跨站 JSON-LD 实体锚、Bing/百度收录实操、伪服务商甄别与承诺边界。
- **frameshot（分镜帧渲染）** — 把旁白文字与配图渲成短视频的一帧帧成品图，再交给 ffmpeg 拼片。自带 31 个成品版式（竖屏 25 / 横屏 5 / 方屏 1），排版用 HTML/CSS 写。纯标准库，无需 Playwright。

更新：

```
/plugin marketplace update lan-skills
```

## 版权 · License

本仓库各插件的许可**不一致**，请分别对待：

| 插件 | 许可 | 说明 |
|---|---|---|
| `jueling` | © Hugo Lan，保留所有权利 | 法义与叙事内容取自蓝晓峰著《新中国人的精神》。欢迎个人安装使用；**未经授权请勿用于商业再分发**。 |
| `geo` | © Hugo Lan，保留所有权利 | 同上。 |
| `frameshot` | **Apache-2.0** | 版式与渲染思路移植自 [AIDC-AI/Pixelle-Video](https://github.com/AIDC-AI/Pixelle-Video)，**可商用**。许可全文见 `plugins/frameshot/skills/frameshot/LICENSE-Apache-2.0`，第三方声明见同目录 `NOTICE`；再分发时保留这两个文件即可。 |

除另有标注者外，© Hugo Lan (蓝晓峰). All rights reserved.
