<div align="center">

# stdraw

**Planarity-aware 系统思维图引擎。节点排布优先、诚实分级、五指标质量证书。**

*Text DSL in → diagram with a quality certificate out. Honest grades, never fake "zero crossings" claims.*

</div>

[![CI](https://github.com/jacky510/stdraw/actions/workflows/ci.yml/badge.svg)](https://github.com/jacky510/stdraw/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.1.0-blue.svg)](pyproject.toml)
[![Stars](https://img.shields.io/github/stars/jacky510/stdraw.svg?style=flat)](https://github.com/jacky510/stdraw/stargazers)

[Install](#install) · [Gallery](#gallery) · [Quickstart](#get-started--quickstart) · [DSL](#dsl%E4%B8%80%E5%88%86%E9%92%9F) · [Certificates](#certificates--%E8%B4%A8%E9%87%8F%E8%AF%81%E4%B9%A6) · [Agent Integration](#agent-integration)

```bash
pip install stdraw
```

---

## What & Why

主流图工具全停在「交叉最小化」启发式，并且**没有一个敢对自己的输出做承诺**。stdraw 反过来：

- **Planarity-Aware 2D**：平面嵌入 + st 编号 + 可见性表示，可平面图的线全竖直、**0 交叉有定理保证**（不是调参调出来的）；
- **排布优先**：节点排布（复杂图均匀、简单图对称规律）是第一目标函数，线交叉第二；
- **诚实分级**：拿不到证书就如实说拿不到——**绝不宣称任意图 0 交叉**（CLD 环多常不可平面，0 交叉有数学边界）；
- **五指标质量证书**：每一次交付都带量化证书（交叉 / 净距 / 对齐 / CV / 穿卡），验证跑在交付坐标上；
- **确定性**：同输入同输出，逐字节一致，图进版本库 diff 干净。

## Gallery

全部为仓内 demos 的真实渲染截图（点击跳转对应 demo）。

| | |
|---|---|
| <a href="../demos/classic-cld-2d.html"><img src="docs/gallery/classic-cld-2d.png" alt="classic CLD 2D zero-crossing layout" width="420"/></a> | <a href="../demos/classic-cld-3d.html"><img src="docs/gallery/classic-cld-3d.png" alt="classic CLD 3D sphere layout" width="420"/></a> |
| **2D · 定理级零交叉**（增长极限×转嫁负担，8n/13e） | **3D · 球面排布**（任意角度旋转，投影交叉由相机解决） |
| <a href="../demos/classic-cld-2d.html"><img src="docs/gallery/certificate.png" alt="quality certificate panel" width="420"/></a> | |
| **质量证书面板**（页面内实时复算，五指标 + 门禁 + 分级） | |

## Ask your agent in plain words

stdraw 是 agent 原生工具：一份 `.cld` 文本进，带证书的图出。你可以直接对 agent 说：

| 你说 | agent 跑 |
|---|---|
| 「帮我把这张因果回路图画出来，要带质量证书」 | `stdraw layout model.cld --outdir out` |
| 「审计这个文件里声明的反馈环：有没有不闭合的、极性标错的？」 | 看 `out/loops_audit.json` 的 `problems`（独立枚举全图回路对照） |
| 「这张图能零交叉吗？拿不到就直说，别吹」 | 看 `out/certificate.json` 的 `grade`（诚实分级，见下） |
| 「给一张能打印的版本」 | 打开 `out/demo-2d.html`（内联 SVG，零联网） |

## Project Structure

```text
stdraw/
├── stdraw/              # Python 包
│   ├── planar.py        #   2D 平面布局（0 交叉定理保证）
│   ├── layout3d.py      #   3D 五形体排布（球面/立方体/四面体/圆锥）
│   ├── metrics.py       #   五指标质量证书 + 诚实分级
│   ├── check.py         #   11 项几何自检（CI 门禁形态）
│   ├── loops.py         #   环路语义审计（lint）
│   ├── dsl.py           #   .cld DSL 解析器
│   ├── model.py         #   图数据模型
│   ├── render.py        #   2D HTML 渲染（内联 SVG）
│   ├── render3d.py      #   3D HTML 渲染（three.js）
│   └── __main__.py      #   CLI：stdraw layout ...
├── examples/            # .cld 案例（增长极限 / 增长极限×转嫁负担）
├── demos/               # 交付形态：2D/3D demo + 证书 JSON
├── viewer/              # 零依赖交互查看器（四形态 + 页面内实时证书）
├── skills/stdraw/       # Agent Skill（skills add 即装）
├── docs/                # DSL 规范 + gallery
└── .github/workflows/   # CI：11 项自检 + 两案例证书断言 + 确定性
```

## Get Started / Quickstart

```bash
# 1. 安装（纯 pip，唯一依赖 networkx）
pip install stdraw

# 2. 跑一个案例：文本 DSL 进
stdraw layout examples/limits-to-growth.cld --outdir out --pitch 62

# 3. 看交付形态
#    out/demo-2d.html  — 2D 零交叉布局 + 内嵌质量证书
#    out/demo-3d.html  — 3D 球面/立方体/四面体/圆锥排布（需同仓 assets/）
#    out/certificate.json — 五指标 + 诚实分级
#    out/loops_audit.json — 环路语义审计
```

仓库内已有跑好的交付形态：直接打开 [`demos/classic-cld-2d.html`](demos/classic-cld-2d.html) / [`demos/classic-cld-3d.html`](demos/classic-cld-3d.html)。
交互查看器（四形态 + 节点拖拽 + 环路面板）：浏览器打开 `viewer/index.html`，无需安装任何东西。

## DSL 一分钟

行导向文本，`#` 起注释：

```ld
graph "增长极限×转嫁负担"
var rate "采纳率"
rate -> + adopters @loops R1,B1,B2      # 极性边 + 回路标签
loop R1 "采纳扩散" "R" [rate, adopters, word]
```

最小闭环 = 变量 / 极性边 / 回路标签 / 分组（可选，布局层不消费分组——布局由关系唯一决定）。
回路标签不是注释——lint 层验证闭合性与 R/B 极性奇偶，独立枚举全图回路对照（抓过「声明环不闭合」「极性标错」）。
规范全文：[docs/dsl-spec-v0.1.md](docs/dsl-spec-v0.1.md)。

## Certificates · 质量证书

每个交付目录里的 `certificate.json`：

```json
{
  "metrics": { "crossings": 0, "min_card_gap": 20.0, "row_align_rate": 0.625,
               "spacing_cv": 0.179, "avg_edge_length": 109.7 },
  "gates":   { "crossings_zero": true, "min_gap_ge_16": true,
               "row_align_ge_060": true, "cv_le_035": true },
  "grade": "最优"
}
```

诚实分级语义（分级铁律：**绝不冒充成品**）：

| 级别 | 定义 |
|---|---|
| **最优** | 排布要求满足 + 线 0 交叉（可平面图走构造式布局，定理保证） |
| **其次** | 排布要求满足 + 交叉 ≤2 处（坐标入证书供人复核；互斥时保排布、放交叉） |
| **最次** | 升维 3D：任意角度旋转，空间无交叉，投影交叉由相机解决 |
| **未获证书** | 其余情况——如实不评级 |

另有 `geometry_report.json`（11 项几何自检，CI 门禁形态，fail>0 时 CLI exit 1）可直接当回归门禁用。

## Agent Integration

| Agent host | 接入方式 |
|---|---|
| 任意能读文件的 agent | 读 [AGENTS.md](AGENTS.md)（仓根，agent 使用说明书） |
| Agent Skills 生态 | `npx skills add jacky510/stdraw` → 安装 [skills/stdraw/SKILL.md](skills/stdraw/SKILL.md) |
| 脚本 / CI 门禁 | `pip install stdraw` → `stdraw layout ...` → 断言 `certificate.json` / `geometry_report.json` |
| MCP server | 规划中（见 AGENTS.md 预留位） |

## Limitations（诚实边界）

- **绝不宣称任意图 0 交叉**：环多的 CLD 常不可平面，0 交叉有数学边界；不可平面输入抛 `NotPlanarError` 诚实降级，不硬画。
- 2D 层的「无关线遮挡式穿卡」为设计允许（卡片不透明），证书里如实计数。
- 3D 层不做 2D 交叉承诺——空间弦线不相交由维度冗余保证，投影交叉由相机解决。
- 布局层是可替换实现（当前：平面嵌入 + 车道装箱），最小交叉求解等在路线图上。

## License

[MIT](LICENSE) © stdraw contributors
