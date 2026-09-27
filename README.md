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

> **ReactionT5 不能直接装进 Streamlit Community Cloud**（权重 ~800MB，加载常需 1.5–3GB+ RAM，会 OOM）。  
> 大模型估算产物质量通常明显弱于 ReactionT5。  
> **推荐：本机跑 ReactionT5 API，用隧道暴露，Cloud 远程调用（质量与本机一致）。**

### Cloud + 本机 ReactionT5（推荐）

1. **本机**安装依赖并启动服务（首次会下载/加载模型，之后用缓存）：

```powershell
cd Davina-ChemAgent
.\.venv\Scripts\pip install -r requirements-t5-server.txt
.\.venv\Scripts\pip install torch transformers sentencepiece
set REACTIONT5_API_TOKEN=换成一串随机密码
.\start_reactiont5_server.bat
```

2. **另开终端**暴露公网（任选）：

```powershell
# Cloudflare 快速隧道（免费，无需注册也可试）
cloudflared tunnel --url http://127.0.0.1:8765

# 或 ngrok
ngrok http 8765
```

3. 把隧道给出的 `https://....` 填进 **Streamlit Cloud → Secrets**（或本地侧栏）：

```toml
REACTIONT5_API_URL = "https://xxxx.trycloudflare.com"
REACTIONT5_API_TOKEN = "与本机一致的随机密码"
```

### 电脑重启后怎么恢复公网？

免费 `cloudflared tunnel --url ...` **每次重启公网地址都会变**，所以要做三件事：

1. 双击运行 `restore_t5_public.bat`（会拉起本机 8765 服务）
2. **另开终端**执行：`cloudflared tunnel --url http://127.0.0.1:8765`
3. 把新的 `https://...` 更新到 **Streamlit Cloud → Secrets** 的 `REACTIONT5_API_URL`

（Token 可写在项目根目录 `.reactiont5_token`，与 Secrets 里 `REACTIONT5_API_TOKEN` 保持一致。）

想避免每次改 URL：配置 Cloudflare **Named Tunnel + 固定域名**。

Cloud 默认选「自动」：能连上 ReactionT5 就用它，连不上再用大模型；访客也可在侧栏填自己的 OpenAI 兼容 Key。

### 仅部署 Streamlit 壳

1. 打开 [Streamlit Cloud](https://share.streamlit.io/) → **New app**
2. Repository：`Davina-Dhh/Davina-ChemAgent` · Branch：`main` · Main file：`app.py`
3. （可选）**Secrets**：仓库已预置演示用 Agnes Key；要接 ReactionT5 远程再加上面两项。

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
