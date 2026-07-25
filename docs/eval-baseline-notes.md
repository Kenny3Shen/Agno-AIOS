# 安全评估基线记录

- 更新时间：2026-07-22 01:01 UTC
- 用途：预发/本地跑通后的参考数字，非论文横比。

## fixture-synthetic（本地实跑）

- suite_run: `a04661ea8c0d4ef9988ec89331de3e26`
- status: **passed**
- passed/failed: 4/0
- ASR: 0.0
- Refusal: 1.0
- Over-refusal: 0.0
- Guardrail blocked: 0
- Profile: full
- Judge: `agent_as_judge:inline+model:default`

## guardrail-regression-v1

- 已可通过评估页 **导入安全包** 导入（3 cases，期望护栏硬拦截）。
- 跑完后关注 `n_guardrail_blocked` 与 ASR 分母是否仍排除护栏桶。

## UI P0（本迭代）

- Suite 运行：勾选 1～2 行做 ASR/拒答/误拒/护栏 **diff**（绿好红差）。
- 用例：有害/未知 input 默认脱敏，可「显示全文」。
