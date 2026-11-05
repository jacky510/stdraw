# benchmarks — stdraw 基准集与基线对比

语料：`corpus/classic/`（19 张经典 CLD，lint 全绿）+ `corpus/random/`（80 张固定种子稀疏图，n∈{10,20,30,50}×20）。清单：`manifest.json`。
运行：`tools/run_all.py`（可重入，预算与 DNF 协议见 `REPORT.md §2`）。
聚合：`tools/collect.py` → `REPORT.md`（逐图大表）。

## 摘要表（classic 均值；随机族按 n 聚合见 REPORT §4）

| 工具 | 交叉 | 框压线 | 净距违规 | CV | 行对齐 | 耗时s |
|---|---|---|---|---|---|---|
| stdraw·ortho(构造法) | — | — | — | — | — | — |
| stdraw·auto(WS3布线) | — | — | — | — | — | — |
| stdraw·auto+WS2(精确层) | — | — | — | — | — | — |
| Graphviz dot | — | — | — | — | — | — |
| Graphviz neato | — | — | — | — | — | — |
| Graphviz sfdp | — | — | — | — | — | — |
| ELK layered | — | — | — | — | — | — |

诚实边界：随机族 n≥20 上 stdraw auto-v2 当前 DNF（见 REPORT §5 瓶颈定位）；OGDF 未同题运行（§6）。「最好」主张措辞以 REPORT §8 为准，经 default 复核后才写入仓库 README。

