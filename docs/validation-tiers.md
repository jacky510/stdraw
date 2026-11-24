# 验证档位重划方案（2026-11-11）

> 状态：**已拍板**（2026-11-11，五项裁决原文见 §7）。本文件只定方案与档位纪律；
> 实现已按拍板口径落地（sweep 工具档位化 + n50 退役注记 + ZCODE 任务书存档），
> 不含任何引擎行为改动。
> 背景：全量逐字节门在 n50 尾段暴露验证成本过高（单图 21 分钟独占、50–57 分钟
> 多卡争抢）。jacky 拍板方向（原话口径，T6 卡 comment 留痕）：
> 「n50 全量逐字节验证不值得——n10 用现行算法，n20 档准备 ZCODE 升级计划，
> n>20 直接走 graphviz 后端；单图 >30 分钟 = 失去软件实用性红线。」
> 卡面修订版把三档边界定为：n10 档验证到 20 节点 / n20 档验证到 30 节点 /
> >30 节点全部取消验证。本文按卡面修订版展开。

## 0. 实测基线（本文所有数字的出处）

| 数据点 | 数字 | 出处 |
|---|---|---|
| 基准语料耗时（WS5 修复后口径） | n10 中位 ~54s / n20 ~21s / n30 ~32s / n50 ~76s | `benchmarks/REPORT.md` §4（引擎版本 bf08643+，基准机口径） |
| 现行引擎（v0.7.15，吸附门加入后）n20 单张 | 184s（rc=1 诚实降级、产物照常落盘） | 2026-11-11 档位探针，单样本，本机 |
| 现行引擎 n30 单张 | 385s（6.4min，rc=1 诚实降级、产物照常落盘）——已贴近 ZCODE P95 目标线 | 2026-11-11 档位探针，单样本，本机（负载未隔离，Z1 复测为准） |
| 现行引擎 n50 单张 | 21min 独占；50–57min 多卡争抢 | T6 收口实测（ref-scrubbed 卡） |
| n20 现行墙钟构成 | ~71% 在 `anchor_snap.snap`（85.4s/张） | T3 分段计时（`STDRAW_TIMING=1`，观察性、零漂移） |
| 逐字节门存量结果 | 86/101 对 sha256 全同、0 漂移（classic 21 全部 + 语料 65 张；n50 尾段 15 张 jacky 豁免） | T6 收口裁定 |
| 语料构成 | classic 19+examples 2（=21 渲染入口）+ random n10/n20/n30/n50 各 20 = 101 | `benchmarks/manifest.json` |
| graphviz 本机形态 | Graphviz 16.1.0 win64 已随仓 `benchmarks/tools/env/`（run_graphviz.py 同源评测用）；系统 PATH 无 dot | `benchmarks/tools/run_graphviz.py:18` |

**注意两点口径**：①基准耗时（§4）与现行引擎耗时差一个吸附门时代的量级
（n20 21s→184s），档位目标必须按**现行引擎**实测定，不按 REPORT 旧数字；
②rc≠0 ≠ 没有产物——随机稠密图诚实降级（grade uncertified）时 layout.json
照常落盘，逐字节门只判「文件存在 + sha」（T4 sweep 既有口径）。

### 0.1 已知边界与已知缺陷（tier-A rc=1 清单；2026-11-24 vg 双几何返修后双腿 sweep 实测）

出处：返修卡 tier-A sweep（`benchmarks/tools/sweep_tiers.py --tier A`，`cp-sat-layered` 口径，Python 3.12 + ortools，
同机）：基线腿 = main 9cc64e8 原树，返修腿 = 返修分支；rc=0 图按 index 记录的 sha256 逐字节比对，rc=1 图
（index 不记 sha）按落盘交付物 sha256 比对。
两腿 rc 分布一致：rc=0 44 图、rc=1 16 图（0.9.0 收尾腿的 random-n20-i18 超时 1 例本轮两腿均 rc=1 落盘，
890s 踩线级、负载相关，rc 分布以「未超时」口径记）。
CLI 退出码语义：**rc=1 = `geometry_report.json summary.fail > 0`**（CI 门形态），交付物照常落盘，
`certificate.json` 的 `grade` 才是质量结论；rc=2 = 输入/配置错误（DSL 校验失败、手工布局不可用、未知立体），
无交付物。

| 归因（check 编号见 geometry_report.json） | 图数（返修后） | 判定 | 处置 |
|---|---|---|---|
| check 1 `crossings<=2` 软目标未达（≥3 交叉） | 16（random-n10-i12 + 15 张 n20） | **已知边界**：n≥10 随机稠密图的 cp-sat 预算内最优 incumbent，局部搜索邻域只有行内平移/相邻交换；交叉是软目标，不得放宽门阈值求绿 | 维持 uncertified 诚实评级；大邻域属 roadmap |
| check 13 `path_d` 渲染/校验折线偏差 >1.5px | 基线 13 → 返修后 **0** | **已返修**（vg 路由 `points` ↔ `vg_corners` 双几何，anchor_snap 延迟/回退后原样出货；方案 b 见 `docs/routing-gates.md` §3 第 7 条）：返修后 13 图 check 13 清零，rc 仍为 1（其余已知边界） | 13 图证书按再生协议更新；门阈值零改动 |
| check 3 边-盒净距（15）/ check 2 盒压（6）/ check 4 锚点角（5）/ check 11 交叉双记账（2） | n20 子集 | **已知边界**：与 check 1 同源（稠密随机图的局部搜索邻域限制），返修前后逐图不变 | 维持 |

rc≠0 图不影响 rc=0 图的逐字节门；引用零回归数字时按 rc=0 子集口径。

## 1. 档位定义（拍板项 D0）

| 档 | 节点域 | 算法 | 验证范围 | 单图耗时目标 |
|---|---|---|---|---|
| **A（现行算法档）** | n ≤ 20 | 现行 auto-v2（含吸附门全家桶） | 逐字节门**全量**到 20 节点 | 维持现状；n10 ≤ 2min / n20 ≤ 4min（P95，现行实测内） |
| **B（ZCODE 升级档）** | 21 ≤ n ≤ 30 | 现行算法 + ZCODE 升级计划（§4） | 逐字节门**抽样**；ZCODE 达标后升全量（验到 30 节点） | 升级验收：n30 全 20 张 P50 ≤ 3min、P95 ≤ 6min、0 例触 30min 红线 |
| **C（graphviz 路线档）** | n > 30 | 现行算法（graphviz 后端不建，见 §3 裁定） | **全部取消验证**（不跑逐字节门、不进收口 sweep） | 红线：单图 > 30min = 失去软件实用性（graphviz 实测秒级，红线只约束 stdraw 自身管线） |

> **2026-11-14 范围拍板（jacky，planarization 实现卡转达）**：stdraw 本体能力上限钉死
> **n≤20**；n30 能力移交 **stdraw20 线**（z.code 承接）。B 档（ZCODE 升级计划）
> 在 stdraw 本体内**不再推进**——本表 B 档行与 §4 任务书存档作历史参考，
> stdraw 侧验收到 A 档（n≤20）为止。

## 2. 语料档位重划与处置清单（任务①）

### 2.1 逐字节门新全量对拍范围

- **A 档全量腿 = 61 图**：classic 21 + random n10×20 + random n20×20，双腿
  （改前基线 / 改后）双跑 layout.json sha256 对拍，沿用 T6 sweep 方法论
  （manifest 断点续跑、按 .cld 源聚合归因、证书类产物按卡验收面扩展对拍）。
- **B 档抽样腿 = n30×5**：固定抽样 `i00 / i04 / i09 / i14 / i19`（与 CI B 层
  抽样风格一致、确定性），双腿对拍；**ZCODE 验收轮**才跑 n30 全 20 张。
- **C 档（n50×20）= 退役**，不进任何 sweep。

### 2.2 n50 语料 20 张的处置（拍板项 D1）

推荐：**文件原地保留 + 档位表标注退役**。

- AGENTS.md 红线「不得动既有语料」——移动/删除文件属违规，且会断
  `benchmarks/raw/` 里 n50 基准证据的语料回放链；
- 落地形态：本文件的档位表即退役声明；`benchmarks/manifest.json` 与
  `benchmarks/tools/validate_corpus.py` 在实现卡里加 `tier: retired` 注记
  （纯元数据，不碰 .cld）；已发布数字（REPORT.md）是历史快照**不回改**，
  如需注记归后续发布卡；
- n50 的 raw 证据（19/20 ok 那轮）保留作历史基准，不删。

### 2.3 抽样清单汇总（快门用）

| 族 | 抽样 | 用途 |
|---|---|---|
| classic | 全 21 张 | 每卡快门 + 收口门 |
| n10 | `i00 i01 i04 i05 i19`（沿用 CI 现有抽样） | 快门 |
| n20 | `i00 i07 i12` | 快门 |
| n30 | `i00 i04 i09 i14 i19` | 收口门抽样腿；ZCODE 验收轮升全量 |
| n50 | — | 退役，不再跑 |

## 3. graphviz 路线裁定（拍板项 D2：不接入）

**裁定：不接入 graphviz 后端。** 方案 B（独立 CLI 模式）否决，整条后端路线
不建（G1/G2 不建）；方案 A（静默 fallback）维持否决；方案 C 不再存在前提。

**用户推荐口径**：对 >20 节点、stdraw 管线耗时超出可接受范围（红线：单图
> 30min = 失去软件实用性）的图，推荐用户**自行**用 graphviz 出图——仓库
`benchmarks/tools/run_graphviz.py` 是同源评测工具（Graphviz 16.1.0 win64
已随仓 `benchmarks/tools/env/`，调用方式见该文件头注释），用户可直接取用。
stdraw 自身不对 graphviz 产物做任何包装、背书或证书化。

**本节原三方案对比（方案 A/B/C）作废，留档见 git 历史。**

## 4. ZCODE 升级计划档（任务③，拍板项 D3）

> **本节验收数字已转存 `docs/zcode-upgrade-brief.md`（任务书存档备用）**；
> Z1/Z2/Z3 实现卡本轮不建，启用时以该任务书开卡。以下为拍板口径原文存档。

**定义**：n21–30 档的算法升级工作代号，目标 = 该档在红线内达到可交付质量 +
可验证耗时。基准语料密度口径：m = round(1.6n)（E/N ≈ 1.6 稀疏族）。

**边界**：20 < n ≤ 30。21–25 由 n30 达标自动覆盖（同算法族、耗时单调），
不单设档。

**可测验收目标（已拍板，D3）**：

| 指标 | 目标 |
|---|---|
| 耗时 | n30 语料 20 张全量：单图 P50 ≤ 3min、P95 ≤ 6min、max ≤ 10min，0 例触 30min 红线 |
| 质量 | 证书硬门口径**不放宽**（压线/净距/锚点/视觉交叉语义不变）；rc=1（诚实降级）率如实统计且不高于现行 |
| 确定性 | 输出逐字节可复现（同输入二跑 sha 全同，沿用现行口径） |
| 漂移面 | A 档（n≤20）61 图逐字节零漂移（构造性事实 + sweep 验证） |

**分阶段路线**（每阶段独立开卡、独立验收）：

- **Z1 计时归因**（~0.5 天）：复用 T3 的 `STDRAW_TIMING=1` 观察性计时
  （零漂移纪律已沉淀：env 开关 + stderr-only + 关态双跑 sha 对拍）。已知起点：
  n20 现行墙钟 ~71% 在 `anchor_snap.snap`；n30 的分布待 Z1 实测。
- **Z2 精确等价加速**（1–2 天）：只做「输出逐位一致」的优化（缓存键控、
  bbox 预过滤、增量维护三类先例），三重验证纪律（差分对拍 + 指纹对拍 +
  全语料 sha 对拍）。
- **Z3 算法级改法**（视 Z2 结果开卡）：若 Z2 后仍超目标，评估稠密 DEFERRED
  路径在 21–30 的取舍、分层路由预算等——属行为面，另行拍板。

## 5. 逐字节门的保留与频率（任务④）

**结论：保留在 A/B 档，分四层频率。** 确定性铁律（同输入同输出逐字节）不因
档位重划动摇——砍掉的是「对 >20/30 节点也全量双跑」的成本，不是确定性承诺。

| 层 | 范围 | 频率 | 预估耗时（本机） |
|---|---|---|---|
| 快门 | classic 21 + n10×3 + n20×2 双跑 | 每张行为改动卡必跑 | ~30–40min |
| 收口全量门 | A 档 61 图 + n30 抽样 5，双腿 | 每张行为改动卡**一次**（收口前，验收快慢门纪律：全量只跑一次） | ~3–4h（后台） |
| ZCODE 验收轮 | n30 全 20 张 + A 档 61 图回归 | 仅 ZCODE 验收时 | ~6–8h（后台，分片） |
| CI | 维持现状（classic 冻结层 + n10 抽样 B 层） | 每 push | 不变 |

补充口径：

- **逐字节全量门不上 CI**：GitHub runner 抽签离散 5 倍（相邻同内容 run
  941s ↔ 2809s 实测），全量门留本地收口，CI 维持抽样层；
- **文档/渲染卡**只跑 demo freshness + pytest，不进全量门；
- n30 抽样腿的产物对拍按卡验收面扩展（T6 教训：不只比 layout.json，
  certificate/geometry_report/loops_audit 按改动面列入）。

## 6. 时间预期与成本估算（实现卡拆分预估，全部本地 CPU、零 API 成本）

| 卡 | 内容 | 人力预估 | 机器时间（验证窗口） |
|---|---|---|---|
| V1 | sweep 工具档位化（A/B/C 分层 + manifest 标注）+ 语料退役注记 | ~0.5 天 | 快门 ~30min（已落地：`benchmarks/tools/sweep_tiers.py`） |
| Z3 | 视 Z2 结果（任务书见 `docs/zcode-upgrade-brief.md`） | 另拍板 | — |

（G1/G2（graphviz 后端）与 Z1/Z2 行已按拍板裁定移除：D2 后端路线不建；
Z1/Z2 并入 `docs/zcode-upgrade-brief.md` 任务书，启用时再开卡。）

## 7. 拍板记录（2026-11-11，五项裁决原文）

| # | 拍板项 | 裁决 |
|---|---|---|
| D0 | 档位边界 | **A 档 n≤20 全量逐字节门 61 图 / B 档 n21–30 ZCODE 升级档 / C 档 >30 取消验证** |
| D1 | n50 语料处置 | **n50 语料原地保留 + manifest 标注退役，不删不移**（已落地：manifest + `validate_corpus.py` 加 `tier: retired` 注记） |
| D2 修订 | graphviz 接入形态 | **不接入 graphviz 后端**（方案 B 否决、整条后端路线不建、G1/G2 不建）；文档推荐用户对 >20 节点图自行用 graphviz（`benchmarks/tools/run_graphviz.py` 同源评测工具）。§3 作废、§6 去掉 G1/G2/Z1/Z2 行 |
| D3 | ZCODE 验收数字 | **n30 全 20 张 P50 ≤ 3min / P95 ≤ 6min / max ≤ 10min、0 例触 30min 红线**，写进 `docs/zcode-upgrade-brief.md` 任务书存档备用；Z1/Z2 实现卡本轮不建 |
| D4 | 收口全量门范围 | **A 档 61 图双腿 + n30 抽样 5 张（i00/i04/i09/i14/i19）**，每行为卡收口跑一次，不上 CI（`sweep_tiers.py --tier full` 即此门） |

## 8. 解释器口径（2026-11-11 返修整改落地）

**全量对拍 sweep（`sweep_tiers.py`）必须用含 ortools 的解释器跑**（实测口径：
含 ortools 9.15 的系统级解释器，本机绝对路径不落发布面）。
原因：分层 cp-sat 引擎只在含 ortools 的解释器下生效；无 ortools 的解释器（如仓
.venv）走 construct 回退引擎——早期一次「59 图零回归」表即在回退口径下复算，
未能覆盖同期视觉验收在分层真实路径上发现 i00 压框 4→25 / 擦边 0→4 回归。

工具侧防再犯（已落地）：
- `sweep_index.json` 记录 `_meta.engine_caliber`（`cp-sat-layered` /
  `fallback-construct`）与 `interpreter`，每图另记 `rec.engine`（layout.json
  `meta.position_engine`），逐字节对比表自带口径标注；
- 无 ortools 时启动打 **DEGRADED ENGINE CALIBER** 横幅（stdout+sweep.log）；
- 同一 leg 中途换解释器续跑（mixed-caliber resume）显式 WARNING；
- `--compare` 双腿口径不一致时打 WARNING（跨口径字节对比无意义）。

`tests/ci_checks.py` 同批整改：无 ortools 时开头打 DEGRADED 横幅、结尾摘要附
`engine caliber: fallback-construct (DEGRADED — cp-sat layered path NOT covered)`
——绿色但降级，先报可见缺陷。

## 9. 读图终审 checklist（2026-11-15 追加拍板，排布类交付必答）

背景：fan-d17 一字排开曾拿到 grade best——三层失守的第三层是「读图三道关
只查缺陷不查设计」。机器门（形态一致性门 + 反向门，见
`docs/layout-modes.md` §放射排布/§静默回退审计）封住前两层后，人读图层
补两项必答：

1. **拓扑合理性终审**（排布类交付的视觉验收卡必答项，由编排方派验收卡
   时内置）：对照 `benchmarks/manual/` 手拉基准回答「这个排布像不像人会
   做的」——hub 是否居中、环是否围合、有没有把放射拓扑排成一字排开；
2. **长边视觉抽查**（worker 自验读图 checklist 项）：数一遍图里超过
   2×中位边长的可见长线，任何一条都要在交付说明里给出成因
   （机器门 `radial_long_edge_rate_zero` 已把放射族钳到 0，此项兜住
   其他形态档）。

## 10. 金标准基模集（2026-11-24 先行批，8 张；全仓 P1 改动的验收基准）

**定位**：一组小而硬的验收基准——8 张最常用的经典系统基模（每张 3–8 节点，
守 n≤20 硬限），任何动引擎的改动都必须让这 8 张图「全 best、FAIL=0、字节
不漂移」。它是 A 档 61 图逐字节全量门的**子集 + 独立快门**（≈2 分钟跑完，
不重定义 A 档口径、不碰 `tests/baselines/` 冻结基线），用于 P1 改动的
日常回归；A 档全量腿仍按 §2.1 在卡收口时跑。

**存放**：`tests/golden/<基模>.cld`（8 张源文件）+ `tests/golden/baseline.json`
（入库基线）。门脚本 `tests/golden_gate.py`，CI 相位 M（checks-corpus 作业，
需 solver 层）。

**门语义**（任一不满足即红）：
1. 每张图走完整 CLI 管线（`python -m stdraw layout`）后：`certificate.json`
   的 `caliber=v2-hardgates`、`grade=best`、全部硬门为真、`crossings=0`、
   `visual_crossings=0`、`geometry_report.json` 的 `fail=0`、
   `loops_audit.json` 的 `problems=0`、`deliverable=true`；
2. 与 `baseline.json` 逐图比对，**漂移即报警**：`certificate.json` /
   `loops_audit.json` 取原始字节 CRLF→LF 折叠后的 sha256；`layout.json`
   取去掉 `engine_version` 字段后的规范 JSON sha256（该字段随版本收尾变，
   其余皆为内容）；`.cld` 源文件本身也钉 sha256——改夹具也是漂移；
   `grade / placement / gates_passed / crossings / nodes / edges` 任一变化
   同样报警；
3. **耗时基线**：逐图墙钟秒记入 `baseline.json` 的 `timing_ref`（平均 +
   最大 + 记录机平台），每次运行打印对照（供 T12 提速对照）；超过参考值
   2 倍只打 WARN 不判红——跑机速度不是仓属性；
4. 无 ortools 的解释器下门**拒绝运行**（基线是 cp-sat 口径，construct 回退
   口径的渲染不可比，见 §8）。

**重铸基线**（唯一入口）：`python tests/golden_gate.py --update-baseline`，
只在获批的卡里做（引擎行为有意变更 / 版本收尾 / 夹具有意修订）；脚本先过
全部硬门再写盘，并打印相对旧基线逐字段的变化清单。非 best 的渲染永不被
写进基线。

**本地跑法**：`python tests/golden_gate.py`（约 2 分钟）；只跑一张
`--only escalation`；`--json out.json` 导出度量。

### 10.1 先行批 8 张与 R/B 回路人工核对表

每条回路沿箭头读一遍极性：全同向 = 增强（R），奇数条负向 = 平衡（B）。
「核对」列是人工读图结论；`loops_audit` 的独立枚举与之一致
（`problems=0`、`declared=enumerated`，`tests/test_golden_set.py` 守住）。

| 基模（文件） | 节点/边 | 回路 | 极性链 | 核对 |
|---|---|---|---|---|
| 增长极限 `limits-to-growth` | 3/4 | R1 增长引擎 | 行动 +> 状态 +> 行动 | R |
| | | B1 增长制约 | 状态 +> 制约 -> 行动 +> 状态 | B |
| 舍本逐末（补救恶化）`fixes-that-fail` | 3/4 | B1 症状缓解 | 问题 +> 修复 -> 问题 | B |
| | | R2 后果反噬 | 问题 +> 修复 +> 后果 +> 问题 | R |
| 舍本逐末（转嫁负担）`shifting-the-burden` | 4/6 | B1 快速见效 | 问题 +> 症状解 -> 问题 | B |
| | | B2 根本治理 | 问题 +> 根本解 -> 问题 | B |
| | | R3 依赖加深 | 问题 +> 症状解 +> 副作用 -> 根本解 -> 问题 | R |
| 恶性升级 `escalation` | 4/4 | R1 军备升级 | 甲行动 +> 乙威胁 +> 乙行动 +> 甲威胁 +> 甲行动 | R |
| 富者愈富 `success-to-the-successful` | 4/5 | R1 甲方滚雪球 | 甲资源 +> 甲成功 +> 甲资源 | R |
| | | R2 乙方滚雪球 | 乙资源 +> 乙成功 +> 乙资源 | R |
| | | （非环耦合） | 甲资源 -> 乙资源（负向），有限资源池此消彼长 | — |
| 公地悲剧 `tragedy-of-the-commons` | 4/6 | R1 越用越赚 | 用量 +> 收益 +> 用量 | R |
| | | B2 收益摊薄 | 用量 +> 总量 -> 收益 +> 用量 | B |
| | | B3 资源枯竭 | 用量 +> 总量 -> 资源 +> 收益 +> 用量 | B |
| 目标侵蚀 `eroding-goals` | 5/6 | B1 目标追求 | 差距 +> 行动 +> 状态 -> 差距 | B |
| | | B2 目标漂移 | 差距 +> 压力 -> 目标 +> 差距 | B |
| 增长与投资不足 `growth-and-underinvestment` | 6/8 | R1 增长引擎 | 努力 +> 绩效 +> 努力 | R |
| | | B2 增长受限 | 绩效 +> 制约 -> 绩效 | B |
| | | B3 产能补齐 | 制约 +> 需求 +> 投资 +> 产能 -> 制约 | B |

结构出处：Senge 1990《第五项修炼》第 7 章 / Braun 2002《The System
Archetypes》/ Kim 1998《Systems Archetype Basics》（公有领域结构）。
标签一律纯中文（含中文标点）：`text_width` 取「字体实测」与「解析式」
的较大者，而解析式给 CJK 字符 1.10×fs、CJK 方块字实测 advance≈1.0×fs
——解析式恒占优，于是有 pillow（Windows msyh）与无 pillow（Linux CI
纯解析式）同宽，布局字节跨平台一致——`tests/test_golden_set.py` 守住
「标签只许 CJK 全角字符」这一前提。

### 10.2 先行批实测（2026-11-24，本机 cp-sat 口径，Python 3.12）

8/8 grade best、11–12/11–12 硬门全过、crossings 0、visual 0、loops 0、
geometry fail 0；排布形态：ring-cycle ×5、bowtie-vertex ×1、
column-chain ×1、layered ×1。耗时 avg 2.1s / max 6.2s（success-to-the-
successful 最慢）。候选而未入批：意外对手 Accidental Adversaries——
SEI 2010 六节点忠实版 `uncertified`（ring-cycle，visual crossings 3），
四节点精简版虽 best 但丢了「面向对方的行动」语义，留给后续补齐批次
（届时须声明 5 条环：两组自利环 + 合作环 + 两条反噬环 + 互害环）。
