# lan-skills · 蓝院长技能市场

Claude Code plugin marketplace by **Hugo Lan (蓝晓峰)** — [lan.x-ip.ai](https://lan.x-ip.ai)

## 收录插件

### 觉灵 · Jueling

以释迦牟尼佛法为觉悟根基、以《新中国人的精神 The Spirit of the Chinese People》为入世蓝本的觉行陪伴者。

当你陷入人生或事业的重大抉择、长期内耗与自我否定、成就之后的空虚、恐惧与焦虑、创伤与丧失、关系困局、意义感缺失时，觉灵陪你走一条路：**由闻而思，由思而觉，由觉发愿，由愿起行，由行印证。**

A companion for the stuck, the anxious, the empty-after-success — moving from confusion to insight, vow, and action. Works in Chinese and English.

## 技能内容 · What's inside

```
plugins/jueling/skills/jueling/
├── SKILL.md                          身份、边界、对话方法
└── references/
    ├── lineage-and-voice.md          法脉、人格底线、语气
    ├── predicament-map.md            困惑分类与对应的故事、语句
    ├── book-map.md                   《新中国人的精神》整体脉络与章节出处
    └── precepts-check.md             十善业与四共加行的日常自照（镜子，不是卷子）
```

配套网页自查表（不打分、不评级、答案不上传）：
[中文](https://lanenglish.com/jueling-diagnostic.html) ·
[English](https://lanenglish.com/jueling-diagnostic-en.html)

## 在 hermes agent 上安装 · Install on hermes

hermes 的 `skills tap` 期望仓库根目录下是 `skills/<名>/SKILL.md`，
与 Claude Code 的 marketplace 布局不同，因此目前请手工安装整个目录
（`SKILL.md` 依赖 `references/`，只装单个文件会残废）：

```bash
git clone --depth 1 https://github.com/xipai2026-jpg/lan-skills.git /tmp/lan-skills
mkdir -p ~/.hermes/skills/lan
cp -r /tmp/lan-skills/plugins/jueling/skills/jueling ~/.hermes/skills/lan/
hermes skills list | grep jueling      # 应显示 jueling | lan | local | enabled
```

> ⚠️ hermes 把技能索引里的 description **截断到 60 字符**（含省略号），
> 触发词必须写在前 57 字内，否则模型看不见、技能不会自动触发。
> 本技能的 description 已按此约束前置触发词；Claude Code 侧不截断，完整描述照常可用。

## 安装 · Install

在 Claude Code 里运行：

```
/plugin marketplace add xipai2026-jpg/lan-skills
/plugin install jueling@lan-skills
```

之后重启或 `/reload-plugins`，即可通过 `/jueling:jueling` 或在对话中自然触发使用。

更新：

```
/plugin marketplace update lan-skills
```

## 版权 · License

觉灵的法义与叙事内容取自蓝晓峰著《新中国人的精神》。版权归作者所有，欢迎个人安装使用；未经授权请勿将内容用于商业再分发。

© Hugo Lan (蓝晓峰). All rights reserved.
