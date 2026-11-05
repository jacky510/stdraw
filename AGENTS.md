# AGENTS.md — 给 agent 的 stdraw 使用说明

stdraw 是 planarity-aware 的系统思维图（CLD / 因果回路图）引擎：
**文本 DSL 进，带质量证书的图出**。它专为 agent 设计——零交互、确定性输出、
每个交付物都是机器可读的 JSON + 可直接打开的 HTML。

给 agent host 的最短路径：本仓 `skills/stdraw/SKILL.md` 是标准 Agent Skill
（`npx skills add jacky510/stdraw` 可直接安装）；本文是详版说明书，两者内容一致。

## 能做什么

1. **2D 布局（定理级）**：可平面图 → 平面嵌入 + 可见性表示，线全竖直、0 交叉有定理保证；
2. **3D 升维**：不可平面或想要立体形态时，节点排成规则立体（球面/立方体/四面体/圆锥），
   空间弦线不相交，投影交叉由相机解决；
3. **质量证书**：五指标（交叉 / 线穿无关卡 / 平均边长 / 行对齐率 / 卡间净距）+
   排布指标（间距变异系数 CV）+ 诚实分级；
4. **环路语义审计（lint）**：验证声明环闭合性、R/B 极性奇偶，独立枚举全图回路对照；
5. **渲染**：独立 HTML（2D 内联 SVG 零联网；3D 用仓内 `assets/three.min.js`）。

## 安装

```bash
pip install stdraw          # 或在仓内 pip install -e .
# 唯一依赖 networkx；Python >= 3.9
```

## CLI

```bash
stdraw layout <input.cld|.json> [--outdir DIR] [--pitch N] [--skip-3d] [--solids LIST] [--name NAME]
# 等价：python -m stdraw layout ...
```

| 选项 | 默认 | 说明 |
|---|---|---|
| `--outdir` | `stdraw-out` | 产出目录 |
| `--pitch` | 56 | 行距 px；小图调大（如 62）更易过净距门禁 |
| `--skip-3d` | off | 只跑 2D 层 |
| `--solids` | `sphere,cube,tetra,cone` | 3D 形体列表 |
| `--name` | 取 DSL graph 名 | 证书里的图名 |

## 输入格式（.cld DSL）

行导向文本，`#` 起注释。最小闭环 = 变量 / 极性边 / 回路标签（分组可选）：

```ld
graph "图名"
var rate "采纳率"                       # 变量（先声明后引用）
rate -> + adopters @loops R1,B1        # 极性边（+ 同向 / - 反向）+ 参与的回路
loop R1 "采纳扩散" "R" [rate, adopters, word]   # 声明回路：节点序列 + 期望类型 R/B
```

完整语法：[docs/dsl-spec-v0.1.md](docs/dsl-spec-v0.1.md)。也接受 JSON 图模型
（`nodes`/`edges`/`loops`，结构同 `graph.json` 输出）。

## 输出（全部落在 `--outdir`）

| 文件 | 内容 | agent 怎么用 |
|---|---|---|
| `graph.json` / `graph.cld` | 图模型正规化 + DSL 往返文本 | 下游程序化消费 |
| `layout.json` | 2D 交付坐标（全整数、2px 网格） | 渲染 / 复算 |
| `geometry_report.json` | 11 项几何自检，`fail>0` 时 CLI exit 1 | **CI 门禁**（断言 fail==0） |
| `certificate.json` | 五指标 + 门禁 + 诚实分级 | **质量断言**（见下） |
| `loops_audit.json` | 环路审计：声明/闭合/枚举/问题 | 断言 `summary.problems == 0` |
| `demo-2d.html` | 2D 交付页（证书内嵌） | 直接给人看/打印 |
| `positions3d.json` / `demo-3d.html` | 3D 各形体坐标 + 交互页 | demo-3d 需与仓内 `assets/` 相对路径同仓 |

## 证书怎么读（诚实分级语义）

`certificate.json` 的 `grade` 字段：

| grade | 语义 |
|---|---|
| `最优` | 排布要求满足 + 线 0 交叉（定理保证） |
| `其次` | 排布要求满足 + 交叉 ≤2 处（`crossing_details` 给坐标供复核） |
| `最次` | 3D 升维交付（2D 层不适用或被放弃时） |
| `未获证书` | 其余情况——**如实不评级**。这不是错误，是诚实边界 |

铁律：stdraw **绝不宣称任意图 0 交叉**。CLD 环多常不可平面，0 交叉有数学边界；
不可平面输入抛 `NotPlanarError`（CLI 打印诚实降级并继续 3D 层，不算失败）。
agent 向用户转述时**必须原样传达分级**——拿到「未获证书」不许说成「完成了」。

典型断言（agent / CI 通用）：

```python
cert = json.load(open("out/certificate.json", encoding="utf-8"))
assert cert["metrics"]["crossings"] == 0 and cert["grade"] == "最优"
audit = json.load(open("out/loops_audit.json", encoding="utf-8"))
assert audit["summary"]["problems"] == 0
```

## 确定性

同输入同输出（逐字节一致，含 3D 指派与 HTML）。布局无 RNG，上游库全部种子化或
确定性实现——产出文件可以安全进版本库，diff 干净。

## 局限（诚实边界，转述给用户时不要夸大）

- 2D 层不做平面化降级：不可平面输入抛 `NotPlanarError`，降级策略是后续路线图；
- 「无关线遮挡式穿卡」为设计允许（卡片不透明），证书如实计数（`occlusions_true_0px`）；
- 3D 层不做 2D 交叉承诺；
- 布局层是可替换实现（当前：平面嵌入 + 车道装箱）。

## MCP server（预留位）

MCP server 形态在路线图中（规划中，未实现）。当前 agent 集成走 CLI + JSON 文件：
任何能跑命令、读 JSON 的 agent 都能完整使用 stdraw。实现后本节会更新接入方式。

## 版本

当前 0.1.0（`stdraw.__version__`）。DSL 为 v0.1 草案，向后兼容升级会同步 bump 与规范文档。
