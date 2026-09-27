# Davina-ChemAgent｜有机合成–分子对接智能工作台

公网演示（部署后）：**https://davina-chemagent.streamlit.app/**

面向化学研究里「查分子 → 预测产物 → 找文献/谱图 → 对接靶点 → 出图」工具链割裂的问题，参考 ChemCrow 的 Tool-using Agent 思路，把多引擎预测、化学工具与对接分析编排成可切换流水线。

## 功能

| 模块 | 说明 |
|------|------|
| 反应预测 | Agnes / GPT / DeepSeek（OpenAI 兼容）· 可选 IBM RXN · 本机可跑 ReactionT5 |
| 分子库 | PubChem / ChEMBL |
| 命名 / 文献 / NMR | 中英 IUPAC、文献检索入口、¹H/¹³C 预测 |
| 蛋白对接 | PDB / AlphaFold → Meeko → AutoDock Vina（含人源 TYR 双铜与文献盒子） |
| 可视化 | 口袋残基 / 氢键键长；本机可 PyMOL 出图 |

## Streamlit Cloud 部署（公网展示）

> **ReactionT5（约 0.2B，磁盘 ~760MB）请勿指望在 Streamlit Community Cloud 运行。**  
> 云端免费档 RAM 约 0.7–2.7GB；`torch + transformers + 权重` 加载常需 1.5–3GB+，会 OOM / 重启。  
> **仓库故意不上传 HF 权重**（也超过 GitHub 单文件 100MB 建议上限）。  
> **公网演示请用侧边栏「大模型产物估计」（Agnes / GPT 等）**；本机可另装 torch 离线跑 ReactionT5。

1. 打开 [Streamlit Cloud](https://share.streamlit.io/) → **New app**
2. Repository：`Davina-Dhh/Davina-ChemAgent` · Branch：`main` · Main file：`app.py`
3. （可选）**Secrets**：仓库已预置演示用 Agnes Key，云端一般**不用再填**。若要换自己的 Key，再在 App settings → Secrets 覆盖即可。

```toml
# 仅在想覆盖仓库默认 Key 时填写
OPENAI_API_KEY = "你的_Key"
OPENAI_API_BASE = "https://apihub.agnes-ai.com/v1"
CHEMCROW_MODEL = "agnes-2.5-flash"
```

4. Deploy → 自定义子域 `davina-chemagent`（若已占用则在设置里改）

## 本机运行

```powershell
cd Davina-ChemAgent
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
# 可选：对接可视化 / ReactionT5
.\.venv\Scripts\pip install -r requirements-dock.txt
.\.venv\Scripts\pip install torch transformers sentencepiece
.\.venv\Scripts\streamlit run app.py --server.port 8502
```

复制 `.env.example` → `.env` 填入 Key。

## 技术栈

- **编排**：多引擎路由（LLM / ReactionT5 / IBM RXN）+ 工具链（RDKit、PubChem、PDB/AlphaFold、Vina、Meeko）
- **LLM**：OpenAI 兼容网关（默认 Agnes `agnes-2.5-flash`）
- **前端**：Streamlit
- **对接**：AutoDock Vina 1.2.5（Win/Linux 自动下载）

## 说明

结果仅供实验规划参考，需实验验证。勿将 `.env` / Secrets 提交到公开仓库。
