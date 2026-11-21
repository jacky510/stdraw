# Pairwise 偏好标注 · 2026-11-21 会话（PROVENANCE）

数据所有权：jacky。30 题（24 主测 + 6 重测）全部作答，文件字节未改。
会话：查看器 LCG 可复现编排（来源盲选：人工/引擎/模板不可见）；model_version 记录在每条 item。
分布：a 8 / b 9 / 都好 7 / 都差 6；覆盖 5 图（brand-flywheel / comb / nonplanar-credit / coupled-underinvestment / classic-cld）。
重测一致率：5/6（唯一分歧=comb 首测「都好」→重测偏 b，平局漂移非硬矛盾）；个体噪声基线与同图多拖 Δ≈1.1 同量级。
用途：M0/M1/M2 偏好排序对照实验的人工标签（Phase 3 首轮，ChatGPT 建议的 20~24 对初始预算）。
口径：「都好」不进训练对（进 ε 标定分析）；「都差」作候选池质量预警；左右互换已在分析侧换算。
