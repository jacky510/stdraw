# 消费侧确定性复现环境（byte-pinned artifacts 正解配方）

适用：消费方仓以 `STDRAW_PIN` / `STDRAW_PIN_COMMIT` 双锁对生成产物做**字节级契约**
（现状唯一消费方：investment-advisor `tools/hdd_chain_layout.py` →
layout.json / certificate.json / full.html 三产物）。

## 硬规则：禁止用本仓 `.venv` 做消费侧重生成

`C:/Users/jacky/Projects/stdraw/.venv` 是**开发专用环境**，三重性质决定它必然漂移：

1. **editable 安装指向本仓工作树**——任何未提交 hunk 都实时改变消费侧输出；
   且开发推进后树 HEAD ≠ PIN 提交，PIN 版本串检查照样能过（提交级锁形同虚设）。
2. 可能缺 `measure` extra（pillow）→ textmetrics 走解析式估宽回退；
3. 可能缺 `solver` extra（ortools）→ `solver_available: false`（engine 恒 construct）。

漂移特征 = **无报错、产物照出**，只能靠哈希对拍发现（实测指纹见下节）。

## 正解配方（2026-11-13 从零重建实测通过）

```bash
SCRATCH=<你的scratch目录>          # 例: ~/AppData/Local/hermes/profiles/<bot>/cache/scratch/stdraw-pin-verify
git -C C:/Users/jacky/Projects/stdraw archive --format=tar.gz \
    -o "$SCRATCH/stdraw-<pin-commit>.tar.gz" <pin-commit>
cd "$SCRATCH"
uv venv stdraw-pin-venv --python 3.12
uv pip install --python stdraw-pin-venv/Scripts/python.exe \
    stdraw-<pin-commit>.tar.gz pillow ortools
```

- `pillow` = `measure` extra（真字体框宽测量）；`ortools` = `solver` extra
  （auto-v2 CP-SAT 放置精化）。两个都装 = 与冻结产物生成环境同特征。
- 每次 PIN 升版都要**重新 archive + 重建 venv**，不要复用旧 venv 换包。

## 重生成前三条验证（全过才动手）

```bash
stdraw-pin-venv/Scripts/python.exe -c "import stdraw; print(stdraw.__file__, stdraw.__version__)"
stdraw-pin-venv/Scripts/python.exe -c "from stdraw.layout_auto import _has_solver; import PIL; print(_has_solver(), PIL.__version__)"
```

判据：① `stdraw.__file__` 落在该 venv 的 `site-packages` 内（出现
`Projects\stdraw\stdraw\__init__.py` 即 editable 污染，立即停）；
② 版本串 == PIN 版本；③ `_has_solver()` 为 True 且 PIL 可导入。

## 漂移指纹（历史实测，advisorbot t_b0f13747 2026-11-12）

| 环境缺失 | 症状 |
|---|---|
| 无 pillow | textmetrics 解析式估宽回退：viewBox 1072→1064、stx 卡宽 130→128、净距 22.4→22.2 |
| 无 ortools | certificate `solver_available: true→false` |

完整重生成命令与哈希对拍口径（layout 4f0087aa / cert 12a2b3a2）的正本指针：
advisorbot 技能 `8777-v2-page-build`「P5 链图深色档返修」节
（`C:/Users/jacky/AppData/Local/hermes/profiles/advisorbot/skills/software-development/8777-v2-page-build/`，不在本仓存副本）。
