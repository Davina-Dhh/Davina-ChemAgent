"""全站浮动操作手册：可开关、可拖拽、盖住所有页面层。"""

from __future__ import annotations

import json

import streamlit as st
import streamlit.components.v1 as components

_MANUAL_VERSION = "v4"
_ROOT_ID = "chem-ops-manual-root"
_STYLE_ID = "chem-ops-manual-style"


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
    <li>产物引擎选「自动」或「大模型」→ 点 <b>开始预测</b></li>
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
    # 不用 Python f-string 拼 CSS，避免 {ROOT_ID} / { } 被误解析
    html = r"""
<!DOCTYPE html>
<html><head><meta charset="utf-8" /></head><body>
<script>
(function () {
  const doc = window.parent.document;
  const VER = __VER__;
  const ROOT_ID = "__ROOT_ID__";
  const STYLE_ID = "__STYLE_ID__";
  const BODY_HTML = __BODY__;

  const old = doc.getElementById(ROOT_ID);
  if (old && old.getAttribute("data-ver") === VER) {
    return;
  }
  if (old) old.remove();
  const oldStyle = doc.getElementById(STYLE_ID);
  if (oldStyle) oldStyle.remove();

  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    #__ROOT_ID__ {
      all: initial;
      font-family: "Space Grotesk", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
    }
    #__ROOT_ID__ * { box-sizing: border-box; }
    #__ROOT_ID__ .com-fab {
      position: fixed;
      right: 18px;
      bottom: 22px;
      z-index: 2147483000;
      width: 56px;
      height: 56px;
      border: none;
      border-radius: 50%;
      cursor: pointer;
      color: #fff;
      font-size: 13px;
      font-weight: 700;
      letter-spacing: 0.06em;
      background: linear-gradient(145deg, #39C6FF, #1E8AD8 55%, #0B4F8A);
      box-shadow: 0 10px 28px rgba(30,138,216,0.45), 0 0 0 3px rgba(255,255,255,0.85);
      transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    #__ROOT_ID__ .com-fab:hover {
      transform: translateY(-2px) scale(1.04);
      box-shadow: 0 14px 32px rgba(30,138,216,0.55), 0 0 18px rgba(57,198,255,0.35);
    }
    #__ROOT_ID__ .com-panel {
      position: fixed;
      top: 72px;
      right: 24px;
      width: min(420px, calc(100vw - 24px));
      max-height: min(78vh, 720px);
      z-index: 2147483001;
      display: none;
      flex-direction: column;
      background: linear-gradient(165deg, rgba(255,255,255,0.97), rgba(232,245,255,0.96));
      border: 1px solid rgba(30,138,216,0.35);
      border-radius: 16px;
      box-shadow: 0 22px 50px rgba(14,79,138,0.22), 0 0 0 1px rgba(57,198,255,0.12);
      overflow: hidden;
      backdrop-filter: blur(10px);
    }
    #__ROOT_ID__ .com-panel.com-open { display: flex; }
    #__ROOT_ID__ .com-head {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.75rem 0.85rem;
      cursor: move;
      user-select: none;
      background: linear-gradient(120deg, #0B4F8A, #1E8AD8 60%, #39C6FF);
      color: #fff;
    }
    #__ROOT_ID__ .com-head h3 {
      margin: 0;
      flex: 1;
      font-size: 0.95rem;
      font-weight: 700;
      letter-spacing: 0.04em;
    }
    #__ROOT_ID__ .com-head .com-sub {
      display: block;
      font-size: 0.68rem;
      opacity: 0.88;
      font-weight: 500;
      margin-top: 0.15rem;
      letter-spacing: 0.02em;
    }
    #__ROOT_ID__ .com-head button {
      border: 1px solid rgba(255,255,255,0.35);
      background: rgba(255,255,255,0.14);
      color: #fff;
      border-radius: 8px;
      width: 32px;
      height: 32px;
      cursor: pointer;
      font-size: 16px;
      line-height: 1;
    }
    #__ROOT_ID__ .com-head button:hover { background: rgba(255,255,255,0.28); }
    #__ROOT_ID__ .com-body {
      padding: 0.85rem 1rem 1.1rem;
      overflow: auto;
      color: #0E2438;
      font-size: 0.86rem;
      line-height: 1.55;
    }
    #__ROOT_ID__ .com-sec {
      margin: 0 0 0.95rem;
      padding-bottom: 0.85rem;
      border-bottom: 1px solid rgba(30,138,216,0.14);
    }
    #__ROOT_ID__ .com-sec-last { border-bottom: none; margin-bottom: 0; padding-bottom: 0; }
    #__ROOT_ID__ .com-sec h4 {
      margin: 0 0 0.45rem;
      font-size: 0.92rem;
      color: #0B4F8A;
      letter-spacing: 0.02em;
    }
    #__ROOT_ID__ .com-sec p { margin: 0.35rem 0; }
    #__ROOT_ID__ .com-sec ul, #__ROOT_ID__ .com-sec ol {
      margin: 0.35rem 0 0.2rem 1.15rem;
      padding: 0;
    }
    #__ROOT_ID__ .com-sec li { margin: 0.22rem 0; }
    #__ROOT_ID__ .com-tip {
      margin-top: 0.45rem !important;
      padding: 0.45rem 0.6rem;
      border-radius: 8px;
      background: rgba(57,198,255,0.12);
      border: 1px solid rgba(30,138,216,0.22);
      color: #0B4F8A;
      font-size: 0.8rem;
    }
    #__ROOT_ID__ .com-flow {
      padding: 0.55rem 0.65rem;
      border-radius: 10px;
      background: linear-gradient(120deg, rgba(14,79,138,0.08), rgba(57,198,255,0.12));
      border: 1px solid rgba(30,138,216,0.25);
      font-weight: 600;
      color: #0A3D6E;
      font-size: 0.82rem;
    }
    #__ROOT_ID__ code {
      font-family: ui-monospace, Consolas, monospace;
      font-size: 0.8em;
      background: rgba(14,79,138,0.08);
      padding: 0.05em 0.35em;
      border-radius: 4px;
    }
    @media (max-width: 640px) {
      #__ROOT_ID__ .com-panel {
        width: calc(100vw - 16px);
        right: 8px;
        top: 56px;
        max-height: 75vh;
      }
      #__ROOT_ID__ .com-fab {
        right: 12px;
        bottom: 14px;
        width: 50px;
        height: 50px;
        font-size: 12px;
      }
    }
  `.split("__ROOT_ID__").join(ROOT_ID);
  doc.head.appendChild(style);

  const root = doc.createElement("div");
  root.id = ROOT_ID;
  root.setAttribute("data-ver", VER);

  const fab = doc.createElement("button");
  fab.type = "button";
  fab.className = "com-fab";
  fab.title = "打开/关闭操作手册";
  fab.setAttribute("aria-label", "操作手册");
  fab.textContent = "手册";

  const panel = doc.createElement("div");
  panel.className = "com-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "操作手册");

  const head = doc.createElement("div");
  head.className = "com-head";
  head.innerHTML = '<div style="flex:1;min-width:0;"><h3>操作手册</h3><span class="com-sub">ChemAgent · 可拖动 · 盖住全站</span></div>';
  const closeBtn = doc.createElement("button");
  closeBtn.type = "button";
  closeBtn.className = "com-close";
  closeBtn.title = "关闭";
  closeBtn.textContent = "×";
  head.appendChild(closeBtn);

  const body = doc.createElement("div");
  body.className = "com-body";
  body.innerHTML = BODY_HTML;

  panel.appendChild(head);
  panel.appendChild(body);
  root.appendChild(fab);
  root.appendChild(panel);
  doc.body.appendChild(root);

  const KEY = "chemagent_ops_manual";
  function loadState() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); }
    catch (e) { return {}; }
  }
  function saveState(patch) {
    const cur = loadState();
    localStorage.setItem(KEY, JSON.stringify(Object.assign(cur, patch)));
  }

  const st0 = loadState();
  if (typeof st0.x === "number" && typeof st0.y === "number") {
    panel.style.left = st0.x + "px";
    panel.style.top = st0.y + "px";
    panel.style.right = "auto";
  }
  if (st0.open) panel.classList.add("com-open");

  function toggle(force) {
    const open = typeof force === "boolean" ? force : !panel.classList.contains("com-open");
    panel.classList.toggle("com-open", open);
    saveState({ open: open });
  }
  fab.addEventListener("click", function (e) {
    e.stopPropagation();
    toggle();
  });
  closeBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    toggle(false);
  });

  let drag = null;
  head.addEventListener("pointerdown", function (e) {
    if (e.target.closest("button")) return;
    const rect = panel.getBoundingClientRect();
    drag = {
      dx: e.clientX - rect.left,
      dy: e.clientY - rect.top
    };
    head.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  head.addEventListener("pointermove", function (e) {
    if (!drag) return;
    const x = Math.max(8, Math.min(window.parent.innerWidth - 80, e.clientX - drag.dx));
    const y = Math.max(8, Math.min(window.parent.innerHeight - 80, e.clientY - drag.dy));
    panel.style.left = x + "px";
    panel.style.top = y + "px";
    panel.style.right = "auto";
  });
  function endDrag() {
    if (!drag) return;
    drag = null;
    const rect = panel.getBoundingClientRect();
    saveState({ x: rect.left, y: rect.top });
  }
  head.addEventListener("pointerup", endDrag);
  head.addEventListener("pointercancel", endDrag);
})();
</script>
</body></html>
"""
    html = (
        html.replace("__VER__", json.dumps(_MANUAL_VERSION))
        .replace("__ROOT_ID__", _ROOT_ID)
        .replace("__STYLE_ID__", _STYLE_ID)
        .replace("__BODY__", json.dumps(_manual_body_html(), ensure_ascii=False))
    )

    st.markdown(
        """
<style>
  div.element-container:has(iframe[height="0"]) {
    position: fixed !important;
    width: 0 !important;
    height: 0 !important;
    margin: 0 !important;
    padding: 0 !important;
    opacity: 0 !important;
    pointer-events: none !important;
    overflow: hidden !important;
  }
</style>
""",
        unsafe_allow_html=True,
    )
    components.html(html, height=0, scrolling=False)
