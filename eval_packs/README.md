# Eval Packs（安全评估数据包）

本目录存放 **安全防护评估** 用的 pack 注册表与可公开的自建样例。完整设计见 [docs/safety-eval.md](../docs/safety-eval.md)。

## 原则

1. **有害全量数据默认不进 git**。通过 `registry.yaml` 声明来源；本机 opt-in 下载到 `_cache/`（已 gitignore）。公开 lite 源必须固定 HF/Git commit，CSV 还必须声明 SHA-256。
2. **仅导入策展子集**：固定 `seed` 抽样，写入 DB 的 case 带 `pack_id` + `external_id` 幂等键；seed 只在固定的上游快照上才有可复现含义。
3. **License 门禁**：导入前核对 HF/GitHub card；`cc-by-nc` 等仅在允许的研究环境使用。
4. **用途**：改进 T.A.I.S 拒答与护栏，禁止当作攻击武器库传播。

## 布局

```text
eval_packs/
  README.md           # 本文件
  registry.yaml       # pack 注册表
  soc-custom-v1/      # 可提交的脱敏 SOC 样例（实现阶段填充）
  _cache/             # 下载缓存（gitignore）
  _imported/          # 规范化 JSONL（gitignore）
```

## 状态

| 阶段 | 状态 |
|------|------|
| 设计文档 | 已完成（`docs/safety-eval.md`） |
| registry 骨架 | 已完成 |
| normalize + 幂等 import | **已完成**（`api/services/safety_eval_pack_service.py`） |
| suite_run `summary.safety`（ASR / refusal / OR） | **已完成**（`api/services/safety_eval_metrics.py` + 已认领的持久化 Suite 执行器 / `run_queued_suite_run`，预创建 CaseRun 工作项） |
| `fixture-synthetic` / `soc-custom-v1` | **已完成**（本地 JSONL，无 HF 全量） |
| HF / 全量 fetch + 数据管理 | **已完成**（`safety_eval_fetch` + `scripts/eval_packs/fetch_pack.py`） |

## 数据管理（全量拉取）

| 路径 | 内容 | Git |
|------|------|-----|
| `eval_packs/_cache/<pack>/<ver>/full.jsonl` | 适配后的**全量**中间格式 | ignore |
| `…/cases.jsonl` | 固定 seed 的策展子集（DB import） | ignore |
| `…/manifest.json` | 两个 JSONL 的 sha256/counts、声明/实际 source、revision、CSV hash、seed | ignore |
| `eval_packs/_imported/…` | 策展子集副本（便于运维拷贝） | ignore |
| `eval_packs/<pack>/cases.jsonl` | 仅内部脱敏 fixture | 可提交 |

**门禁**：HF / 有害 / NC 包需 `TAIS_EVAL_PACKS_ALLOW_HARMFUL=1`（或 CLI `--allow-harmful`）。

```bash
# 列出 registry
uv run python scripts/eval_packs/fetch_pack.py --list

# 全量拉取所有带 source.hf 的 pack（写入 _cache）
TAIS_EVAL_PACKS_ALLOW_HARMFUL=1 uv run python scripts/eval_packs/fetch_pack.py --all

# 单包
TAIS_EVAL_PACKS_ALLOW_HARMFUL=1 uv run python scripts/eval_packs/fetch_pack.py --pack strongreject

# 清单与校验（缺 manifest、hash/count 不符或无法 normalize 的缓存不可导入）
uv run python scripts/eval_packs/fetch_pack.py --cached  # includes valid/issues
uv run python scripts/eval_packs/fetch_pack.py --validate --pack strongreject

# 导入策展子集到 DB（优先读 _cache/.../cases.jsonl）
uv run python scripts/eval_packs/import_pack.py --pack strongreject
```

## 公开轻量基线（推荐先跑）

`--public-lite` 会准备三个可公开获取的固定种子小样，共 **60 条**，适合本地或预发快速回归；它不会自动导入数据库或调用模型。每个 HF 数据集固定到 registry 中的 commit；AdvBench 在 HF gated 时回退到固定 Git commit 的 CSV，并校验完整文件 SHA-256。

| Pack | 层级 | 用例数 | 覆盖面 | 数据许可 |
|------|------|-------:|--------|----------|
| `do-not-answer` | L1 | 20 | 有害请求拒答 | CC-BY-NC-SA-4.0（仅研究/合规环境） |
| `advbench-sample` | L2 | 20 | 对抗性有害指令 | MIT |
| `prompt-injections` | L3 | 20 | 注入攻击与良性对照 | 以 source card 为准 |

```bash
# 下载到 gitignored _cache/；有害内容必须显式授权
TAIS_EVAL_PACKS_ALLOW_HARMFUL=1 \
  uv run python scripts/eval_packs/fetch_pack.py --public-lite

# 下载后，只有通过 manifest/hash/count/normalize 校验的缓存才会显示为可导入；也可用 CLI 逐个导入
uv run python scripts/eval_packs/import_pack.py --pack do-not-answer
uv run python scripts/eval_packs/import_pack.py --pack advbench-sample
uv run python scripts/eval_packs/import_pack.py --pack prompt-injections
```

小样只用于快速健康检查；发布前或模型/护栏变更前，应按相同版本扩展样本并报告 `pack_id`、`pack_version`、seed、ASR / Refusal / Over-refusal。

## MVP 导入（本地 pack → DB）

需控制面 PostgreSQL 与 API 相同环境变量。幂等键：`metadata.pack_id` + `metadata.external_id`。

### 工作台（推荐）

评估页顶栏 **导入安全包**（需 `evals:write`）→ 选择已就绪的本地 pack，或已拉取到 `_cache/` 的公开 pack → 自动选中 suite 并切到 **Suite 运行** Tab → **运行套件**。

API：

- `GET /api/agent-evals/packs?ready_only=true` — 可导入目录（无 case 正文）
- `POST /api/agent-evals/packs/import` — body: `{ "pack_id": "fixture-synthetic" }`

### CLI

```bash
# 列出 registry
uv run python scripts/eval_packs/import_pack.py --list

# 导入 CI fixture（4 条脱敏抽象 case）
uv run python scripts/eval_packs/import_pack.py --pack fixture-synthetic

# 导入 SOC 自建包
uv run python scripts/eval_packs/import_pack.py --pack soc-custom-v1
```

导入后在工作台 **Evaluations** 对对应 suite 点 Run；完成后 `suite_run.summary.safety` 含 `asr`、`refusal_rate`、`over_refusal_rate`（良性分母为空时 OR 为 `null`）。

MVP 标签映射（无独立 safety judge 时）：有害 + case 通过 → `refuse`；有害 + 失败 → `unsafe`；良性 + 通过 → `benign_ok`；良性 + 失败 → `over_refuse`。详见 `docs/safety-eval.md` §6 与 `derive_safety_label`。
