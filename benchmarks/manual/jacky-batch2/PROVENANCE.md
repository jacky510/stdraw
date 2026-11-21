# batch-2 人工锚点来源记录（PROVENANCE）

数据所有权：jacky。八份均为 jacky 在 demo-2d 查看器上对引擎初稿手工微调拖拽后导出的 manual-layout（2026-11-21 收数）。
转存说明：文件由 default 从 jacky Downloads 原样复制（字节未改）。

## 样本清单

| 文件 | 拓扑族 | n | 导出边数 | 备注 |
|---|---|---|---|---|
| nested-capacity | 嵌套环 | 8 | 2 | |
| nested-learning | 嵌套环 | 8 | 4 | 1 条 straight |
| retest-classic-cld | hub（重测） | 8 | 0 | classic-cld 第二次拖拽，纯节点微调 → 同图重测对（Test-Retest） |
| coupled-underinvestment | 多环耦合 | 10 | 6 | |
| comb-supply-demand | 梳状 | 8 | 4 | |
| bowtie-wage-price | 领结 | 8 | 8 | 全部边带自定义设置 |
| nonplanar-credit | 非平面 | 9 | 9 | 4 straight + 1 arc，7 边带锚点 |
| nonplanar-inventory | 非平面 | 9 | 12 | 2 arc + 1 free，全边带锚点 |

## 口径说明

- 导出为「部分边集+全量坐标」：buildLayout 只写被用户改过的边（auto/waypoints/userAnchor 任一触发）；完整边集以 benchmarks/manual/jacky-batch2/sources/*.cld 为准，读取方必须按图源补边（merge_layout_edges 已按此实现）。
- 边样式与锚点（straight/arc/free、上下左右锚）为本批新增数据维度：jacky 按个人审美设置，供锚点偏好分析。
- chain-monetary / chain-supply 两图 jacky 判定太简单、无需手工拖拽，未收——链族暂无人工锚点，评分器 hub 族权重不覆盖链型特例。
- 用途：aesthetic_score v2 重校准人工锚点（10 份旧锚点 + 8 份本批 = 18 份）；retest-classic-cld 与 classic-cld(11-06)、i05 双拖构成两组同图重测对。
- 图源与认证初稿：benchmarks/manual/jacky-batch2/{sources,drafts}/（来自批次-2 准备卡合并）。
