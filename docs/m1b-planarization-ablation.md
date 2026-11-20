# M1-B 消融报告：平面化候选源（planarized source）

状态：M1-B 交付物。分支 `p1/m1b-planar-source`；基线 = M1-A（main 合并态，
5da2257）。方案依据：优化方案综合稿 v1.3.1 §7 Phase 1 M1-B + §15(3)。
本报告不含内部卡号（仓泄漏门禁口径）；原始输出见 kanban/evidence/ 对应
证据目录（不入库），复跑命令见文末。

## 1. 新增源口径（实现拍板记录）

`stdraw/candidate_planar.py`（构造核）+ `candidate_sources.py`（接入）：
删边集全枚举（|D|≤2，**主环边保护**——loop 模型 primary loop 的边永不进删
集；枚举带 (size, 边序) 确定性序）→ 嵌入×外面选择（G−D 上复用
`planar.py` 机器：sorted 插入的 check_planarity 旋转系统 + `faces_of` 面枚举
+ Even-Tarjan st 编号 + 可视性表示 + 行压缩装箱；外面选择 = 每条真实边的
双向 (s,t) 枚举，覆盖嵌入任一镜像的全部面）→ 面约束画法（全整型 2px 网格
坐标）→ 双变体插回（A = 插回交叉数最小 + 交叉对描述字典序；
B = J_cross=Σw(c) 最小，w=2 若交叉涉及主环边否则 1——§15(3) 的
「平面面均匀度仅作平面化候选附加指标」口径同样遵守：面信息只进 metadata，
零评分权）。

**零评分权**：全部完成的变体构造都进统一管线（每删除集最多 2 个候选
A/B，构造相同的 B 并入 A 并打 `variant_b_same_construction` 标注）；
管道三级筛选照常裁决。静态 import lint 扩展覆盖新模块
（tests/test_candidate_planar.py）。

**确定性合同**：sorted 插入 + 全排序迭代；实测 PYTHONHASHSEED
0/1/2/12345 四种子下 K5−e / K3,3−e / Petersen 旋转系统逐字节一致；
双向 (s,t) 枚举对嵌入镜像不变 ⇒ 候选集不依赖探针返回哪个镜像。
同图双跑字节一致（测试 + 消融 runner 双树实测）。

**预算（预注册资源帽，非质量筛选）**：`PLANAR_MAX_DELETE=2`、
`PLANAR_MAX_DELETION_SETS=4`、`PLANAR_MAX_ST_PER_SET=12`；编排器每源
配额 2（M1-A 既有口径）不变——实测每触发图 emitted 4、kept 2。

**触发规则（纯拓扑）**：核心子图非平面才启用（`core_is_planar` 探针）；
平面图 `disabled_by_rule`，n>20 沿用模板统一节点帽。

## 2. 管线作用域变化（M1-B 契约变更）

M1-A 的 L1 短路（`planarized-l1-incumbent`）退役：候选池现进入 L1
平面化作用域运行。**L1 阶梯的交付楼层语义不变**——守卫的 incumbent 侧
就是 L1 见证图，候选仅在交付证书口径不劣于楼层时才替换交付
（fail-closed 一致性断言保留）。非平面图 provenance 增注
`incumbent_planarization_mode`；平面图 provenance 不增键（负例保护）。
对应测试 `test_planarized_l1_scope_pool_runs_with_l1_floor`（替代原
L1 短路用例）。

## 3. 长尾验收集

`benchmarks/corpus/longtail/`：12 图（链 3 / 星 3 / 非平面 3 / 混合 3，
全部 n≤10，族标签在首行注释；K₅ / K₃,₃ / Petersen 为非平面成员，构造依据
见该目录 README.md）。Phase 0 空族（链/星/非平面 0 覆盖）由此补齐。

## 4. 消融结果（15 图 = 12 长尾 + 3 既有负例夹具）

方法：双 checkout（main=M1-A / 分支=M1-B）各跑 candidate-v1 + auto-v2，
runner = `benchmarks/tools/ablate_m1b.py`，原始输出
`ablation-raw.json`（证据目录）。

### 4.1 触发图（3/3 非平面成员触发，各 emitted 4 / kept 2）

| 图 | M1-A 交付 | M1-B 交付 | 交叉数 M1-A→M1-B | 守卫元组（候选 vs 楼层） |
|---|---|---|---|---|
| longtail-nonplanar-k5 | L1 incumbent | **候选交付** | 1 → 1（=cr(K₅) 理论最优） | spacing_cv 0.384→**0.0**，其余分量不劣 |
| longtail-nonplanar-k33 | L1 incumbent | **候选交付** | 1 → 1（=cr(K₃,₃) 理论最优） | anchor 违例 18→**1** 且 cv 0.56→**0.0** |
| longtail-nonplanar-petersen | L1 incumbent | 楼层回退（守卫拦截：geo fails 1>0） | 2 → 2（=cr(Petersen)） | 候选被诚实拒绝，楼层语义生效 |

**正增益证明（验收项）**：K₅ 与 K₃,₃ 的交付候选在交付证书守卫元组上
**严格优于** M1-A 的 L1 楼层（K₅：cv 0.384→0.0；K₃,₃：anchor 违例 18→1
且 cv 0.56→0.0），且交叉数保持理论最优；池覆盖从「仅 incumbent」变为
「+2 平面化候选/图」。Petersen 展示失败路径：候选劣于楼层时守卫拦截、
L1 见证图原样交付——不劣于守卫无一回归。

### 4.2 非触发图（12 = 9 平面长尾 + 3 负例夹具）

| 保护口径 | 结果 |
|---|---|
| auto-v2 配方 layout 逐字节（15/15 全图） | **15/15 IDENTICAL** |
| candidate-v1 交付坐标逐字节（12 非触发图） | **12/12 IDENTICAL** |
| candidate-v1 全 layout 字节 | 非触发图按设计不同：provenance 诚实记录新源的 `disabled_by_rule` 行（与 M1-A 验收口径同类） |

## 5. 复跑命令

```bash
# 双树消融（原始输出落 --outdir）
python benchmarks/tools/ablate_m1b.py \
  --m1a-root <M1-A checkout> --m1b-root <本分支 checkout> \
  --outdir <evidence dir> --python <interpreter>

# 定向测试（27 项新增/改约）
python -m pytest tests/test_candidate_planar.py tests/test_candidate_pool.py -q

# 全量铁门
python -m pytest tests/ -q && python tests/ci_checks.py
```

## 6. 已知边界（诚实声明）

- 每源配额 2 使 4 个 emitted 候选只保留前 2 个删除集的变体（结构配额、
  确定序，非质量筛选）——配额放宽留给 M2 拍板。
- 删除集帽 4 / 每集构造帽 12：n≤20 大图上可能截断枚举（帽是预注册资源
  规则，metadata 记录 `deletion_sets_capped` / `st_per_set_capped`）。
- 旋转系统跨进程稳定性实测覆盖 K5−e / K3,3−e / Petersen 族（3 连通平面
  子图嵌入唯一镜像定理族）；含 2-分离嵌入自由度的图未逐一实测——同进程
  双跑一致性由测试保证，跨进程字节一致性在这类图上列为待实测边界。
- variant B 在实测 3 图上均与 A 同构造（可视性表示间距大，直线插回零
  交叉）——B 键的判别力目前只在单元层验证（主环权重 2/1 分档），
  真实分化样本留待 M2 语料扩充。

## 7. 验证状态（实测）

- 全量 pytest（分支 @ 语言门修复提交）：**341 passed, 1 skipped**
  （3236.7 s；1 skip 为既有跳过项；与兄弟卡的并发 pytest 隔离 TMPDIR
  后并行跑，无固定名互踩）。
- ci_checks 全量（2445.3 s）：除语言政策门外**全绿**（ortho 冻结字节
  回归 / auto 硬门 / 随机密集 / 崩溃回归 / 平面化 L1 goldens / exact /
  manual loop / ring / H2 19 图 / 新鲜度 / D0 / 内漏门全部 OK）。
- 语言政策门：本分支原有 1 处新增违例（candidate_sources.py 中文注释）
  已修复为英文；**剩余 37 处命中全部为已提交 main 的既有违例**
  （36 处 benchmarks/REPORT.md + 1 处 benchmarks/tools/gen_v082_report_
  section.py，来自上游 REPORT 重测卡的合入；双树违例集 diff 为空集新增）。
  上游修复建议另立卡处理（REPORT.md 为已发布数字面，本卡不代改）。
