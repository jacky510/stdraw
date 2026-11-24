# 人工审美采样第二批 · 采样协议（jacky-batch2）

状态：准备就绪待采样。目的：为审美模型 v2 校准补充拓扑族人工锚点
（第一批 10 份锚点的族缺口 = 链 / 嵌套环 / 非平面 / 领结梳状）。
图源清单与会话入口见 `benchmarks/manual/jacky-batch2/index.html`。

## 0. 采样对象（10 图，族覆盖）

| # | 图 | 族 | n/e | 预期 |
|---|---|---|---|---|
| 1 | chain-monetary | 链 | 7/6 | 0 交叉 |
| 2 | chain-supply | 链 | 6/5 | 0 交叉 |
| 3 | nested-learning | 嵌套环 | 8/9 | 0 交叉 |
| 4 | nested-capacity | 嵌套环 | 8/10 | 0 交叉 |
| 5 | nonplanar-inventory | 非平面（K3,3 细分） | 9/12 | 最小交叉 = 1（crossed-certified） |
| 6 | nonplanar-credit | 非平面（K5 细分） | 9/14 | 最小交叉 = 1 |
| 7 | bowtie-wage-price | 领结（双环共点） | 8/9 | 0 交叉 |
| 8 | comb-supply-demand | 梳（双侧） | 8/9 | 0 交叉 |
| 9 | coupled-underinvestment | 多环耦合 | 10/12 | 0 交叉 |
| 10 | retest-classic-cld | 重测（二拖） | 8/13 | 0 交叉（spine-wing）|

图源 `.cld` 在 `benchmarks/manual/jacky-batch2/sources/`（重测图用仓内
既有 `examples/classic-cld-growth-and-burden.cld`，不复制）。

## 1. 每图导出两个文件（成对命名）

对每一图：

1. **拖拽前初稿**（`<graph>-draft.json`）：由准备卡预存，落
   `benchmarks/manual/jacky-batch2/`。它是现行引擎 auto-v2 布局的等价
   导出（与「Export layout」同 schema：`nodes` + `viewBox`，样式全默认），
   jacky 不需要动它，只作偏好对的 A 侧。
2. **拖拽后导出**（`<graph>-jacky.json`）：jacky 在该图的 demo-2d 页面
   拖完之后，点右上角 **Export layout** 按钮，浏览器下载的文件改名成
   `<graph>-jacky.json`，放进同一目录。

两个文件构成一张偏好对：同图、同拓扑、两种画法。

## 2. 锚点与边样式：随意设（这是新增数据维度）

本批不要求「标准答案」，**你觉得怎么好看就怎么摆**：

- **节点**：直接拖卡片。
- **边样式**：双击一条边循环切换 `auto → straight → arc → free`；
  `free` 后拖边可插入折点手柄（每条边最多 3 个折点），拖折点即钉住该边。
- **边锚点**：鼠标悬停在某张卡片上会显示它的 16 个标准锚点
  （n / s / e / w / 四角 / 黄金分割点等）；点击一个可见锚点，就把它
  显式指定给最近的那条连边端点（导出为 `edges[].anchors.src/dst`，
  形如 `n` / `se` / `g1` 等）。同侧多条边的锚点想怎么分组就怎么点。
- 弧线的弯向/弧度也可以通过锚点+样式的组合随意调。

## 3. 「都不满意」也如实导出

某一图无论怎么拖都不满意时：**照样点 Export layout 导出**，按
`<graph>-jacky.json` 命名，并在交付时（聊天/台账）注明「该图均不满意」；
也可以额外存一份 `<graph>-jacky-none.txt` 写一两句不满意的原因。
如实标注的负样本对校准同样有价值，不要因为不满意就不导出。

## 4. 时间预算

每图预计 **5~10 分钟**（拖节点 + 调几条边的样式/锚点 + 导出），
10 图合计约 1~1.5 小时，可分多次坐完成，顺序不限。

## 5. 收尾与回放

- jacky 的导出收集齐后统一放入 `benchmarks/manual/jacky-batch2/`，
  与 `<graph>-draft.json` 并排。
- 每份 `<graph>-jacky.json` 可用 `--from-layout` 重放复核：
  `stdraw layout <sources>/<graph>.cld --outdir <检查目录> --from-layout <graph>-jacky.json`
  （人工口径下自动管线的结构门读 N/A，其余门如实评级，见
  docs/grading-contract.md §3.1）。
- 后续消费：偏好对进入人工锚点库（第一批先例 =
  `benchmarks/manual/`，PROVENANCE 记来源与日期）。
