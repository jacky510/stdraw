# hub 桶塌缩诊断报告（branch p0/hub-collapse-diagnosis）

诊断卡：评分器 v2 hub 桶 9 正样本仅 2 个不同得分向量（8/9 塌缩于 81.3）的三项零成本
诊断 + 扰动剂量-响应 + 外部评审（ChatGPT 2026-11-21）扩充的四层审计 / 特征相关性 /
假设 D。**纯诊断**：评分器代码、committed `model-v2.json` 与全部校准产物零改动。

- 诊断脚本：`benchmarks/aesthetic/diagnose_collapse.py`
- 全量数据：`benchmarks/aesthetic/diagnosis-hub-collapse.json`（本报告全部数字出自该文件）
- 复算：仓库开发解释器（Python 3.12）跑
  `python benchmarks/aesthetic/diagnose_collapse.py`（工作树根目录执行；
  本机解释器绝对路径不进被跟踪文件——泄漏门口径）
- 确定性：同树双跑字节一致（输出 sha256 `430cfc96…5c5ba`）；脚本自断言 18 锚点
  分数/路由与 committed `calibration-report-v2.json` 逐位一致（loader 口径复现门）。

口径声明（影响读数的三处）：
1. 加载管线 = `calibrate_v2.py` 同一函数（同筛选、同补边链、同 completeness 门）；
2. 打分只用 committed `model-v2.json`（normalized caliber 胜出口径），不重拟合；
3. 存档文档（negatives 库 / batch-2 草稿）的证书为**代理口径**：直线中心距线段 +
   缺省卡 96×44（引擎交付缺省）过 `metrics.certificate`；现场重生成的引擎候选
   （auto / ortho / auto-arc，`--skip-3d`）用引擎真 `certificate.json`。两种口径在
   表中分别标注，不混用。

---

## 0. 结论速览（假设 A/B/C/D 判别读数）

| 假设 | 判别读数 | 结论 |
|---|---|---|
| **A 特征盲** | hub 模型只保留 2 特征：`alignment_max_coverage`（w=+1.395）与 `bend_total_curvature`（w=−1.498）。9 正样本中 bend **恒为 0.0**（distinct=1），alignment 只有 **2 个取值**（8 个 =1.0，fan-d12 =0.8919）→ 输入侧本来就只有 2 个向量，81.3×8 + 65.4×1 是恒等映射，不是变换压缩 | **成立，主因** |
| **C 优化压缩** | L4 饱和轻微：\|z\|≤1.473，sigmoid 导数 0.152–0.226（p≈0.81 处仍敏感）；L2 标准化后 kept 特征方差 0.035/0.0，L3 z 只有 2 个值（var 0.069）。z 差 0.835 完整保留到输出（81.3 vs 65.4）——压缩层没有吃掉任何差异 | **排除为主因** |
| **C′ 筛选压缩**（评审"第三种解释"的修正落点） | 23/32 个标量在正样本间**有差异**，但被单变量 AUC 筛（\|AUC−0.5\|≥0.30）全部丢弃；其中 aspect_deviation AUC=0.783、layout_n_nodes 0.781、canvas_fill_rate 0.672、visual_centroid 0.656、voronoi_area_cv 0.636、mirror/symmetry_axis_err 0.619——多个近阈值判别信号在进入模型前被砍掉，多元组合信息从未参与 | **部分成立**（是筛选门槛压缩，不是 L2 收缩；权重收缩无从谈起，因为根本没进模型） |
| **D 子形态混合** | 桶内确为多族混合：嵌套环×3、fan/radial×2、梳状×1、非平面×1、多环耦合×1、随机×1（结构二分：radial 5 / non-radial 4）。但按族/结构分组后**组内分数仍全等**（嵌套环组 3 个全 81.3）——混合本身不致病，是 A 让桶"看不见"族差异 | **成立但不独立致病** |
| **B 信号缺维** | 边风格/锚位数据只在 batch-2 导出存在（8/18=43% < MIN_COVERAGE 0.70，v2 卡已如实拒纳）；本审计未发现可由现有单源特征补入的新缺维 | **无新证据** |

**塌缩是缺陷吗——口径修正成立**：hub separation −13.9 **完全由 fan-d12 × soil-erosion
一对贡献**（65.4 vs 79.3；全部 3 个交叉对都含 fan-d12，见 §5）。其余 8/9 hub 正样本
高于全部 23 个 hub 负样本。同图候选内排序读数（漏斗实际用途）：12 个有 ≥2 候选的图
中，人工领先 8 图（delta +2.0 ~ +70.5），**4 图引擎最佳候选与人工在 81.3 完全打平
（delta = 0.0）**——塌缩点不是人工锚专属，引擎输出也批量落进同一点。

## 1. 诊断一：L1–L4 四层审计（hub 桶 9 正样本）

### 1.1 L1 原始 32 标量分布（正样本间）

总口径：`SCALAR_SPECS` 31 项 + `layout_n_nodes` = 32（卡面写"26 特征"指可提取标量集，
实际 dump 全部 32，JSON 含逐项表）。

- **常数（6 个）**：`bend_total_curvature`(0.0)、`loop_edge_crossings`、
  `loop_foreign_nodes`、`loop_overlap_area`、`loop_self_intersections`、
  `min_crossing_angle`（+ 2 个无数据 `loop_edge_length_cv`/`loop_compactness_mean`，
  覆盖率 0）
- **有差异但被 AUC 筛丢弃（23 个）**：近阈值代表——

| 特征 | 正样本 distinct | 正样本范围 | AUC(pos vs neg) | 模型内权重 |
|---|---|---|---|---|
| aspect_deviation | 9 | 0.138–1.123 | **0.783** | —（被筛） |
| layout_n_nodes | 6 | 6–18 | **0.781** | —（被筛） |
| canvas_fill_rate | 9 | 0.063–0.224 | 0.672 | — |
| visual_centroid_px / ratio | 9 | 0.014–0.050 | 0.656 | — |
| voronoi_area_cv | 9 | 0.054–0.732 | 0.636 | — |
| mirror_axis_err / symmetry_axis_err_px | 7 | 0.007–89.19 | 0.619 | — |
| angular_resolution_min | 7 | — | 0.597 | — |
| max_min_edge_ratio | 9 | — | 0.572 | — |
| automorphism_residual | 7 | 0.007–33.51 | 0.286 | — |
| min_spacing_px / ratio | 9 | 0.035–0.226 | 0.308 | — |

- **有差异且保留（1 个）**：`alignment_max_coverage`，distinct=2，范围
  [0.8919, 1.0]，AUC=0.867，w=+1.395（符号约束 expect w>0 ✓）

判别读数：**"特征在正样本间是常数"只对 bend_total_curvature 这一 kept 特征成立**；
其余 22 个常数特征根本不在模型里。塌缩的直接机制 = kept 二特征输入向量只有 2 种。

### 1.2 L2→L4 逐锚点（kept 特征）

| 锚点 | L2 (align, bend) | L3 贡献 (align, bend) | L3 z | L4 分 | sigmoid 导数 |
|---|---|---|---|---|---|
| brand-flywheel | (0.917, −0.690) | (+1.280, +1.034) | +1.473 | 81.3 | 0.152 |
| classic-cld | 同上 | 同上 | +1.473 | 81.3 | 0.152 |
| classic-cld retest | 同上 | 同上 | +1.473 | 81.3 | 0.152 |
| fan-d17 | 同上 | 同上 | +1.473 | 81.3 | 0.152 |
| comb-supply-demand | 同上 | 同上 | +1.473 | 81.3 | 0.152 |
| coupled-underinvestment | 同上 | 同上 | +1.473 | 81.3 | 0.152 |
| nonplanar-credit | 同上 | 同上 | +1.473 | 81.3 | 0.152 |
| random-n10-i05 | 同上 | 同上 | +1.473 | 81.3 | 0.152 |
| **fan-d12** | (0.319, −0.690) | (+0.445, +1.034) | **+0.638** | **65.4** | 0.226 |

- L2 压缩检查：kept 特征标准化后方差 0.035 / 0.0——alignment 的 0.108 原始差被
  σ=1.187 放大为 0.598 标准差差，**L2 没有压缩差异**。
- L4 饱和检查：最大 \|z\|=1.473，导数区间 [0.152, 0.226]，**饱和轻微**；两簇 z 差
  0.835 原样表现为 15.9 分差。分数恒等 = 输入恒等。

## 2. 诊断二：特征相关与有效独立维度（正样本内部）

- 可用特征 29 个；**14 对 \|Spearman ρ\|≥0.9**，其中 4 对 ρ=1.0 完全别名：
  `min_spacing_ratio`~`min_spacing_px`、`mirror_axis_err`~`symmetry_axis_err_px`、
  `visual_centroid_px`~`visual_centroid_ratio`、`hub_centroid_ratio`~`hub_centroid_px`
  （后者是 px 与 px/对角线的确定性缩放——**同一测量的两种单位都当独立特征筛过**）。
- 高相关簇：canvas_fill ~ hub_centroid_ratio ~ hub_centroid_px ~
  hub_neighbor_centrality_ratio（ρ 0.95–0.97）；edge_length_cv ~ max_min_edge_ratio
  （0.983）；aspect_deviation ~ degree_canvas_spearman（−0.917）。
- 方差承载特征 24 个，但 9×29 正样本矩阵秩 = 9（受样本数上限）——**有效独立维度
  ≤ 9，且其中携带判别信息的组合从未被单变量筛保留**。26 键远不是 26 个独立信号。

## 3. 诊断三：假设 D 子形态混合分组

| 分组 | n | 分数 | distinct |
|---|---|---|---|
| family:嵌套环 | 3 | 81.3, 81.3, 81.3 | 1 |
| family:fan/radial | 2 | 65.4, 81.3 | 2 |
| family:梳状 | 1 | 81.3 | 1 |
| family:非平面族 | 1 | 81.3 | 1 |
| family:多环耦合 | 1 | 81.3 | 1 |
| family:random-n10 | 1 | 81.3 | 1 |
| structure:radial(fan-like) | 5 | 全 81.3 | 1 |
| structure:non-radial | 4 | 65.4, 81.3×3 | 2 |

桶内 ≥5 族混合属实；分组不产生更均匀的子群（fan-d12 在两套分组里都落单）。**子形态
混合需要通过"kept 特征看不见差异"才表现塌缩**——治本在特征/筛选层，不在路由层。

## 4. 诊断四：拓扑内口径分离度

### 4.1 跨拓扑 sep −13.9 的构成（v2 现行口径）

- hub pos_min = **fan-d12 (65.4)**；hub neg_max = **soil-erosion (79.3)**。
- 全部交叉对 3 个，**无一例外含 fan-d12**：
  `fan-d12 < soil-erosion (−13.9)`、`fan-d12 < fishing-collapse (−8.1)`、
  `fan-d12 < random-n10-i18 (−5.4)`。其余 8/9 正样本全部 > neg_max。
- **一对难样本拖垮全局数字**：fan-d12 是唯一 alignment < 1.0 的正锚（放射形拖拽
  对齐覆盖天然低），而它没有同图引擎候选（fan 族无 negatives 无源 .cld），
  拓扑内口径下它根本不可比。

### 4.2 拓扑内口径：人工 − 引擎最佳候选（同图 delta）

| 图 | 人工分 | 引擎最佳 | delta | 引擎候选 grade |
|---|---|---|---|---|
| random-n10-i11 | 95.8 | 25.3 | **+70.5** | uncertified |
| nonplanar-inventory | 97.8 | 34.1 | **+63.7** | uncertified/crossed-certified |
| random-n10-i05 | 81.3 | 43.3 | +38.0 | uncertified |
| brand-flywheel | 81.3 | 46.2 | +35.1 | **best** |
| random-n10-i00 | 64.7 | 41.2 | +23.5 | uncertified |
| bowtie-wage-price | 88.6 | 79.3 | +9.3 | best(54.3 档)/uncertified(79.3 档) |
| nested-capacity | 84.1 | 79.0 | +5.1 | best |
| nested-learning | 83.3 | 81.3 | +2.0 | best/uncertified |
| classic-cld | 81.3 | 81.3 | **0.0** | best/uncertified |
| comb-supply-demand | 81.3 | 81.3 | **0.0** | best(28.9 档)/uncertified |
| coupled-underinvestment | 81.3 | 81.3 | **0.0** | best |
| nonplanar-credit | 81.3 | 81.3 | **0.0** | uncertified |
| epidemic-feedback / fan-d12 / fan-d17 | — | — | 不可测（无同图引擎候选） | — |

读数：**4/12 图引擎打平人工**——打平图全部经塌缩点 81.3（引擎 ortho/draft 输出同样
alignment=1.0、bend=0）。漏斗的同图排序能力在塌缩区为零。

### 4.3 同图多候选排序：评分器 vs 现行交付选择

12 图有 ≥2 候选（存档 + 现场 auto/ortho/auto-arc，交付规则=证书 grade 最优 >
交叉数升序 > 分数降序，交付不读美学分——设计如此）：

- **一致 7 / 分歧 5**。典型分歧：bowtie-wage-price 评分器首选 ortho（79.3，
  grade=uncertified），交付按证书选 grade=best 的 auto/auto-arc（54.3）——评分器
  偏好一张证书更差的图。
- 引擎候选频繁落进塌缩点（classic-cld ortho、nested-learning auto、coupled draft
  均 81.3）：**塌缩点区分不了人手与引擎**。

## 5. 诊断五：高分负样本审计（v2 打分，top 8 / 40）

| 负样本 | 族 | 分 | 路由 | 交叉 | 证书 grade | kept 距最近锚 |
|---|---|---|---|---|---|---|
| urban-migration | classic/多环耦合 | **87.7** | ring | 0 | second | 0.735 (epidemic-feedback) |
| **soil-erosion** | classic/嵌套环 | **79.3** | hub | **0** | **best** | **0.086**（brand-flywheel） |
| **fishing-collapse** | classic/嵌套环 | 73.5 | hub | **0** | **best** | 0.302（brand-flywheel） |
| burnout-attrition | classic/多环耦合 | 71.0 | ring | 0 | second | 1.718 |
| random-n10-i18 | random-n10 | 70.8 | hub | 2 | second | 0.145 |
| random-n10-i17 | random-n10 | 62.8 | hub | 2 | second | 0.633 |
| random-n10-i02 | random-n10 | 58.1 | ring | 1 | second | 0.300 |
| random-n10-i14 | random-n10 | 51.9 | ring | 2 | second | 0.204 |

汇总：40 负样本 **15 个 grade=best**；5 个分数高于人工下界 65.4；最高 87.7。

**供 default+jacky 拍板的重标素材**：soil-erosion（0 交叉 grade=best，kept 特征
距最近人工锚仅 0.086——模型视野里与人手锚几乎同一个点）与 fishing-collapse
（0 交叉 best）是"引擎输出确实质量高而模型分不上去"的实证；若口径认为此类输出
不应作负样本，v1/v2 的 hub separation/AUC 需重算。**本卡不改标注，只列清单。**

## 6. 诊断六：扰动剂量-响应（18 锚点 × 4 级累积扰动）

剂量定义（确定性，无 RNG；L1→L4 累积）：L1 每节点 ±3px id-hash 抖动 → L2 交换
两个最小序 id 位置 → L3 前半节点绕画布中心镜像（破边镜像）→ L4 奇数节点
(+7,+5)px 挪离对齐线。
存活性门（几何门，剔除并计数）：min card gap ≥16px 且零真压卡
（`metrics.certificate` 直线段口径）。

- 门剔除计数：L0=3，L1=3，L2=3，**L3=13，L4=13**（镜像反射大量造成卡重叠/压线，
  被门如实剔除）；3 锚点在原始布局就不过门（fan-d12、fan-d17、random-n10-i05
  手工导出），整条剂量线不可测，如实计为 gate-blocked。
- **分辨率分类（15 个可测锚点）：严格单调下降 0；全平坦（无分辨率）5；混有上升步
  10。**

| 锚点（可测，节选） | L0→…→L4 分数 | 分类 |
|---|---|---|
| brand-flywheel | 81.3 全程恒 | 无分辨率 |
| comb-supply-demand | 81.3 全程恒 | 无分辨率 |
| classic-cld（两个 drag） | 81.3 恒至 L2，L3+ 被门剔 | 无分辨率 |
| coupled-underinvestment | 81.3 恒至 L2，L3+ 被门剔 | 无分辨率 |
| nonplanar-credit | 81.3 → 81.3 → 12.8 → 2.6 → 2.8 | 混合（L4 反升 +0.2；大跌幅来自路由翻转 hub→ring 换模型，非桶内梯度） |
| nonplanar-inventory | 97.8 → 97.8 → 95.3 → 12.1 → 12.1 | 混合 |
| nested-capacity | 84.1 → **84.2**（抖动反升）→ 33.4 → 剔 | 混合 |
| i11-a / i11-b | 96.9→…；95.8 → **95.9** → 77.5 → 79.5 | 混合 |

**两个诚实的限定**：
1. 剂量-容差：alignment 容差 = `ALIGN_TOL_FRAC(0.04) × min(画布边)` ≈ 22px，
   L4 挪离量 (7,5)px 远小于容差 → kept 特征在全部剂量内保持 1.0/0.0 不动。"无
   分辨率"结论限定在本卡剂量内；更强的挪离剂量是后续卡问题（改剂量参数表即可复算）。
2. 大幅度分数变化全部来自**路由翻转**（换 shape 模型），桶内不存在连续梯度——
   这正是"该区域无分辨率"的 fail-visible 证据：评分器对保持路由不翻转的布局恶化
   完全不响应，对翻转则跳变。

## 7. 口径修正影响：v1/v2 哪些数字需要换口径重读

若"塌缩可能根本不是缺陷"成立（本次证据支持），以下数字应按新口径重读：

1. **hub separation −13.9（v2）**：被 fan-d12 单对支配（它无同图候选、不可比）。
   应改报：拓扑内 delta 分布（§4.2）+ 交叉对计数（3，全含 fan-d12）。
2. **hub AUC 0.9855 / ring AUC**：正侧只有 2 个向量，数字本质是负样本侧方差 +
   一个离群正锚；不反映"人工 vs 引擎"分辨力。同图打平读数（4/12）才是漏斗口径。
3. **human lower bound 65.4**：= fan-d12 单样本分，不是"人工下界"，是"最弱离群锚"。
4. **8/9 塌缩本身**：不是模型失灵，是 kept 特征输入恒等的准确反映；应与"漏斗同图
   排序在塌缩区不可用（4/12 打平 + 评分器/交付 5/12 分歧）"一起披露。
5. **hub test-retest delta=0**：构造性结果（v2 已披露），本次口径确认。
6. **负样本库口径**：15/40 grade=best（含 soil-erosion / fishing-collapse 这类
   0 交叉且 kept 距人工锚 <0.31 的输出）是否仍作负样本——待 jacky/default 拍板，
   拍板前一切 sep/AUC 数字保持现口径不动。

## 8. 红线自查

- 评分器代码 / 模型 / 校准产物 / 阈值 / 基线：零改动（`git status` 仅新增诊断脚本、
  本报告、诊断 JSON）；负样本库只读未写；确定性双跑字节一致；分支推回不并 main。
- 诊断自身新增口径（证书代理 96×44、直线段）均已在 §口径声明 标注，不回写任何
  正式产物。
