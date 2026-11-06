# AGENTS.md — 给 agent 的 stdraw 使用说明（v0.6.0）

stdraw 是 planarity-aware 的系统思维图（CLD / 因果回路图）引擎：
**文本 DSL 进，带质量证书的图出**。它专为 agent 设计——零交互、确定性输出、
每个交付物都是机器可读的 JSON + 可直接打开的 HTML。

给 agent host 的最短路径：本仓 `skills/stdraw/SKILL.md` 是标准 Agent Skill
（`npx skills add jacky510/stdraw` 可直接安装）；本文是详版说明书，两者内容一致。

## 能做什么（v0.6.0 终态）

1. **auto-v2 默认配方（模式化排布）**：按图结构确定性选择排布模式，优先级
   = 领结对对称（双三角共边，4 节点 5 边）→ 纵列（3≤n≤12 ∧ 最长简单回路
   3≤k≤4 ∧ k<n）→ 环形（纯环 / 主环覆盖 ≥n−2 或环边占比 ≥0.9 ∧ k≥5 或
   覆盖全图）→ 分层；每个模式带**试验闸门**（构造后排布跑同一布线器复核硬门
   代理），任一不过**静默回退**下一级，负例逐字节不变。规则详见
   [docs/layout-modes.md](docs/layout-modes.md)。
   - **排布硬门**：框不压线 = 0（任意角度、1px 余量）、边-框净距 ≥16px、
     锚点平滑、卡间净距 ≥16px（目标 36px 呼吸感）、互环对（a↔b 双向边）两线
     分离 ≥4px、线-线视觉重合 = 0；排布规律门按模式切换——ring：环上等间距
     CV ≤0.05 + 正多边形模板拟合 ≤0.05；column：主链列轴偏差 ≤2px + 主链
     行距恒等；symmetric：镜像轴误差 ≤2px；layered：行距恒等 + 列吸附；
   - **交叉与行对齐是报告项（软目标）**：排布规律达标时允许 ≤2 交叉（秩序与
     优美优先）；分级语义不变——「最优」仍要求 0 交叉；
   - **R/B 极性颜色化**（替代文字徽标）：单环边 R=琥珀 `#d97706`、B=天蓝
     `#0284c7`；多环异 kind 或非环边中性灰 `#64748b`；负极性边虚线
     （`stroke-dasharray="6 4"`）。
2. **数学布线层（WS3）**：绕障 = 净距膨胀障碍**可见性图 Dijkstra 最短路**
   （图上精确最优；相对圆角障碍连续空间真最短路每贴角至多多
   (2−π/2)·膨胀余量 px）；平滑 = 折角**相切圆弧**（G1 切线连续、曲率有界，
   逐弧净距复检）；互环对走透镜双弧/平行偏移/外围绕行，禁止重合成双箭头线；
   **交叉双口径**：路由理论逐边命中数之和/2 必须等于交付坐标几何复检数，
   不一致拒发证书；折线带固定类型代价（vg 绕障折角 +120 / poly 车道折线
   +40 / wrap 外围绕行 +200）——直线/弧线可行时折线不抢分，折线=最后手段。
3. **精确交叉数层（WS2，`--exact`）**：ordering 插入 ILP + 平面化 oracle +
   B&B 夹逼计算 cr(G)，写入证书 `exactness` 块（`proven_optimal` / `gap` /
   `lb` / `crossing_number`）。已证参考真值：K5=1、K3,3=1（Kuratowski）、
   K6=3（Guy 1960 公式）、Petersen=2——方法学与文献口径见
   [docs/crossing-exact.md](docs/crossing-exact.md)。最优性只相对该文档 §1-5
   定义的模型类成立（good-drawing 口径、安全缩减后的 2-边-连通核族、B&B
   覆盖的可平面子图 × 全嵌入族），不虚称任意画法空间。需可选依赖
   `pip install "stdraw[solver]"`；未装时 `computed:false` 如实标注。
4. **ortho-v1 冻结配方（`--recipe ortho`）**：平面嵌入 + st 编号 + 可见性
   表示，线全竖直、可平面图 **0 交叉有定理保证**；行为冻结、CI
   byte-regression 铁门保护，生产调用方可安全 pin。不可平面输入抛
   `NotPlanarError`（CLI 打印诚实降级并继续 3D 层，不算失败）。
5. **环路语义审计（lint）**：验证声明环闭合性、R/B 极性奇偶，独立枚举全图
   回路对照；`loops_audit.json` 的 `summary.problems` 必须 = 0。
6. **手动微调闭环（拖拽 → 导出 → 复算）**：`demo-2d.html`（auto 配方）内置
   拖拽层——拖节点时**全部线型实时重布线**（JS 移植可见性图最短路，与
   Python 同数学口径；障碍被拖走后旧绕行即时作废）；绕障折点渲染为**可拖
   把手**，拖动即用户锚定，「导出布局」对锚定边写 `edges[].waypoints`；
   `--from-layout` 按手动坐标跑同一布线+证书管线（硬门口径不变、如实
   评分）；`--compare-auto` 同图另跑自动布局输出双证书对比
   `compare-auto.json`；`layout-diff` 出三层 diff（节点位移 / 结构指标 /
   回路语义）。
7. **3D 升维 + viewer**：节点排成规则立体（球面/立方体/四面体/圆锥），空间
   弦线不相交，投影交叉由相机解决；`viewer/index.html` 零依赖交互查看器
   （四种形态 + 拖拽 + 回路面板）。

## 安装

```bash
pip install stdraw              # 或仓内 pip install -e .；唯一硬依赖 networkx；Python >= 3.9
pip install "stdraw[solver]"    # 可选：ortools（auto-v2 CP-SAT 定位精化 + --exact 精确层）
```

未装 solver 时 auto-v2 优雅降级为构造法（功能完整、构造档质量），证书如实标注。

## CLI（以 `--help` 实测为准）

```bash
stdraw layout <input.cld|.json> [选项]        # 布局全管线（等价 python -m stdraw layout ...）
stdraw layout-diff <layout.json> <layout2.json> [--cld 图源] [--diff-out diff.json]
```

| 选项 | 默认 | 说明 |
|---|---|---|
| `--outdir` | `stdraw-out` | 产出目录 |
| `--recipe {auto,ortho}` | `auto` | auto=auto-v2（直线/弧线 + 硬门 + 模式排布）；ortho=ortho-v1（构造法，行为冻结 pin-safe） |
| `--linestyle {straight,arc}` | `straight` | auto 配方线型（arc=全弧线偏好） |
| `--skip-3d` | off | 只跑 2D 层 |
| `--solids` | `sphere,cube,tetra,cone` | 3D 形体列表（逗号分隔） |
| `--pitch` | 56 | 行距 px；小图调大（如 62）更易过净距门禁 |
| `--name` | 取 DSL graph 名 | 证书里的图名 |
| `--exact` | off | 精确交叉数层：B&B 夹逼计算 cr(G) 写入证书 exactness 块（需 `stdraw[solver]`） |
| `--from-layout` | — | 手动布局 JSON（demo-2d.html「导出布局」产物或 layout.json 子集：节点 id→x,y + viewBox [+ edges[].waypoints]）。按手动坐标跑同一布线+证书管线，硬门口径不变、如实评分 |
| `--compare-auto` | off | 配合 `--from-layout`：同图另跑自动布局到 `<outdir>-compare-auto/`，输出双证书对比 `compare-auto.json` |
| `--cld` | — | layout-diff：图源（.cld/.json），启用语义级（回路归属/聚拢） |
| `--diff-out` | — | layout-diff：机器可读 JSON 输出路径 |

示例：

```bash
stdraw layout examples/limits-to-growth.cld --outdir out --pitch 62
python -m stdraw layout examples/limits-to-growth.cld --outdir out --skip-3d
stdraw layout model.cld --outdir out --exact
stdraw layout model.cld --outdir out-manual --skip-3d --from-layout graph-manual-layout.json
stdraw layout-diff out/layout.json out-manual/layout.json --cld model.cld --diff-out diff.json
```

## 输入格式（.cld DSL）

行导向文本，`#` 起注释。最小闭环 = 变量 / 极性边 / 回路标签（分组可选；
布局层不消费分组——排布只由关系决定）：

```ld
graph "图名"
var rate "采纳率"                       # 变量（先声明后引用）
rate -> + adopters @loops R1,B1        # 极性边（+ 同向 / - 反向）+ 参与的回路
loop r1 "采纳扩散" "R" [rate, adopters, word]   # 声明回路：节点序列 + 期望类型 R/B
```

回路标签不是注释——lint 层会对照独立枚举的全图回路验证闭合性与 R/B 奇偶。
完整语法：[docs/dsl-spec-v0.1.md](docs/dsl-spec-v0.1.md)。也接受 JSON 图模型
（`nodes`/`edges`/`loops`，结构同 `graph.json` 输出）。

## 输出（全部落在 `--outdir`）

| 文件 | 内容 | agent 怎么用 |
|---|---|---|
| `graph.json` / `graph.cld` | 图模型正规化 + DSL 往返文本 | 下游程序化消费 |
| `layout.json` | 2D 交付坐标（全整数、2px 网格）；边带 `loop_kinds`/`loop_color` 与布线 `kind`（line/arc/vg/poly/waypoints）及 `via` 折点 | 渲染 / 复算 |
| `geometry_report.json` | 几何自检（CI 门禁形态），`fail>0` 时 CLI exit 1 | **CI 门禁**（断言 fail==0） |
| `certificate.json` | 指标 + 门禁 + 报告项 + 诚实分级 + `placement` 排布模式 | **质量断言**（见下） |
| `loops_audit.json` | 环路审计：声明/闭合/枚举/问题 | 断言 `summary.problems == 0` |
| `demo-2d.html` | 2D 交付页（证书内嵌 + 拖拽微调层） | 直接给人看/打印 |
| `positions3d.json` / `demo-3d.html` | 3D 各形体坐标 + 交互页 | demo-3d 需与仓内 `assets/` 相对路径同仓 |
| `compare-auto.json`（`--compare-auto` 时） | 手动 vs 自动双证书对比 | 量化引擎与人的审美距离 |

## 证书怎么读（诚实分级语义）

`certificate.json`：

- **metrics**：crossings / box_press_1px / edge_box_min_clear / min_card_gap /
  spacing_cv / row_align_rate（模式不适用时**如实 null**，如环形/纵列）+
  报告指标 loop_cohesion_spread（回路聚拢）、center_offset_x、
  line_kind_counts、ring_spacing_cv / ring_template_deviation（环形口径）；
- **gates（硬门，按 `placement` 模式切换）**：以
  `demos/classic-certificate.json` 实测（ring-cycle 模式）为例，9 门
  **9/9 通过**——box_press_zero / edge_box_clear_ge_16 / anchors_smooth /
  min_gap_ge_16 / ring_spacing_cv_le_005 / ring_template_fit_le_005 /
  mutual_pairs_separated / lines_no_coincidence / routing_consistent；
- **reports（报告项，非硬门）**：`crossings_zero`（软目标：排布规律达标时
  允许 ≤2 交叉）与 `row_align_ge_060`；分级语义不受影响；
- **grade**：

| grade | 语义 |
|---|---|
| `最优` | 排布硬门全过 + 线 0 交叉（auto 配方为优化结果，非定理保证；ortho 配方为定理保证） |
| `其次` | 排布硬门全过 + 交叉 ≤2 处（`crossing_details` 给坐标供复核） |
| `最次` | 3D 升维交付（2D 层不适用或被放弃时） |
| `未获证书` | 其余情况——**如实不评级**。这不是错误，是诚实边界 |

铁律：stdraw **绝不宣称任意图 0 交叉**。CLD 环多常不可平面，0 交叉有数学
边界。agent 向用户转述时**必须原样传达分级**——拿到「未获证书」不许说成
「完成了」。

典型断言（agent / CI 通用）：

```python
cert = json.load(open("out/certificate.json", encoding="utf-8"))
assert cert["grade"] == "最优"          # 或按需 >= "其次"
geo = json.load(open("out/geometry_report.json", encoding="utf-8"))
assert geo["summary"]["fail"] == 0
audit = json.load(open("out/loops_audit.json", encoding="utf-8"))
assert audit["summary"]["problems"] == 0
```

## 确定性

同输入同输出（逐字节一致，含 3D 指派与 HTML）。布局无 RNG，CP-SAT 单
worker + 固定种子；n>10 的 CP-SAT 定位用**确定性时间预算**
（`max_deterministic_time=8`，操作计数口径而非墙钟——同版本同输入在任何
机器上同一 incumbent；`layout.json` meta 的 `solver_status`/
`solver_det_budget` 如实标注）。产出文件可以安全进版本库，diff 干净。

## 基准对比摘要（benchmarks/，protocol 见 REPORT.md §2）

语料 = 19 张经典 CLD + 80 张固定种子随机稀疏图 × {stdraw ortho / stdraw
auto / auto+精确层} × {Graphviz 16.1.0 dot/neato/sfdp, ELK layered}，六指标
同源实现、全部原始评测 JSON 留证 `benchmarks/raw/`。**测量基点**：stdraw
auto/auto-exact 为 WS5 性能修复后引擎（b4ea801+）重测；Graphviz/ELK 基线
与 stdraw-ortho 沿用 WS4 同机实测。

classic 均值（REPORT.md §7）：

| 工具 | 交叉 | 框压线 | 净距违规 | CV | 行对齐 | 耗时s | 成功率 |
|---|---|---|---|---|---|---|---|
| stdraw·ortho(构造法) | 0.0 | 1.4 | 1.7 | 0.296 | 0.48 | 0.01 | 19/19 |
| stdraw·auto(WS3布线) | 0.2 | **0.0** | **0.0** | 0.133 | 0.34 | 10.02 | 19/19 |
| stdraw·auto+WS2(精确层) | 0.2 | **0.0** | **0.0** | 0.133 | 0.34 | 10.42 | 19/19 |
| Graphviz dot | 0.2 | 0.1 | 2.6 | 0.139 | 0.34 | 0.03 | 19/19 |
| Graphviz neato | **0.1** | 1.2 | 3.1 | 0.080 | 0.05 | 0.06 | 19/19 |
| Graphviz sfdp | 0.3 | **0.0** | **0.0** | 0.131 | 0.37 | 0.03 | 19/19 |
| ELK layered | **0.1** | **0.0** | 3.0 | 0.208 | 0.41 | 0.07 | 19/19 |

诚实结论（赢的写赢，输的写输）：

- **赢的域**：classic 上「框压线=0 且净距违规=0」双零达成的工具只有
  stdraw-auto（-exact）与 sfdp，且该组内 stdraw 交叉数更低（0.16 vs
  0.26）；同输入同框尺寸的 CLD 卡片画法 + 硬门语义全维度同时达标是 stdraw
  的比较优势域；
- **输的域**：交叉数全场最低**不成立**（neato/ELK 均值 0.05 更低，代价是
  破坏排布硬门）；运行时间慢基线 **2~3 个数量级**（10.0s vs 0.03–0.07s）；
- **随机稀疏族**：n=20/30 出图 20/20、n=50 出图 19/20，但框压线/净距非 0
  （布线是惩罚最小化非定理保证）；「全规模最好」主张不成立；
- **OGDF**：未同题运行（无构建工具链，如实评估），不参与胜负判定。

## 局限（诚实边界，转述给用户时不要夸大）

- 交叉为软目标（v0.6.0 起）：排布规律优先，硬门全过时 ≤2 交叉可接受
  （「最优」级仍需 0 交叉）；ortho 配方不可平面输入抛 `NotPlanarError`，
  2D 平面化降级在路线图；
- ortho-v1 允许「无关线遮挡式穿卡」（卡片不透明，v0.1 设计口径），证书如实
  计数；auto-v2 的框压线是硬门 = 0；
- 3D 层不做 2D 交叉承诺；
- 随机稀疏图 n≥20：定位为 8det 预算内最优 incumbent（非证到最优），布线
  框压线/净距以 REPORT §4 实测为准（非 0）；`_polish` 回喂仅 n≤10 执行；
- 局部搜索邻域限于行内平移与相邻交换，个别图最后一处交叉可能需更大邻域
  （路线图 M3）。

## MCP server（预留位）

MCP server 形态在路线图中（规划中，未实现）。当前 agent 集成走 CLI + JSON
文件：任何能跑命令、读 JSON 的 agent 都能完整使用 stdraw。实现后本节会
更新接入方式。

## 版本

当前 **0.6.0**（`stdraw.__version__`，与 `pyproject.toml` 一致）。DSL 为
v0.1 草案，向后兼容升级会同步 bump 与规范文档。
