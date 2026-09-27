"""全站浮动操作手册：可开关、可拖拽、盖住所有页面层。"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_MANUAL_VERSION = "v7"
_INJECT_FILE = Path(__file__).resolve().parent / "static" / "ops_manual_inject.html"


def _manual_body_html() -> str:
    return """
<div class="com-sec">
  <h4>一、产品是什么</h4>
  <p><b>Davina ChemAgent</b> 是蓝白科幻风的化学 Agent 工作台，覆盖：</p>
  <ul>
    <li><b>反应预测</b>：原料解析 → 产物/条件/投料比/文献 → NMR</li>
    <li><b>分子库</b>：PubChem / ChEMBL 查结构与性质</li>
    <li><b>蛋白对接</b>：下载受体 → Vina 对接 → PyMOL 出图</li>
    <li><b>历史记录</b>：回载修改重跑、对接结果存档</li>
    <li><b>路径出图</b>：多步合成路线对比图</li>
  </ul>
</div>

<div class="com-sec">
  <h4>二、界面速览</h4>
  <ul>
    <li><b>顶栏</b>：品牌与能力模块（说明性，不挡操作）</li>
    <li><b>导航条</b>：反应预测 / 分子库 / 蛋白对接 / 历史 / 路径 / 说明</li>
    <li><b>左侧栏</b>：LLM API Key、Base URL、模型（演示环境已预置 Agnes）</li>
    <li><b>本手册</b>：右下角「手册」按钮，任意页面可开可关、可拖动</li>
  </ul>
</div>

<div class="com-sec">
  <h4>三、最短路径（5 分钟）</h4>
  <ol>
    <li>打开「反应预测」（默认页）</li>
    <li>原料已预填溴苯 + 苯硼酸；或改名后点「解析」/「一键解析」</li>
    <li>条件可保持默认（溶剂/温度/催化剂等）</li>
    <li>产物引擎默认「自动」（优先专业反应模型，连不上再用大模型）→ 点 <b>开始预测</b></li>
    <li>看主产物；需要对接则点 <b>添加为对接配体</b>（自动跳转）</li>
  </ol>
  <p class="com-tip">侧栏 Key 演示环境一般不用改。IBM RXN / ReactionT5 按需再开。</p>
</div>

<div class="com-sec">
  <h4>四、反应预测 · 逐步</h4>
  <ol>
    <li><b>① 两个原料</b>：中文名 / 英文名 / SMILES → 解析；可手工改 SMILES</li>
    <li><b>② 反应条件</b>：溶剂、温度、催化剂、碱、时间、气氛、备注</li>
    <li><b>②½ 引擎</b>：自动 / 大模型 / ReactionT5 本机 / IBM RXN</li>
    <li><b>③ 保存方式</b>：新建记录 或 强制另存 → <b>开始预测</b></li>
    <li>结果区：主产物、候选、投料比、文献；可预测 NMR</li>
    <li>主产物按钮：<b>用作原料 A/B</b>（下一步反应）、<b>添加为对接配体</b></li>
  </ol>
</div>

<div class="com-sec">
  <h4>五、哪些步骤可以省略 / 衔接上次</h4>
  <ul>
    <li><b>可省略解析</b>：若 SMILES 已知，直接贴进 SMILES 框即可</li>
    <li><b>可省略条件优化/文献</b>：取消对应勾选，预测更快</li>
    <li><b>可省略 RXN Key</b>：用大模型或 ReactionT5（Cloud 可能无 T5）</li>
    <li><b>接上次实验</b>：去「历史记录」→ 本页查看 / 回载 → 改条件再预测</li>
    <li><b>多步串联</b>：产物「用作原料 A/B」后不必重查分子库</li>
    <li><b>预测→对接</b>：「添加为对接配体」自带 SMILES 并跳转，可跳过分子库</li>
    <li><b>对接换配体/酶</b>：直接改 SMILES 或受体下拉，不必先清结果</li>
    <li><b>已有 PDB</b>：蛋白页用 PDB ID / 本地已下载结构，可跳过 AlphaFold</li>
  </ul>
</div>

<div class="com-sec">
  <h4>六、分子库查询</h4>
  <ol>
    <li>导航 →「分子库查询」</li>
    <li>输入药名/俗名/SMILES → <b>开始查询</b></li>
    <li>结果可：用作原料 A/B、添加为对接配体</li>
  </ol>
  <p class="com-tip">无需 API Key。PubChem 请控制约 ≤5 次/秒。</p>
</div>

<div class="com-sec">
  <h4>七、蛋白对接（三阶段）</h4>
  <p><b>① 准备</b></p>
  <ol>
    <li>确认/粘贴配体 SMILES（可由预测页带入）</li>
    <li>下载受体：预设酶 / PDB ID / AlphaFold / RCSB 搜索</li>
    <li>人源 TYR 常用 UniProt <code>P14679</code>；需要时做双铜修饰</li>
  </ol>
  <p><b>② 计算</b></p>
  <ol>
    <li>选 Grid Box：文献坐标或自定义尺寸（TYR 常 25³ Å；5M8O 常 22 Å）</li>
    <li>点 <b>开始对接</b>（首次会准备 Vina；结果自动进历史）</li>
  </ol>
  <p><b>③ 分析</b></p>
  <ol>
    <li>看结合能 ΔG、pose、口袋残基</li>
    <li>页内 3D / 下载 complex.pdb · .pml</li>
    <li>可选：渲染 fig1/fig2 PNG 或「用 PyMOL 打开」</li>
  </ol>
</div>

<div class="com-sec">
  <h4>八、历史 · 路径出图 · 说明</h4>
  <ul>
    <li><b>历史记录</b>：查看预测/对接档、回载重跑、删除、导出</li>
    <li><b>路径出图</b>：粘贴多步路线文本 → 生成对比图并下载</li>
    <li><b>说明</b>：功能位置速查表（与本手册互补）</li>
  </ul>
</div>

<div class="com-sec">
  <h4>九、侧栏与引擎注意</h4>
  <ul>
    <li>大模型：产物估计 / 条件 / 文献（侧栏切换模型）</li>
    <li>ReactionT5：本机权重，首次下载；Streamlit Cloud 可能不可用</li>
    <li>IBM RXN：需自备 Key</li>
    <li>对接与 PyMOL：本机/已配置环境更完整</li>
  </ul>
</div>

<div class="com-sec com-sec-last">
  <h4>十、推荐工作流</h4>
  <p class="com-flow">查分子（可选）→ 反应预测 → 用作原料 或 对接配体 → 蛋白对接 → 历史存档 / 路径出图</p>
  <p class="com-tip">拖动本窗口标题栏可移动；点右下角「手册」可随时隐藏。</p>
</div>
"""


def inject_ops_manual() -> None:
    """向父页面注入浮动手册（跨模块、最高层、可拖拽）。"""
    try:
        if not _INJECT_FILE.is_file():
            st.warning("操作手册资源缺失：static/ops_manual_inject.html")
            return

        html = _INJECT_FILE.read_text(encoding="utf-8")
        html = html.replace("__VER__", _MANUAL_VERSION)
        html = html.replace(
            "__BODY__", json.dumps(_manual_body_html(), ensure_ascii=False)
        )

        st.markdown(
            '<style>div.element-container:has(iframe[height="0"]){'
            "position:fixed!important;width:0!important;height:0!important;"
            "margin:0!important;padding:0!important;opacity:0!important;"
            "pointer-events:none!important;overflow:hidden!important;}"
            "</style>",
            unsafe_allow_html=True,
        )
        components.html(html, height=0, scrolling=False)
    except Exception as exc:  # noqa: BLE001
        # 绝不因手册拖垮整站；本地旧缓存/异常时仅提示
        st.caption(f"操作手册未加载（{_MANUAL_VERSION}）：{exc}")
