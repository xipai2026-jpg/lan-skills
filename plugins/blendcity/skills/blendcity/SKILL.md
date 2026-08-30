---
name: blendcity
description: 用无头 Blender 把真实地理数据建成 3D 体块城市并渲成图。给一个经纬度和半径，自动从 OpenStreetMap 拉建筑轮廓/楼高/路网/水系/公园，生成网格、打光、出图，全程 15-20 分钟不用手工建模。当用户要做城市鸟瞰图、街区体块模型、地产/招商/园区方案的城市底图、城市对比图，或问「怎么快速建一座城」「20分钟重建纽约那个怎么做」「OSM 数据怎么变成 3D」「Blender 怎么批量建楼」时使用。也是无头 Blender 程序化建模（bpy 脚本 + 批量渲染）的可复用骨架。纯标准库，不装 pip 包。
---

# blendcity · 20 分钟重建一座城

**一句话：AI 指挥数据管道，不是手工建模。**

真实建筑轮廓和楼高本来就躺在 OpenStreetMap 里，缺的只是「把它挤成体块、打光、出图」这一步。
两个脚本接起来就是全部：`fetch_osm.py` 拉数据 → `build_city.py` 在 Blender 里建模渲染。

已实测：成都天府广场半径 1.7km，**4229 栋建筑**含路网、锦江、公园，1080p 出图约 10 秒。

## 什么时候用

- 城市**鸟瞰/黏土风体块图**：专栏配图、汇报封面、短视频空镜
- 地产 / 招商 / 园区 / 文旅方案里的**城市区位底图**
- 同一地块**改参数反复出图**（换机位、换高度阈值、换分辨率）
- 想要一个**无头 Blender 程序化建模的骨架**去改成别的东西（园区、厂房、地形）

不适合：要照片级真实感、要单体建筑细节、要室内、要精确尺寸。
体块图就是体块图，它的价值在**快**和**真实底数**，不在精细。

## 环境

- Python 3（标准库即可，**不装任何 pip 包**）
- Blender 4.x（本配方在 **4.5.9 LTS** 上验证）
  macOS 装法：清华镜像下 dmg → `hdiutil attach` → `cp -R` 到 `/Applications`

## 用法

```bash
# 1. 拉数据（经纬度 = 想要的城市中心）
python3 fetch_osm.py --center 30.6572,104.0658 --radius 1700 --out scene.json

# 2. 建模 + 渲染
/Applications/Blender.app/Contents/MacOS/Blender --background \
    --python build_city.py -- --scene scene.json --outdir renders --name chengdu
```

出图在 `renders/chengdu_aerial.png`、`renders/chengdu_street.png`。

**换城市只改 `--center` 和 `--radius`，别的都不用动**——地面尺寸和机位是按数据范围自动算的。

### 常用参数

| 参数 | 说明 |
|---|---|
| `--radius` | 半径米。1500-2000 是甜区；超过 3000 楼太多、画面变糊 |
| `--shots` | `aerial`（斜瞰全城）/ `street`（低空街区）/ `top`（正射俯视），逗号分隔 |
| `--res` | 默认 `1920x1080`。出 4K 写 `3840x2160` |
| `--samples` | 默认 32。试机位时调到 8 更快 |
| `--tower-height` | 默认 60m，超过的楼给玻璃金属质感。想让更多楼「发光」就调低 |
| `--save-blend` | 顺便存一份 .blend，之后可以打开手动调 |
| `--no-roads` | 只要建筑，跳过路网水系（快一半） |

## ⚠️ 五个会让你白跑一趟的坑

**1. 相机 `clip_end` 默认只有 100 米。**
城市尺度不放大，整座城会被裁掉、渲出来**一张纯天空**——而且不报错。
脚本里已经按数据范围自动设成 `max(30000, R*20)`，这是这个管道最经典的翻车点。

**2. Overpass 裸 POST 会 406。**
必须把查询 urlencode 成 `data=` 提交。脚本已处理，并且**主站和 kumi 镜像互为兜底**——
两边都会间歇性抽风（实测遇到过镜像整站 500、主站正常，也遇到过反过来），
所以别只配一个端点，失败自动换下一个 + 重试三轮。

**3. 闭合环的收尾点要去掉。**
OSM 的闭合 way 会把第一个点在末尾重复一次。不去掉，建出来的楼会多一个退化面。

**4. 楼顶必须三角剖分。**
L 形、凹字形的楼，顶面直接连成一个多边形会破洞。用 `tessellate_polygon`，脚本已处理。

**5. 只取主干路。**
支路、人行道全拉进来，画面会糊成一团麻。默认只要 motorway/trunk/primary/secondary/tertiary。

## 楼高是怎么来的

优先级：`height` 标签 → `building:levels` × 3.2m → **按 OSM id 的 md5 哈希给 9-30m**。

第三档是兜底：OSM 上很多楼两个标签都没有。用哈希而不是随机数，是为了**同一栋楼每次跑都一样高**——
否则你改个机位重渲，整座城的天际线就变了，没法对比。

## 想改成别的东西

`build_city.py` 是个可复用的无头 Blender 骨架，几块可以单独拆用：

- `add_object()` —— `from_pydata` 直接喂顶点和面，**全城合并成单网格**，4000+ 栋也是秒级
  （逐栋 `bpy.ops` 建对象会慢几个数量级）
- `strip_from_line()` —— 折线按宽度偏移成条带，做路、河、管线都用它
- `build_polys()` —— 任意多边形铺成面
- 底部那套 EEVEE Next + GTAO + AgX-Punchy + 25° 仰角暖阳，是调好的**黏土风预设**，可以整段搬走

## 📋 许可：出图商用前必读

**OpenStreetMap 数据是 ODbL 1.0。** 用它渲出来的图属于 ODbL 定义的 *Produced Work*，
**可以商用，但必须署名**。图上或图注里带一句即可：

> 地理数据 © OpenStreetMap contributors (ODbL)

只要你不再分发「数据库本身」，share-alike 不会传染到你的图和文章。
但如果你把 `scene.json` 这类**加工后的数据集**公开分发，那就是 Derivative Database，要按 ODbL 开放。

本技能的两个脚本是蓝院长自有代码，不含任何第三方代码。

## 参考

- 交互式建模（在打开的 Blender 里边聊边改）是另一条路，用 MCP 不用 skill：
  [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp)（MIT）。
  它擅长基础几何、摆位、材质；有机造型和精确尺寸不行。两者不冲突：本技能是批量程序化出图，它是交互微调。
- 照片级路线：Blosm 付费版拉 Google 3D Tiles。纽约有官方免费全城 3D 模型，别的城市没有。
