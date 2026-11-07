# benchmarks/manual — jacky 手拉样本留档

本目录存 **jacky 亲手拖拽导出的手动布局**（ground truth），作为排布形态
「结构等价」验收的基准。坐标不要求逐 px 复刻，但引擎自动排布的角色归组
（纵柱 / 中线行 / 翼列 / 落单位）与相对几何规律必须与样本一致。

## classic-cld-manual-layout.json

- **来源**：jacky 在 stdraw demo-2d 交互页手动拖拽后「导出布局」产物
  （Kanban 卡 ref-scrubbed 附件，2026-11-06）。
- **图**：`classic-cld-growth-and-burden`（增长极限×转嫁负担，8 节点）。
- **viewBox**：856×760。
- **结构规律**（回归测试 `tests/test_layout_modes.py::TestSpineWingManualEquivalence`
  以本文件为准自动推导角色归组）：
  - 端点纵列：adopters(413,214) / rate(412,535) —— x 同列 1px；
  - 中层横排：word(308,368) / potential(112,368) / crowding(547,369) —— 同行 ±1px；
  - 右翼同列：quickfix(741,289) / sideeffect(747,453) —— x 同列 6px；
  - 落单中下位：fundamental(594,533)（与 rate 同行带）。
- **副本纪律**：本文件是 ground truth 正本（仓库内），与引擎行为挂钩的
  回归测试只读本文件推导，不在测试里写坐标副本。

## 历史事件（防再犯）

v0.7.1（ref-scrubbed）引擎侧 spine-wing 已落地且结构正确，但
`demos/classic-cld-2d.html` 与 `docs/gallery/*.png` 未随引擎重渲染，
jacky 眼验看到的是旧 ring-construct 渲染而被误判「结构不一致」
（返修卡 ref-scrubbed，v0.7.2）。防再犯门：`tests/ci_checks.py` 交付件
新鲜度检查——demo-2d.html 与当前引擎重渲染逐字节比对。
