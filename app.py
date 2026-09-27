"""Davina ChemAgent 可视化页面（蓝白清新化学风）。

启动:
  .\\.venv\\Scripts\\streamlit.exe run app.py --server.port 8502
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv

from draw_pathway import parse_routes_text, render_comparison
from history_store import (
    delete_record,
    list_records,
    load_record,
    save_dock_record,
    save_record,
)
from name_resolve import resolve_to_smiles
from ops_manual import inject_ops_manual
from reaction_predict import PredictResult, mol_image, run_prediction, validate_smiles

load_dotenv()
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)

st.set_page_config(
    page_title="Davina ChemAgent",
    page_icon="assets/chem_favicon.png",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _asset_b64(name: str) -> str:
    p = ROOT / "assets" / name
    if not p.is_file():
        return ""
    return base64.b64encode(p.read_bytes()).decode("ascii")


# 依赖仓库内 assets/；未提交时 Cloud 端为空，英雄区会隐藏吉祥物
_MASCOT_B64 = (
    _asset_b64("chem_bunny_female.png")
    or _asset_b64("chem_bunny_scifi.png")
    or _asset_b64("chemist_mascot.png")
)
_STRIP_B64 = _asset_b64("chem_hud_strip.png") or _asset_b64("chem_lab_atmosphere.png")
_FAVICON_B64 = _asset_b64("chem_favicon.png") or _asset_b64("chem_logo_mark.png")

# 冰蓝科幻 HUD · 动态增强版
st.markdown(
    f"""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

  :root {{
    --ink: #0E2438;
    --ink-soft: #4A6B86;
    --deep: #0B4F8A;
    --cyan: #39C6FF;
    --blue: #1E8AD8;
    --ice: #EAF6FF;
    --panel: rgba(255,255,255,0.72);
    --line: rgba(30,138,216,0.22);
    --glow: 0 0 24px rgba(57,198,255,0.22);
  }}

  html, body, [class*="css"] {{
    font-family: "Space Grotesk", "Segoe UI", sans-serif;
    color: var(--ink);
  }}

  .stApp {{
    background-color: #EAF4FC;
    background-image:
      radial-gradient(1.5px 1.5px at 20px 30px, rgba(57,198,255,0.35), transparent),
      radial-gradient(1.5px 1.5px at 80px 70px, rgba(30,138,216,0.28), transparent),
      radial-gradient(1.2px 1.2px at 140px 40px, rgba(57,198,255,0.22), transparent),
      linear-gradient(rgba(30,138,216,0.055) 1px, transparent 1px),
      linear-gradient(90deg, rgba(30,138,216,0.055) 1px, transparent 1px),
      radial-gradient(1000px 480px at 8% -12%, rgba(57,198,255,0.32), transparent 58%),
      radial-gradient(800px 420px at 96% 0%, rgba(14,79,138,0.14), transparent 55%),
      radial-gradient(600px 360px at 50% 100%, rgba(57,198,255,0.10), transparent 60%),
      linear-gradient(180deg, #F8FCFF 0%, #E8F4FC 45%, #F3F9FE 100%);
    background-size:
      160px 120px, 160px 120px, 160px 120px,
      42px 42px, 42px 42px,
      auto, auto, auto, auto;
    animation: chem-aurora 14s ease-in-out infinite alternate;
  }}

  .block-container {{
    padding-top: 0.9rem !important;
    padding-bottom: 3rem !important;
    max-width: 1120px;
  }}

  /* —— 侧栏 HUD —— */
  section[data-testid="stSidebar"] {{
    background:
      linear-gradient(180deg, rgba(250,253,255,0.96) 0%, rgba(232,243,252,0.98) 100%);
    border-right: 1px solid var(--line);
    box-shadow: inset -1px 0 0 rgba(57,198,255,0.12);
  }}
  section[data-testid="stSidebar"] h2 {{
    font-family: "Orbitron", "Space Grotesk", sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.06em !important;
    text-transform: uppercase;
    color: var(--deep) !important;
    font-size: 0.95rem !important;
  }}

  .chem-side-brand {{
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    margin: 0 0 1rem;
    padding: 1rem 0.75rem 1.05rem;
    background: linear-gradient(160deg, rgba(255,255,255,0.9), rgba(232,245,255,0.78));
    border: 1px solid var(--line);
    border-radius: 14px;
    box-shadow: var(--glow);
    overflow: hidden;
  }}
  .chem-side-brand::before {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(115deg, transparent 40%, rgba(57,198,255,0.10) 50%, transparent 60%);
    background-size: 220% 100%;
    animation: chem-scan 5.5s linear infinite;
    pointer-events: none;
  }}
  .chem-side-avatar {{
    width: 88px;
    height: 88px;
    border-radius: 12px;
    object-fit: cover;
    object-position: center 18%;
    background: #0B4F8A;
    border: 1px solid rgba(57,198,255,0.55);
    box-shadow:
      0 0 0 3px rgba(255,255,255,0.7),
      0 0 22px rgba(57,198,255,0.28);
    animation: chem-breathe 5s ease-in-out infinite;
  }}
  .chem-side-name {{
    margin: 0.75rem 0 0.15rem;
    font-family: "Orbitron", sans-serif;
    font-weight: 700;
    font-size: 1.05rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--deep);
  }}
  .chem-side-sub {{
    margin: 0;
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--ink-soft);
  }}
  .chem-side-badge {{
    margin-top: 0.65rem;
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.28rem 0.7rem;
    border-radius: 6px;
    background: rgba(14,79,138,0.08);
    border: 1px solid rgba(57,198,255,0.35);
    color: var(--deep);
    font-family: "Orbitron", sans-serif;
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }}
  .chem-side-badge::before {{
    content: "";
    width: 7px; height: 7px;
    border-radius: 50%;
    background: var(--cyan);
    box-shadow: 0 0 8px rgba(57,198,255,0.85);
    animation: chem-pulse 1.6s ease-in-out infinite;
  }}

  /* —— 顶栏 HUD —— */
  .chem-top {{
    position: relative;
    display: grid;
    grid-template-columns: 1.35fr 0.85fr;
    gap: 1rem;
    align-items: stretch;
    margin: 0 0 0.9rem;
    padding: 1.35rem 1.45rem;
    border-radius: 16px;
    border: 1px solid var(--line);
    background:
      linear-gradient(125deg, rgba(255,255,255,0.88) 0%, rgba(230,244,255,0.75) 55%, rgba(210,234,252,0.55) 100%);
    box-shadow: 0 18px 40px rgba(14,79,138,0.08), var(--glow);
    overflow: hidden;
    animation: chem-fade-in 0.55s ease-out both;
  }}
  .chem-top::before {{
    content: "";
    position: absolute;
    inset: 0;
    background:
      linear-gradient(90deg, transparent, rgba(57,198,255,0.08), transparent);
    background-size: 200% 100%;
    animation: chem-scan 7s linear infinite;
    pointer-events: none;
  }}
  .chem-top::after {{
    content: "";
    position: absolute;
    top: 0; left: 1.2rem; right: 1.2rem;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: 0.85;
  }}
  .chem-kicker {{
    margin: 0 0 0.55rem;
    font-family: "Orbitron", sans-serif;
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--blue);
  }}
  .chem-top-title {{
    margin: 0;
    font-family: "Orbitron", "Space Grotesk", sans-serif;
    font-weight: 700;
    font-size: clamp(1.7rem, 3.2vw, 2.35rem);
    color: var(--ink);
    letter-spacing: 0.02em;
    line-height: 1.15;
  }}
  .chem-top-title span {{
    color: var(--deep);
    text-shadow: 0 0 18px rgba(57,198,255,0.35);
    background: linear-gradient(120deg, #0B4F8A, #1E8AD8, #39C6FF, #1E8AD8);
    background-size: 220% auto;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: chem-shimmer 5s ease infinite;
  }}
  .chem-top-sub {{
    margin: 0.55rem 0 0;
    max-width: 34rem;
    color: var(--ink-soft);
    font-size: 0.95rem;
    font-weight: 500;
    line-height: 1.55;
  }}
  .chem-top-mascot-stage {{
    position: relative;
    z-index: 1;
    justify-self: end;
    width: min(220px, 38vw);
    aspect-ratio: 1;
    display: grid;
    place-items: center;
  }}
  .chem-ring {{
    position: absolute;
    inset: 4%;
    border-radius: 50%;
    border: 1.5px dashed rgba(57,198,255,0.45);
    animation: chem-spin 18s linear infinite;
    pointer-events: none;
  }}
  .chem-ring-2 {{
    inset: -2%;
    border-style: solid;
    border-color: transparent;
    border-top-color: rgba(57,198,255,0.65);
    border-bottom-color: rgba(30,138,216,0.35);
    animation-duration: 10s;
    animation-direction: reverse;
  }}
  .chem-orb {{
    position: absolute;
    width: 10px; height: 10px;
    border-radius: 50%;
    background: radial-gradient(circle, #fff 0%, var(--cyan) 60%, transparent 75%);
    box-shadow: 0 0 12px rgba(57,198,255,0.8);
    animation: chem-orbit 7s linear infinite;
  }}
  .chem-orb.o2 {{ animation-duration: 9.5s; animation-delay: -2s; width: 7px; height: 7px; }}
  .chem-orb.o3 {{ animation-duration: 12s; animation-delay: -4s; width: 6px; height: 6px; }}
  .chem-top-mascot-wrap {{
    position: relative;
    width: 78%;
    aspect-ratio: 1;
    border-radius: 16px;
    overflow: hidden;
    background:
      radial-gradient(circle at 50% 28%, rgba(57,198,255,0.35), transparent 55%),
      linear-gradient(160deg, #F7FCFF, #C8E6FA);
    border: 1px solid rgba(57,198,255,0.55);
    box-shadow:
      0 0 32px rgba(57,198,255,0.28),
      0 12px 28px rgba(14,79,138,0.12);
    animation: chem-float 5s ease-in-out infinite;
  }}
  .chem-top-mascot-wrap::before {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(180deg, transparent 55%, rgba(57,198,255,0.12) 100%);
    pointer-events: none;
    z-index: 1;
  }}
  .chem-top-mascot-wrap::after {{
    content: "";
    position: absolute;
    left: 0; right: 0; height: 28%;
    top: -30%;
    background: linear-gradient(180deg, transparent, rgba(255,255,255,0.45), transparent);
    animation: chem-vscan 3.8s ease-in-out infinite;
    pointer-events: none;
    z-index: 2;
  }}
  .chem-top-mascot-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 14%;
  }}
  .chem-fx-dots {{
    position: absolute;
    inset: 0;
    pointer-events: none;
    z-index: 0;
    overflow: hidden;
  }}
  .chem-fx-dots span {{
    position: absolute;
    width: 4px; height: 4px;
    border-radius: 50%;
    background: var(--cyan);
    opacity: 0.35;
    box-shadow: 0 0 8px rgba(57,198,255,0.7);
    animation: chem-drift 8s ease-in-out infinite;
  }}
  .chem-fx-dots span:nth-child(1) {{ left: 12%; top: 28%; animation-delay: 0s; }}
  .chem-fx-dots span:nth-child(2) {{ left: 28%; top: 68%; animation-delay: -1.2s; width: 3px; height: 3px; }}
  .chem-fx-dots span:nth-child(3) {{ left: 62%; top: 22%; animation-delay: -2.4s; }}
  .chem-fx-dots span:nth-child(4) {{ left: 78%; top: 58%; animation-delay: -3.1s; width: 5px; height: 5px; }}
  .chem-fx-dots span:nth-child(5) {{ left: 46%; top: 80%; animation-delay: -4s; }}
  .chem-metric-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin-top: 0.85rem;
  }}
  .chem-metric {{
    padding: 0.35rem 0.65rem;
    border-radius: 8px;
    background: rgba(14,79,138,0.06);
    border: 1px solid rgba(57,198,255,0.28);
    font-family: "Orbitron", sans-serif;
    font-size: 0.62rem;
    letter-spacing: 0.08em;
    color: var(--deep);
    animation: chem-blink 4.5s ease-in-out infinite;
  }}
  .chem-metric:nth-child(2) {{ animation-delay: 0.8s; }}
  .chem-metric:nth-child(3) {{ animation-delay: 1.6s; }}

  /* —— 装饰六边形 / HUD 条 —— */
  .chem-hex-field {{
    position: absolute;
    inset: auto -8% -18% auto;
    width: 180px; height: 180px;
    opacity: 0.35;
    pointer-events: none;
    z-index: 0;
    background:
      radial-gradient(circle at 30% 30%, rgba(57,198,255,0.35), transparent 45%),
      radial-gradient(circle at 70% 65%, rgba(30,138,216,0.22), transparent 50%);
    mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Cpath fill='white' d='M50 4 L90 27 V73 L50 96 L10 73 V27 Z'/%3E%3C/svg%3E");
    -webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Cpath fill='white' d='M50 4 L90 27 V73 L50 96 L10 73 V27 Z'/%3E%3C/svg%3E");
    animation: chem-spin 28s linear infinite;
  }}
  /* —— 能力矩阵：标题条 + 四宫格 —— */
  .chem-section {{
    margin: 0 0 1rem;
  }}
  .chem-strip {{
    position: relative;
    min-height: 88px;
    margin: 0 0 0.7rem;
    padding: 1rem 1.15rem 0.95rem;
    border-radius: 14px;
    overflow: hidden;
    border: 1px solid rgba(30,138,216,0.28);
    background-color: #C5E4F7;
    background-image:
      linear-gradient(105deg, rgba(248,252,255,0.94) 0%, rgba(232,245,255,0.88) 42%, rgba(210,234,250,0.55) 100%),
      url("data:image/png;base64,{_STRIP_B64}");
    background-size: cover;
    background-position: center right;
    box-shadow: 0 12px 28px rgba(14,79,138,0.10);
  }}
  .chem-strip-beam {{
    position: absolute;
    inset: 0;
    background: linear-gradient(105deg, transparent 40%, rgba(57,198,255,0.16) 50%, transparent 60%);
    background-size: 220% 100%;
    animation: chem-scan 6s linear infinite;
    pointer-events: none;
  }}
  .chem-strip-inner {{
    position: relative;
    z-index: 1;
    max-width: 34rem;
  }}
  .chem-strip-kicker {{
    margin: 0 0 0.35rem;
    font-family: "Orbitron", sans-serif;
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: #1470B8;
  }}
  .chem-strip-title {{
    margin: 0;
    font-family: "Orbitron", "Space Grotesk", sans-serif;
    font-weight: 700;
    font-size: clamp(1.15rem, 2.4vw, 1.45rem);
    letter-spacing: 0.04em;
    color: #0A3D6E;
    text-shadow: 0 1px 0 rgba(255,255,255,0.65);
    line-height: 1.25;
  }}
  .chem-strip-title em {{
    font-style: normal;
    color: #1E8AD8;
  }}
  .chem-strip-sub {{
    margin: 0.4rem 0 0;
    font-size: 0.84rem;
    font-weight: 560;
    color: #3A5F7E;
    line-height: 1.45;
  }}
  .chem-strip-tags {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-top: 0.55rem;
  }}
  .chem-strip-tags b {{
    font-family: "Orbitron", sans-serif;
    font-size: 0.58rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    padding: 0.22rem 0.5rem;
    border-radius: 5px;
    color: #0B4F8A;
    background: rgba(255,255,255,0.72);
    border: 1px solid rgba(30,138,216,0.28);
  }}

  .chem-modules {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0.65rem;
  }}
  .chem-mod {{
    position: relative;
    padding: 0.85rem 0.75rem 0.8rem;
    border-radius: 14px;
    background: linear-gradient(160deg, rgba(255,255,255,0.95), rgba(232,245,255,0.82));
    border: 1px solid var(--line);
    box-shadow: 0 10px 22px rgba(14,79,138,0.06);
    overflow: hidden;
    transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    animation: chem-rise 0.55s ease-out both;
  }}
  .chem-mod:nth-child(2) {{ animation-delay: 0.06s; }}
  .chem-mod:nth-child(3) {{ animation-delay: 0.12s; }}
  .chem-mod:nth-child(4) {{ animation-delay: 0.18s; }}
  .chem-mod:hover {{
    transform: translateY(-3px);
    border-color: rgba(57,198,255,0.5);
    box-shadow: 0 14px 28px rgba(14,79,138,0.12), 0 0 18px rgba(57,198,255,0.15);
  }}
  .chem-mod::before {{
    content: "";
    position: absolute;
    top: 0; left: 12%; right: 12%;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    opacity: 0.8;
  }}
  .chem-mod-ico {{
    width: 42px; height: 42px;
    margin-bottom: 0.55rem;
    border-radius: 11px;
    display: grid;
    place-items: center;
    background: linear-gradient(145deg, #EAF6FF, #C9E8FA);
    border: 1px solid rgba(57,198,255,0.35);
    box-shadow: 0 0 14px rgba(57,198,255,0.15);
  }}
  .chem-mod-ico svg {{ width: 24px; height: 24px; }}
  .chem-mod strong {{
    display: block;
    font-family: "Orbitron", sans-serif;
    font-size: 0.78rem;
    letter-spacing: 0.05em;
    color: #0A3D6E;
    margin-bottom: 0.28rem;
  }}
  .chem-mod span {{
    display: block;
    font-size: 0.78rem;
    color: #4A6B86;
    line-height: 1.4;
    font-weight: 560;
  }}

  /* —— 系统面板 —— */
  .chem-welcome {{
    position: relative;
    display: grid;
    grid-template-columns: 96px 1fr;
    gap: 0.95rem;
    align-items: center;
    margin: 0 0 1rem;
    padding: 1rem 1.1rem;
    background: var(--panel);
    backdrop-filter: blur(12px);
    border: 1px solid var(--line);
    border-radius: 14px;
    box-shadow: 0 12px 28px rgba(14,79,138,0.06);
    animation: chem-rise 0.6s 0.05s ease-out both;
  }}
  .chem-welcome::before {{
    content: "";
    position: absolute;
    left: 0; top: 12px; bottom: 12px;
    width: 3px;
    border-radius: 3px;
    background: linear-gradient(180deg, var(--cyan), var(--blue));
    box-shadow: 0 0 12px rgba(57,198,255,0.45);
  }}
  .chem-welcome-art {{
    width: 84px;
    height: 84px;
    border-radius: 12px;
    overflow: hidden;
    background: linear-gradient(160deg, #F4FAFF, #CDE7FA);
    border: 1px solid rgba(57,198,255,0.4);
    box-shadow: 0 0 16px rgba(57,198,255,0.15);
  }}
  .chem-welcome-art img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 18%;
  }}
  .chem-welcome h3 {{
    margin: 0 0 0.3rem !important;
    font-family: "Orbitron", sans-serif !important;
    font-weight: 600 !important;
    font-size: 0.92rem !important;
    letter-spacing: 0.05em !important;
    text-transform: uppercase;
    color: var(--deep) !important;
  }}
  .chem-welcome p {{
    margin: 0;
    color: var(--ink-soft);
    font-size: 0.88rem;
    line-height: 1.5;
    font-weight: 500;
  }}
  .chem-steps {{
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-top: 0.65rem;
  }}
  .chem-step {{
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.26rem 0.6rem;
    border-radius: 6px;
    background: rgba(14,79,138,0.05);
    color: var(--deep);
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    border: 1px solid rgba(30,138,216,0.2);
  }}
  .chem-step i {{
    width: 18px; height: 18px;
    border-radius: 4px;
    display: inline-grid;
    place-items: center;
    background: linear-gradient(145deg, #39C6FF, #1E8AD8);
    color: #fff;
    font-style: normal;
    font-family: "Orbitron", sans-serif;
    font-size: 0.58rem;
    font-weight: 700;
  }}

  @keyframes chem-float {{
    0%, 100% {{ transform: translateY(0); }}
    50% {{ transform: translateY(-8px); }}
  }}
  @keyframes chem-breathe {{
    0%, 100% {{ transform: scale(1); }}
    50% {{ transform: scale(1.04); }}
  }}
  @keyframes chem-pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.45; }}
  }}
  @keyframes chem-fade-in {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}
  @keyframes chem-rise {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}
  @keyframes chem-scan {{
    0% {{ background-position: 120% 0; }}
    100% {{ background-position: -120% 0; }}
  }}
  @keyframes chem-shimmer {{
    0% {{ background-position: 0% 50%; }}
    100% {{ background-position: 100% 50%; }}
  }}
  @keyframes chem-aurora {{
    0% {{ background-position: 0 0, 0 0, 0 0, 0 0, 0 0, 0% 0%, 100% 0%, 50% 100%, 0 0; }}
    100% {{ background-position: 40px 20px, -30px 40px, 20px -20px, 0 0, 0 0, 8% 4%, 92% 6%, 48% 96%, 0 0; }}
  }}
  @keyframes chem-spin {{
    to {{ transform: rotate(360deg); }}
  }}
  @keyframes chem-orbit {{
    0% {{ transform: rotate(0deg) translateX(92px) rotate(0deg); }}
    100% {{ transform: rotate(360deg) translateX(92px) rotate(-360deg); }}
  }}
  @keyframes chem-vscan {{
    0% {{ top: -30%; opacity: 0; }}
    20% {{ opacity: 0.7; }}
    55% {{ opacity: 0.5; }}
    100% {{ top: 110%; opacity: 0; }}
  }}
  @keyframes chem-drift {{
    0%, 100% {{ transform: translateY(0); opacity: 0.25; }}
    50% {{ transform: translateY(-14px); opacity: 0.7; }}
  }}
  @keyframes chem-blink {{
    0%, 100% {{ border-color: rgba(57,198,255,0.28); box-shadow: none; }}
    50% {{ border-color: rgba(57,198,255,0.65); box-shadow: 0 0 12px rgba(57,198,255,0.2); }}
  }}
  @keyframes chem-ripple {{
    0% {{ box-shadow: 0 0 0 0 rgba(57,198,255,0.35); }}
    70% {{ box-shadow: 0 0 0 12px rgba(57,198,255,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(57,198,255,0); }}
  }}

  /* —— 导航：精密条 —— */
  div[role="radiogroup"] {{
    gap: 0.25rem !important;
    background: rgba(255,255,255,0.78);
    backdrop-filter: blur(10px);
    padding: 0.35rem !important;
    border-radius: 12px;
    border: 1px solid var(--line);
    box-shadow: 0 8px 22px rgba(14,79,138,0.06);
    justify-content: center;
    flex-wrap: wrap !important;
    margin-bottom: 0.4rem;
  }}
  div[role="radiogroup"] label {{
    background: transparent !important;
    border-radius: 8px !important;
    padding: 0.42rem 0.85rem !important;
    font-size: 0.86rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em;
    color: var(--ink-soft) !important;
    transition: all 0.2s ease !important;
  }}
  div[role="radiogroup"] label:hover {{
    background: rgba(57,198,255,0.10) !important;
    color: var(--deep) !important;
  }}
  div[role="radiogroup"] label:has(input:checked) {{
    background: linear-gradient(135deg, #1E8AD8, #0B4F8A) !important;
    color: #fff !important;
    box-shadow: 0 0 16px rgba(57,198,255,0.35);
  }}

  /* —— 平板 / 手机 —— */
  @media (max-width: 900px) {{
    .chem-modules {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  @media (max-width: 820px) {{
    .block-container {{
      padding-left: 0.85rem !important;
      padding-right: 0.85rem !important;
      padding-top: 0.55rem !important;
    }}
    /* 手机端双栏改单栏堆叠，避免挤扁 */
    div[data-testid="stHorizontalBlock"] {{
      flex-wrap: wrap !important;
      gap: 0.35rem !important;
    }}
    div[data-testid="stHorizontalBlock"] > div {{
      min-width: min(100%, 280px) !important;
      flex: 1 1 100% !important;
    }}
    .chem-top {{
      grid-template-columns: 1fr;
      text-align: left;
      padding: 1rem 1rem 1.05rem;
      gap: 0.75rem;
    }}
    .chem-top-title {{ font-size: 1.45rem; letter-spacing: 0; }}
    .chem-top-sub {{ font-size: 0.86rem; max-width: none; }}
    .chem-kicker {{ font-size: 0.58rem; letter-spacing: 0.14em; }}
    .chem-top-mascot-stage {{
      justify-self: center;
      width: 132px;
      order: -1;
      margin: 0 auto 0.15rem;
    }}
    .chem-ring, .chem-ring-2, .chem-orb, .chem-hex-field, .chem-fx-dots {{
      display: none !important;
    }}
    .chem-top-mascot-wrap {{
      width: 100%;
      border-radius: 14px;
      animation: none;
      box-shadow: 0 8px 20px rgba(14,79,138,0.12);
    }}
    .chem-top-mascot-wrap::after {{ display: none; }}
    .chem-metric {{ font-size: 0.55rem; padding: 0.28rem 0.5rem; }}
    .chem-strip {{
      min-height: 0;
      padding: 0.85rem 0.9rem;
      margin-bottom: 0.55rem;
    }}
    .chem-strip-title {{ font-size: 1.05rem; }}
    .chem-strip-sub {{ font-size: 0.78rem; }}
    .chem-strip-kicker {{ font-size: 0.55rem; letter-spacing: 0.12em; }}
    .chem-modules {{
      grid-template-columns: repeat(2, 1fr);
      gap: 0.5rem;
    }}
    .chem-mod {{ padding: 0.7rem 0.65rem; }}
    .chem-mod strong {{ font-size: 0.66rem; }}
    .chem-mod span {{ font-size: 0.7rem; }}
    .chem-mod-ico {{ width: 36px; height: 36px; }}
    .chem-mod-ico svg {{ width: 20px; height: 20px; }}
    .chem-welcome {{
      grid-template-columns: 64px 1fr;
      gap: 0.7rem;
      padding: 0.8rem 0.85rem 0.8rem 1rem;
      align-items: start;
    }}
    .chem-welcome-art {{ width: 64px; height: 64px; }}
    .chem-welcome h3 {{ font-size: 0.78rem !important; letter-spacing: 0.03em !important; }}
    .chem-welcome p {{ font-size: 0.8rem; }}
    .chem-steps {{ gap: 0.3rem; }}
    .chem-step {{ font-size: 0.65rem; padding: 0.22rem 0.45rem; }}

    div[role="radiogroup"] {{
      justify-content: flex-start !important;
      gap: 0.2rem !important;
      padding: 0.3rem !important;
      border-radius: 12px;
      overflow-x: auto;
      flex-wrap: nowrap !important;
      -webkit-overflow-scrolling: touch;
    }}
    div[role="radiogroup"] label {{
      padding: 0.38rem 0.65rem !important;
      font-size: 0.78rem !important;
      white-space: nowrap !important;
      flex: 0 0 auto !important;
    }}

    .stButton > button,
    .stDownloadButton > button {{
      min-height: 2.45rem !important;
      font-size: 0.88rem !important;
    }}
    section[data-testid="stSidebar"] .chem-side-avatar {{
      width: 72px; height: 72px;
    }}
  }}
  @media (max-width: 420px) {{
    .chem-modules {{ grid-template-columns: 1fr 1fr; }}
    .chem-top-title {{ font-size: 1.28rem; }}
    .chem-metric-row {{ gap: 0.3rem; }}
    .chem-welcome {{ grid-template-columns: 1fr; text-align: left; }}
    .chem-welcome-art {{ width: 56px; height: 56px; }}
  }}
  @media (prefers-reduced-motion: reduce) {{
    .stApp, .chem-top::before, .chem-ring, .chem-orb, .chem-top-mascot-wrap,
    .chem-top-title span, .chem-metric, .chem-strip-beam,
    .stButton > button[kind="primary"] {{
      animation: none !important;
    }}
  }}

  /* —— 产物面板 —— */
  .main-product-box {{
    position: relative;
    border: 1px solid rgba(57,198,255,0.35);
    background: linear-gradient(145deg, rgba(255,255,255,0.95), rgba(232,245,255,0.9));
    border-radius: 14px;
    padding: 1.15rem 1.3rem;
    margin: 0.9rem 0 1.25rem;
    box-shadow: 0 14px 34px rgba(14,79,138,0.08), 0 0 20px rgba(57,198,255,0.08);
  }}
  .main-product-box::before {{
    content: "";
    position: absolute;
    top: 0; left: 1rem; right: 1rem;
    height: 2px;
    background: linear-gradient(90deg, transparent, var(--cyan), transparent);
  }}
  .main-product-title {{
    color: var(--deep);
    font-family: "Orbitron", sans-serif;
    font-size: 1.15rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    margin-bottom: 0.4rem;
  }}

  /* —— 科幻按钮 —— */
  .stButton > button,
  .stDownloadButton > button,
  div[data-testid="stFormSubmitButton"] > button,
  button[data-testid="baseButton-primary"],
  button[data-testid="baseButton-secondary"],
  button[kind="primary"],
  button[kind="secondary"] {{
    border-radius: 10px !important;
    font-family: "Space Grotesk", sans-serif !important;
    font-weight: 650 !important;
    font-size: 0.92rem !important;
    letter-spacing: 0.03em !important;
    min-height: 2.6rem !important;
    padding: 0.48rem 1.15rem !important;
    position: relative !important;
    overflow: hidden !important;
    transition:
      transform 0.2s cubic-bezier(.2,.8,.2,1),
      box-shadow 0.2s ease,
      border-color 0.2s ease,
      filter 0.2s ease !important;
  }}

  .stButton > button,
  .stDownloadButton > button,
  button[data-testid="baseButton-secondary"],
  button[kind="secondary"] {{
    background: linear-gradient(180deg, rgba(255,255,255,0.95), rgba(236,246,255,0.95)) !important;
    color: var(--deep) !important;
    border: 1px solid rgba(30,138,216,0.35) !important;
    box-shadow: 0 4px 14px rgba(14,79,138,0.07) !important;
  }}
  .stButton > button:hover,
  .stDownloadButton > button:hover,
  button[data-testid="baseButton-secondary"]:hover,
  button[kind="secondary"]:hover {{
    transform: translateY(-2px);
    border-color: rgba(57,198,255,0.7) !important;
    box-shadow: 0 8px 22px rgba(14,79,138,0.12), 0 0 16px rgba(57,198,255,0.18) !important;
    color: var(--deep) !important;
  }}
  .stButton > button:active,
  .stDownloadButton > button:active {{
    transform: translateY(0) scale(0.985);
  }}

  .stButton > button[kind="primary"],
  .stDownloadButton > button[kind="primary"],
  button[data-testid="baseButton-primary"],
  button[kind="primary"],
  div[data-testid="stFormSubmitButton"] > button {{
    background: linear-gradient(120deg, #39C6FF, #1E8AD8, #0B4F8A, #1E8AD8) !important;
    background-size: 220% 220% !important;
    animation: chem-shimmer 5s ease infinite !important;
    border: 1px solid rgba(57,198,255,0.45) !important;
    color: #fff !important;
    text-shadow: 0 1px 0 rgba(0,0,0,0.15);
    box-shadow:
      0 10px 24px rgba(30,138,216,0.35),
      0 0 18px rgba(57,198,255,0.22),
      inset 0 1px 0 rgba(255,255,255,0.28) !important;
  }}
  .stButton > button[kind="primary"]::after,
  button[data-testid="baseButton-primary"]::after,
  button[kind="primary"]::after {{
    content: "";
    position: absolute;
    inset: 0;
    background: linear-gradient(105deg, transparent 35%, rgba(255,255,255,0.35) 50%, transparent 65%);
    background-size: 220% 100%;
    animation: chem-scan 2.8s linear infinite;
    pointer-events: none;
  }}
  .stButton > button[kind="primary"]:hover,
  .stDownloadButton > button[kind="primary"]:hover,
  button[data-testid="baseButton-primary"]:hover,
  button[kind="primary"]:hover,
  div[data-testid="stFormSubmitButton"] > button:hover {{
    transform: translateY(-3px) scale(1.02);
    filter: brightness(1.08);
    animation: chem-shimmer 5s ease infinite, chem-ripple 1.2s ease-out infinite !important;
    box-shadow:
      0 16px 34px rgba(30,138,216,0.45),
      0 0 32px rgba(57,198,255,0.4),
      inset 0 1px 0 rgba(255,255,255,0.35) !important;
    color: #fff !important;
  }}
  .stButton > button[kind="primary"]:active,
  button[data-testid="baseButton-primary"]:active {{
    transform: translateY(0) scale(0.985);
  }}

  .stButton > button:disabled,
  .stDownloadButton > button:disabled,
  button[disabled] {{
    opacity: 0.48 !important;
    transform: none !important;
    animation: none !important;
    box-shadow: none !important;
  }}

  div[data-testid="column"] .stButton > button {{ width: 100%; }}

  h1, h2, h3 {{ color: var(--deep) !important; }}
  h2, h3 {{
    font-family: "Orbitron", "Space Grotesk", sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em;
    text-transform: none;
  }}

  .stTextInput input,
  .stTextArea textarea,
  .stSelectbox div[data-baseweb="select"] > div {{
    border-radius: 10px !important;
    border-color: var(--line) !important;
    background: rgba(255,255,255,0.92) !important;
    box-shadow: inset 0 0 0 1px rgba(57,198,255,0.05);
  }}
  .stTextInput input:focus,
  .stTextArea textarea:focus {{
    border-color: rgba(57,198,255,0.65) !important;
    box-shadow: 0 0 0 3px rgba(57,198,255,0.15) !important;
  }}

  div[data-testid="stSlider"] [role="slider"] {{
    background-color: var(--cyan) !important;
    box-shadow: 0 0 10px rgba(57,198,255,0.45);
  }}

  hr {{
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, rgba(30,138,216,0.35), transparent) !important;
  }}

  div[data-testid="stExpander"] {{
    background: rgba(255,255,255,0.78);
    border: 1px solid var(--line);
    border-radius: 12px;
    backdrop-filter: blur(8px);
  }}
  div[data-testid="stAlert"] {{ border-radius: 12px; }}

  header[data-testid="stHeader"] {{ background: transparent; }}
  div[data-testid="stDecoration"] {{ display: none; }}
  footer {{ visibility: hidden; }}
</style>
""",
    unsafe_allow_html=True,
)


def _chem_hero_html() -> str:
    mascot = ""
    if _MASCOT_B64:
        mascot = (
            f'<img alt="Female bunny chemist" '
            f'src="data:image/png;base64,{_MASCOT_B64}" />'
        )
    # 内联 SVG：分子 / 烧瓶 / DNA / 原子（不依赖额外切图）
    ico_mol = """<svg viewBox="0 0 24 24" fill="none" stroke="#1E8AD8" stroke-width="1.6"><circle cx="6" cy="12" r="2.2" fill="#39C6FF"/><circle cx="18" cy="6" r="2.2" fill="#7CC8F0"/><circle cx="18" cy="18" r="2.2" fill="#0B4F8A"/><path d="M8 12h8M16.5 7.2l-7 3.6M16.5 16.8l-7-3.6" stroke-linecap="round"/></svg>"""
    ico_flask = """<svg viewBox="0 0 24 24" fill="none" stroke="#1E8AD8" stroke-width="1.6"><path d="M9 3h6M10 3v5l-4.5 9.2A2.5 2.5 0 0 0 7.8 21h8.4a2.5 2.5 0 0 0 2.3-3.8L14 8V3" stroke-linejoin="round"/><path d="M8.2 14h7.6" stroke="#39C6FF"/><circle cx="10" cy="16.5" r="0.8" fill="#39C6FF" stroke="none"/><circle cx="13.5" cy="17.5" r="0.6" fill="#7CC8F0" stroke="none"/></svg>"""
    ico_dna = """<svg viewBox="0 0 24 24" fill="none" stroke="#1E8AD8" stroke-width="1.6"><path d="M7 4c4 3 6 3 10 0M7 20c4-3 6-3 10 0M7 8c4 2.2 6 2.2 10 0M7 16c4-2.2 6-2.2 10 0" stroke-linecap="round"/><path d="M9 6.5h6M9 12h6M9 17.5h6" stroke="#39C6FF" stroke-width="1.2"/></svg>"""
    ico_atom = """<svg viewBox="0 0 24 24" fill="none" stroke="#1E8AD8" stroke-width="1.5"><circle cx="12" cy="12" r="2.2" fill="#39C6FF" stroke="none"/><ellipse cx="12" cy="12" rx="9" ry="3.8" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="9" ry="3.8" transform="rotate(-60 12 12)"/><ellipse cx="12" cy="12" rx="9" ry="3.8"/></svg>"""
    return f"""
<div class="chem-top">
  <div class="chem-fx-dots" aria-hidden="true">
    <span></span><span></span><span></span><span></span><span></span>
  </div>
  <div class="chem-hex-field" aria-hidden="true"></div>
  <div style="position:relative;z-index:1;">
    <p class="chem-kicker">ChemOps // Neural Lab Console</p>
    <p class="chem-top-title">Davina <span>ChemAgent</span></p>
    <p class="chem-top-sub">
      冰蓝分子计算台 · 反应推演 · 结构检索 · 蛋白对接 · 光谱 / 文献链路
    </p>
    <div class="chem-metric-row">
      <span class="chem-metric">CPU · ONLINE</span>
      <span class="chem-metric">RXN · STANDBY</span>
      <span class="chem-metric">VINA · READY</span>
    </div>
  </div>
  <div class="chem-top-mascot-stage">
    <div class="chem-ring"></div>
    <div class="chem-ring chem-ring-2"></div>
    <span class="chem-orb"></span>
    <span class="chem-orb o2"></span>
    <span class="chem-orb o3"></span>
    <div class="chem-top-mascot-wrap">{mascot}</div>
  </div>
</div>
<section class="chem-section">
  <div class="chem-strip">
    <div class="chem-strip-beam"></div>
    <div class="chem-strip-inner">
      <p class="chem-strip-kicker">Capability Matrix</p>
      <p class="chem-strip-title">核心能力 <em>模块</em></p>
      <p class="chem-strip-sub">从反应预测到蛋白对接，四条可切换的化学计算链路。</p>
      <div class="chem-strip-tags">
        <b>LATTICE</b><b>SPECTRAL</b><b>DOCKING</b><b>LITERATURE</b>
      </div>
    </div>
  </div>
  <div class="chem-modules">
    <div class="chem-mod"><div class="chem-mod-ico">{ico_flask}</div><strong>RXN ENGINE</strong><span>反应预测与条件推演</span></div>
    <div class="chem-mod"><div class="chem-mod-ico">{ico_mol}</div><strong>MOL DATABASE</strong><span>PubChem / ChEMBL 检索</span></div>
    <div class="chem-mod"><div class="chem-mod-ico">{ico_atom}</div><strong>DOCKING</strong><span>Vina 口袋与结合能</span></div>
    <div class="chem-mod"><div class="chem-mod-ico">{ico_dna}</div><strong>NMR / LIT</strong><span>光谱估计与文献链路</span></div>
  </div>
</section>
<div class="chem-welcome">
  <div class="chem-welcome-art">{mascot}</div>
  <div>
    <h3>SYSTEM READY · 女兔实验员在线</h3>
    <p>配置原料与参数后启动引擎；也可切到对接跑 Vina，或在分子库查结构。</p>
    <div class="chem-steps">
      <span class="chem-step"><i>01</i>解析原料</span>
      <span class="chem-step"><i>02</i>引擎推演</span>
      <span class="chem-step"><i>03</i>产物 / 对接</span>
    </div>
  </div>
</div>
"""


def _chem_sidebar_brand_html() -> str:
    avatar = ""
    if _MASCOT_B64:
        avatar = (
            f'<img class="chem-side-avatar" alt="Female bunny chemist" '
            f'src="data:image/png;base64,{_MASCOT_B64}" />'
        )
    elif _FAVICON_B64:
        avatar = (
            f'<img class="chem-side-avatar" alt="ChemAgent mark" '
            f'src="data:image/png;base64,{_FAVICON_B64}" '
            f'style="object-fit:contain;padding:12px;background:#fff;" />'
        )
    return f"""
<div class="chem-side-brand">
  {avatar}
  <p class="chem-side-name">ChemAgent</p>
  <p class="chem-side-sub">Ice-Tech · Agent Node</p>
  <div class="chem-side-badge">Link Active</div>
</div>
"""

def _sidebar_keys() -> None:
    # 1) 仓库内演示默认 Key（访客无需自填）
    try:
        import demo_defaults as _dd

        for k in ("OPENAI_API_KEY", "OPENAI_API_BASE", "CHEMCROW_MODEL", "REACTIONT5_DISCOVERY_URL"):
            v = getattr(_dd, k, None)
            if v and not (os.getenv(k) or "").strip():
                os.environ[k] = str(v)
    except Exception:
        pass

    # 2) Streamlit Cloud Secrets / 本地 secrets.toml（可覆盖默认）
    try:
        if hasattr(st, "secrets") and st.secrets:
            for k in (
                "OPENAI_API_KEY",
                "OPENAI_API_BASE",
                "CHEMCROW_MODEL",
                "RXN4CHEM_API_KEY",
                "HF_TOKEN",
                "REACTIONT5_API_URL",
                "REACTIONT5_API_TOKEN",
                "REACTIONT5_DISCOVERY_URL",
            ):
                try:
                    v = st.secrets.get(k)  # type: ignore[attr-defined]
                except Exception:
                    v = None
                if v:
                    os.environ[k] = str(v)
    except Exception:
        pass

    st.sidebar.markdown(_chem_sidebar_brand_html(), unsafe_allow_html=True)
    st.sidebar.header("API / 模型")
    st.sidebar.caption("演示环境已预置 Agnes Key，一般无需修改。")
    agnes = st.sidebar.text_input(
        "LLM API Key（OpenAI 兼容）",
        value=os.getenv("OPENAI_API_KEY", ""),
        type="password",
    )
    base = st.sidebar.text_input(
        "LLM Base URL",
        value=os.getenv("OPENAI_API_BASE", "https://apihub.agnes-ai.com/v1"),
    )
    rxn = st.sidebar.text_input(
        "IBM RXN API Key（可选）",
        value=os.getenv("RXN4CHEM_API_KEY", ""),
        type="password",
    )
    hf = st.sidebar.text_input(
        "Hugging Face Token（可选，一般可留空）",
        value="",
        type="password",
        help="ReactionT5 本机推理一般不需要 Token；填错反而会 401",
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "专业反应模型：本机开机运行 keep_t5_online.bat（可装开机自启），"
        "Cloud 自动发现地址，刷新即可调用。"
    )
    with st.sidebar.expander("高级：手动覆盖地址 / Token", expanded=False):
        t5_url = st.text_input(
            "反应模型 API URL（可留空）",
            value=os.getenv("REACTIONT5_API_URL", ""),
            help="一般留空，走自动发现。",
            placeholder="通常留空",
            key="t5_api_url_input",
        )
        t5_tok = st.text_input(
            "反应模型 API Token",
            value=os.getenv("REACTIONT5_API_TOKEN", ""),
            type="password",
            help="与本机 .reactiont5_token 一致；Cloud Secrets 配一次即可",
            key="t5_api_tok_input",
        )

    presets = [
        "agnes-2.5-flash",
        "agnes-2.0-flash",
        "gpt-4o",
        "gpt-4o-mini",
        "deepseek-chat",
        "自定义…",
    ]
    current = os.getenv("CHEMCROW_MODEL", "agnes-2.5-flash")
    default_idx = presets.index(current) if current in presets else len(presets) - 1
    pick = st.sidebar.selectbox("大模型（产物/条件/文献）", presets, index=default_idx)
    if pick == "自定义…":
        model = st.sidebar.text_input(
            "自定义模型名",
            value=current if current not in presets[:-1] else "agnes-2.5-flash",
        )
    else:
        model = pick

    st.session_state["ui_llm_model"] = (model or "agnes-2.5-flash").strip()
    st.sidebar.caption(f"当前模型：`{st.session_state['ui_llm_model']}`")

    if agnes:
        os.environ["OPENAI_API_KEY"] = agnes
    if base:
        os.environ["OPENAI_API_BASE"] = base
    if rxn:
        os.environ["RXN4CHEM_API_KEY"] = rxn
    if hf:
        os.environ["HF_TOKEN"] = hf
        os.environ["HUGGINGFACE_HUB_TOKEN"] = hf
    if t5_url.strip():
        os.environ["REACTIONT5_API_URL"] = t5_url.strip().rstrip("/")
    elif "REACTIONT5_API_URL" in os.environ and not (os.getenv("REACTIONT5_API_URL") or "").strip():
        pass
    if t5_tok.strip():
        os.environ["REACTIONT5_API_TOKEN"] = t5_tok.strip()
    os.environ["CHEMCROW_MODEL"] = st.session_state["ui_llm_model"]

    st.sidebar.markdown("---")
    has_rxn = bool((rxn or os.getenv("RXN4CHEM_API_KEY") or "").strip())
    has_hf = bool((hf or os.getenv("HF_TOKEN") or "").strip())
    try:
        from reactiont5_remote import resolve_reactiont5_base_url as _rb

        has_t5_remote = bool(_rb())
    except Exception:
        has_t5_remote = bool((os.getenv("REACTIONT5_API_URL") or "").strip())
    st.sidebar.caption(
        "产物：自动优先专业反应模型，连不上再用大模型 / 自备 Key。"
        + (" · 反应模型在线" if has_t5_remote else " · 反应模型未在线（本机跑 keep_t5_online）")
        + (" · 已有 RXN" if has_rxn else "")
        + (" · 已有 HF" if has_hf else "")
    )


def _init_state() -> None:
    defaults = {
        "input_a": "溴苯",
        "input_b": "苯硼酸",
        "smi_a": "c1ccccc1Br",
        "smi_b": "B(O)(O)c1ccccc1",
        "src_a": "local",
        "src_b": "local",
        "solvent": "甲苯/水",
        "temperature": "80 °C",
        "catalyst": "Pd(PPh3)4",
        "base": "K2CO3",
        "reagents": "",
        "time_h": "12 h",
        "atmosphere": "氮气",
        "notes": "Suzuki 偶联尝试",
        "active_record_id": None,
        "last_predict": None,
        "last_predict_meta": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _apply_pending_reactants() -> None:
    """必须在任何 key=input_a/smi_a 的 widget 创建之前调用。"""
    for side in ("a", "b"):
        pend_key = f"_pending_reactant_{side}"
        if pend_key not in st.session_state:
            continue
        data = st.session_state.pop(pend_key) or {}
        st.session_state[f"input_{side}"] = data.get("display") or data.get("smiles") or ""
        st.session_state[f"smi_{side}"] = data.get("smiles") or ""
        st.session_state[f"src_{side}"] = data.get("src") or "from-product"


def _fill_reactant(smiles: str, side: str, label: str = "") -> None:
    """button on_click 回调：在下一轮脚本最前写入原料（早于 widget）。"""
    smi = (smiles or "").strip()
    if not smi:
        return
    st.session_state[f"_pending_reactant_{side}"] = {
        "display": smi,
        "smiles": smi,
        "src": f"from-product:{label}" if label else "from-product",
    }
    st.session_state["active_record_id"] = None
    st.session_state["_reactant_toast"] = (
        f"已把产物写入原料 {side.upper()}：`{smi}`。"
        "请点上方「反应预测」页签继续投料。"
    )


def _apply_pending_dock_ligand() -> None:
    """在对接页 SMILES widget 之前写入待添加配体。"""
    if "_pending_dock_ligand" not in st.session_state:
        return
    smi = (st.session_state.pop("_pending_dock_ligand") or "").strip()
    if not smi:
        return
    st.session_state["dock_ligand_smi"] = smi
    st.session_state["protein_ligand_smi"] = smi


def _fill_dock_ligand(smiles: str, label: str = "") -> None:
    """预测结果 → 对接配体，并跳转蛋白对接页。"""
    smi = (smiles or "").strip()
    if not smi:
        return
    st.session_state["_pending_dock_ligand"] = smi
    st.session_state["nav_goto"] = "蛋白对接"
    st.session_state["_dock_toast"] = (
        f"已添加为分子对接配体"
        + (f"（{label}）" if label else "")
        + f"：`{smi[:64]}`"
    )


def _load_dock_viz():
    """强制 reload dock_viz，避免 Streamlit 热重载缓存旧模块缺符号。"""
    import importlib
    import sys

    import dock_viz as _dv

    _dv = importlib.reload(_dv)
    # 极少数情况下 reload 半成品：再清缓存强载一次
    if not hasattr(_dv, "has_embedded_pymol"):
        sys.modules.pop("dock_viz", None)
        import dock_viz as _dv  # noqa: F811

        _dv = importlib.reload(_dv)
    return _dv


def _use_as_reactant(smiles: str, side: str, label: str = "") -> None:
    """兼容旧调用：排队写入并 rerun（勿放在会 catch Exception 的 try 里）。"""
    _fill_reactant(smiles, side, label)
    st.rerun()


def _resolve_box(side: str, label: str) -> None:
    input_key = f"input_{side}"
    smi_key = f"smi_{side}"
    src_key = f"src_{side}"

    st.markdown(f"**{label}**（中文名 / 英文名 / SMILES，可改）")
    st.text_input(
        f"{label}输入",
        key=input_key,
        label_visibility="collapsed",
        placeholder="例如：溴苯 / bromobenzene / c1ccccc1Br",
    )
    b1, b2 = st.columns(2)
    with b1:
        if st.button(f"解析{label}", key=f"btn_resolve_{side}", use_container_width=True):
            ok, val, src = resolve_to_smiles(st.session_state[input_key])
            if ok:
                st.session_state[smi_key] = val
                st.session_state[src_key] = src
                st.success(f"已解析 → `{val}`（{src}）")
            else:
                st.error(val)
    with b2:
        if st.button(f"清空{label}", key=f"btn_clear_{side}", use_container_width=True):
            st.session_state[f"_pending_reactant_{side}"] = {
                "display": "",
                "smiles": "",
                "src": "",
            }
            st.rerun()

    st.text_input(f"{label} SMILES（可手工改）", key=smi_key)
    smi = st.session_state.get(smi_key, "")
    if smi:
        img = mol_image(smi, size=(300, 220))
        if img:
            st.image(img, caption=f"{label} 结构", width=280)
        else:
            st.error(validate_smiles(smi)[1])
        src = st.session_state.get(src_key, "")
        if src:
            st.caption(f"来源：{src}")


def _result_from_session() -> PredictResult | None:
    """从 session 还原结果。始终按 dict 存，避免模块热重载后 isinstance 失效。"""
    raw = st.session_state.get("last_predict")
    if raw is None:
        return None
    try:
        return _dict_to_result(raw)
    except Exception as exc:  # noqa: BLE001
        st.session_state["last_predict_error"] = str(exc)
        return None


def _dict_to_result(raw) -> PredictResult:
    from dataclasses import asdict, fields, is_dataclass

    from reaction_predict import ConditionSuggestion, MoleculeHit

    if is_dataclass(raw) and not isinstance(raw, type):
        raw = asdict(raw)
    if not isinstance(raw, dict):
        raise TypeError(f"无法识别的结果类型: {type(raw)}")

    mh_names = {f.name for f in fields(MoleculeHit)}
    cs_names = {f.name for f in fields(ConditionSuggestion)}
    products = [
        MoleculeHit(**{k: v for k, v in p.items() if k in mh_names})
        for p in (raw.get("products") or [])
        if isinstance(p, dict)
    ]
    suggestions = [
        ConditionSuggestion(**{k: v for k, v in s.items() if k in cs_names})
        for s in (raw.get("condition_suggestions") or [])
        if isinstance(s, dict)
    ]
    return PredictResult(
        precursors=raw.get("precursors", ""),
        input_conditions=raw.get("input_conditions") or {},
        products=products,
        condition_suggestions=suggestions,
        literature=raw.get("literature") or [],
        engine=raw.get("engine", ""),
        llm_model=raw.get("llm_model", ""),
        product_backend=raw.get("product_backend", ""),
        warnings=raw.get("warnings") or [],
        raw=raw.get("raw") or {},
    )


def _show_compound_literature(
    smiles: str,
    ninfo: Dict[str, str],
    *,
    key_prefix: str,
    extra_hits: Optional[List[Dict[str, str]]] = None,
) -> None:
    """具体论文标题 + 可跳转；SciFinder 可复制结构。"""
    from urllib.parse import quote_plus

    en = (ninfo.get("iupac_en") or ninfo.get("iupac") or "").strip()
    zh = (ninfo.get("iupac_zh") or "").strip()
    inchikey = (ninfo.get("inchikey") or "").strip()
    inchi = (ninfo.get("inchi") or "").strip()
    molfile = (ninfo.get("molfile") or "").strip()
    smi = (ninfo.get("smiles") or smiles or "").strip()

    st.markdown("#### 相关文献（本化合物 / 相近结构）")
    st.caption("优先展示论文**具体标题**；点按钮打开百度学术或 PubMed 检索页（不用 doi.org）。")

    # 检索用名
    if en or zh:
        st.markdown("**检索用名**")
        if en:
            st.code(en, language=None)
        if zh:
            st.code(zh, language=None)

    # 拉论文
    papers: List[Dict[str, str]] = []
    try:
        from literature import search_compound_papers

        with st.spinner("检索相关论文标题…"):
            papers = search_compound_papers(
                iupac_en=en,
                iupac_zh=zh,
                inchikey=inchikey,
                smiles=smi,
                limit=8,
            )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"论文检索暂失败：{exc}")

    if papers:
        st.markdown("**① 具体文献（标题可复制，按钮可跳转）**")
        for i, p in enumerate(papers, 1):
            title = p.get("paper_title") or p.get("title") or ""
            note = p.get("note") or ""
            st.markdown(f"**{i}. {title}**")
            if note:
                st.caption(f"`{p.get('source') or ''}` · {note}")
            st.code(title, language=None)
            c1, c2, c3 = st.columns(3)
            with c1:
                if p.get("url_baidu") or p.get("url"):
                    st.link_button(
                        "百度学术",
                        p.get("url_baidu") or p["url"],
                        key=f"{key_prefix}_pap_bd_{i}",
                        use_container_width=True,
                    )
            with c2:
                if p.get("url_pubmed"):
                    st.link_button(
                        "PubMed",
                        p["url_pubmed"],
                        key=f"{key_prefix}_pap_pm_{i}",
                        use_container_width=True,
                    )
            with c3:
                st.link_button(
                    "知网搜标题",
                    "https://kns.cnki.net/kns8s/defaultresult/index?kw="
                    + quote_plus(title[:80]),
                    key=f"{key_prefix}_pap_cnki_{i}",
                    use_container_width=True,
                )
    else:
        st.info(
            "暂未自动命中论文标题。请用上方化合物名去 SciFinder / 知网 / 百度学术搜；"
            "或复制下方 SMILES 在 SciFinder 按结构找相近化合物文献。"
        )

    st.markdown("**② SciFinder：按结构找本化合物 / 相近结构文献与谱图**")
    st.caption(
        "登录后 Substances 粘贴 SMILES → 可看文献；"
        "Refine → NMR 可找别人做过的核磁谱。"
    )
    st.link_button(
        "打开 SciFinder-n",
        "https://scifinder-n.cas.org/",
        key=f"{key_prefix}_sf_portal",
        use_container_width=True,
    )
    st.markdown("可复制 · SMILES（SciFinder 直接粘贴）")
    st.code(smi, language=None)
    if inchikey:
        st.markdown("可复制 · InChIKey")
        st.code(inchikey, language=None)
    if inchi:
        with st.expander("可复制 · InChI", expanded=False):
            st.code(inchi, language=None)
    if molfile:
        st.download_button(
            "下载 Molfile（.mol）→ SciFinder Import",
            data=molfile.encode("utf-8"),
            file_name="product_scifinder.mol",
            mime="chemical/x-mdl-molfile",
            key=f"{key_prefix}_sf_mol",
            use_container_width=True,
        )

    if extra_hits:
        with st.expander("其它模型线索（需人工核实）", expanded=False):
            for j, lit in enumerate(extra_hits, 1):
                title = lit.get("title") or "线索"
                url = lit.get("url") or ""
                note = lit.get("note") or ""
                src = lit.get("source") or ""
                st.markdown(f"{j}. **{title}** `{src}`")
                if note:
                    st.caption(note)
                if url:
                    st.link_button(
                        "打开",
                        url,
                        key=f"{key_prefix}_extra_lit_{j}",
                        use_container_width=True,
                    )


def _show_result_panel(result: PredictResult, *, key_prefix: str = "main") -> None:
    if not result.products:
        st.error("未得到产物候选")
        return

    main = next((p for p in result.products if p.role == "product"), result.products[0])
    st.markdown('<div class="main-product-box">', unsafe_allow_html=True)
    st.markdown(
        '<div class="main-product-title">★ 预测主产物</div>',
        unsafe_allow_html=True,
    )
    rid = st.session_state.get("active_record_id")
    st.markdown(
        f"**产物引擎：** `{getattr(result, 'product_backend', '') or '—'}`  ·  "
        f"**大模型：** `{getattr(result, 'llm_model', '') or '—'}`"
    )
    st.caption(result.engine + (f"  ·  记录 `{rid}`" if rid else ""))
    mc1, mc2 = st.columns([1, 2])
    with mc1:
        img = mol_image(main.smiles, size=(360, 280))
        if img:
            st.image(img, use_container_width=True)
        else:
            st.warning(f"结构图绘制失败：{main.smiles}")
    with mc2:
        st.markdown("**SMILES**")
        st.code(main.smiles, language=None)
        # 系统命名（中英）
        from chem_names import resolve_systematic_name

        name_key = f"{key_prefix}_iupac_{main.smiles}"
        force_name = st.session_state.pop(f"{name_key}_force", False)
        cached = st.session_state.get(name_key) or {}
        # 无英文名才自动重解析；有英文即可先展示（快）
        need_name = force_name or name_key not in st.session_state or (
            not (cached.get("iupac_en") or cached.get("iupac"))
        )
        if need_name:
            try:
                from chem_names import clear_name_cache

                clear_name_cache(main.smiles)
                with st.spinner("解析系统命名（约数秒；新化合物可能稍慢）…"):
                    # 首次只要尽快出英文；点「重新解析」时再强制补中文
                    st.session_state[name_key] = resolve_systematic_name(
                        main.smiles, want_zh=bool(force_name)
                    )
            except Exception as exc:  # noqa: BLE001
                st.session_state[name_key] = {
                    "error": str(exc),
                    "iupac": "",
                    "iupac_en": "",
                    "iupac_zh": "",
                    "inchikey": "",
                    "smiles": main.smiles,
                }
        ninfo = st.session_state.get(name_key) or {}
        st.markdown("**系统命名结果 (IUPAC)**")
        en = ninfo.get("iupac_en") or ninfo.get("iupac") or ""
        zh = ninfo.get("iupac_zh") or ""
        if en or zh:
            if en:
                st.markdown("英文")
                st.code(en, language=None)
                st.caption(f"来源：{ninfo.get('source') or '—'}")
            if zh:
                st.markdown("中文")
                st.code(zh, language=None)
                st.caption(f"来源：{ninfo.get('source_zh') or '—'}")
            elif en:
                st.caption("中文系统名暂缺（PubChem 繁忙时会走侧边栏大模型，可点下方重新解析）")
            if ninfo.get("inchikey"):
                st.caption(f"InChIKey：`{ninfo['inchikey']}`")
        else:
            st.warning(ninfo.get("error") or "暂无系统命名")
            if ninfo.get("inchikey"):
                st.caption(f"InChIKey：`{ninfo['inchikey']}`（请用结构在 SciFinder 检索）")
        if st.button("重新解析系统命名", key=f"{name_key}_retry"):
            st.session_state[f"{name_key}_force"] = True
            st.session_state.pop(name_key, None)
            try:
                from chem_names import clear_name_cache

                clear_name_cache(main.smiles)
            except Exception:  # noqa: BLE001
                pass
            st.rerun()

        u1, u2, u3, u4 = st.columns(4)
        with u1:
            st.button(
                "用作原料 A",
                key=f"{key_prefix}_as_a",
                use_container_width=True,
                on_click=_fill_reactant,
                args=(main.smiles, "a", "中间体(主产物)"),
            )
        with u2:
            st.button(
                "用作原料 B",
                key=f"{key_prefix}_as_b",
                use_container_width=True,
                on_click=_fill_reactant,
                args=(main.smiles, "b", "中间体(主产物)"),
            )
        with u3:
            st.button(
                "添加为对接配体",
                key=f"{key_prefix}_as_dock",
                use_container_width=True,
                type="primary",
                on_click=_fill_dock_ligand,
                args=(main.smiles, "预测主产物"),
                help="写入对接 SMILES 并跳转到「蛋白对接」",
            )
        with u4:
            st.download_button(
                "下载 SMILES",
                data=main.smiles.encode("utf-8"),
                file_name="main_product.smi",
                mime="text/plain",
                key=f"{key_prefix}_dl_smi",
                use_container_width=True,
            )
    st.markdown("</div>", unsafe_allow_html=True)

    byproducts = [p for p in result.products if p.smiles != main.smiles]
    if byproducts:
        with st.expander(
            f"副产物 / 其他候选（{len(byproducts)}）— 也可作为下一步原料",
            expanded=False,
        ):
            for i, hit in enumerate(byproducts):
                cols = st.columns([1, 2, 1, 1])
                with cols[0]:
                    img = mol_image(hit.smiles, size=(200, 150))
                    if img:
                        st.image(img, use_container_width=True)
                with cols[1]:
                    st.markdown(f"**#{hit.rank}** `{hit.role}`")
                    st.code(hit.smiles, language=None)
                with cols[2]:
                    st.button(
                        "→ 原料A",
                        key=f"{key_prefix}_bp_a_{i}",
                        use_container_width=True,
                        on_click=_fill_reactant,
                        args=(hit.smiles, "a", f"候选#{hit.rank}"),
                    )
                with cols[3]:
                    st.button(
                        "→ 原料B",
                        key=f"{key_prefix}_bp_b_{i}",
                        use_container_width=True,
                        on_click=_fill_reactant,
                        args=(hit.smiles, "b", f"候选#{hit.rank}"),
                    )

    if result.condition_suggestions:
        st.markdown("#### 条件优化 + 投料比 / 用量（基准：原料 A = 1.0 mmol）")
        rows = []
        for i, s in enumerate(result.condition_suggestions, 1):
            rows.append(
                {
                    "方案": i,
                    "A equiv": s.reactant_a_equiv,
                    "B equiv": s.reactant_b_equiv,
                    "催化剂 mol%": s.catalyst_mol_percent,
                    "碱 equiv": s.base_equiv,
                    "添加剂 equiv": s.additive_equiv,
                    "溶剂 mL/mmol A": s.solvent_ml_per_mmol_a,
                    "浓度 M": s.concentration_m,
                    "溶剂": s.solvent,
                    "温度": s.temperature_c,
                    "催化剂": s.catalyst,
                    "碱": s.base,
                    "时间": s.time_h,
                    "气氛": s.atmosphere,
                    "用量说明": s.scale_note,
                    "理由": s.rationale,
                    "预期效果": s.expected_effect,
                }
            )
        st.dataframe(rows, use_container_width=True)
        with st.expander("各方案用量说明（文字）", expanded=True):
            for i, s in enumerate(result.condition_suggestions, 1):
                st.markdown(f"**方案 {i}：** {s.scale_note or '（无）'}")
                st.caption(s.rationale)

    _show_compound_literature(
        main.smiles,
        ninfo,
        key_prefix=key_prefix,
        extra_hits=list(result.literature or []) or None,
    )

    _show_nmr_section(
        main.smiles,
        key_prefix=key_prefix,
        cached_nmr=_nmr_from_session(key_prefix),
        name_info=ninfo,
    )

    for w in result.warnings:
        st.warning(w)


def _nmr_from_session(key_prefix: str):
    view = st.session_state.get(f"nmr_view_{key_prefix}")
    if view:
        return view
    lp = st.session_state.get("last_predict")
    if isinstance(lp, dict) and lp.get("nmr"):
        return lp["nmr"]
    return None


def _load_nmr_api():
    """强制加载最新 nmr_predict（避免 Streamlit 缓存旧模块缺函数）。"""
    import importlib
    import sys

    if "nmr_predict" in sys.modules:
        importlib.reload(sys.modules["nmr_predict"])
    import nmr_predict as nmr

    need = (
        "NMRPeak",
        "NMRSpectrum",
        "SOLVENT_LABELS",
        "fig_to_png_bytes",
        "format_peak_list_text",
        "plot_stick_spectrum",
        "predict_both",
        "search_nmr_literature",
        "build_ms_scifinder_guide",
        "spectrum_to_rows",
        "expected_h_count",
    )
    missing = [n for n in need if not hasattr(nmr, n)]
    if missing:
        raise ImportError(
            f"nmr_predict 缺少: {missing}。请重启 UI（start_ui.bat）后再试。"
        )
    return nmr


def _show_nmr_section(
    smiles: str,
    *,
    key_prefix: str,
    cached_nmr=None,
    name_info: Optional[Dict[str, str]] = None,
) -> None:
    """主产物 ¹H / ¹³C NMR（NMRShiftDB，溶剂 CDCl3 / DMSO-d6）。"""
    try:
        nmr = _load_nmr_api()
    except Exception as exc:  # noqa: BLE001
        st.warning(f"NMR 模块暂不可用：{exc}")
        return

    SOLVENT_LABELS = nmr.SOLVENT_LABELS
    NMRPeak = nmr.NMRPeak
    NMRSpectrum = nmr.NMRSpectrum
    fig_to_png_bytes = nmr.fig_to_png_bytes
    format_peak_list_text = nmr.format_peak_list_text
    plot_stick_spectrum = nmr.plot_stick_spectrum
    predict_both = nmr.predict_both
    search_nmr_literature = nmr.search_nmr_literature
    build_ms_scifinder_guide = nmr.build_ms_scifinder_guide
    spectrum_to_rows = nmr.spectrum_to_rows
    expected_h_count = nmr.expected_h_count

    st.markdown("#### ¹H / ¹³C NMR（预测）")
    st.caption(
        "数据来自 [NMRShiftDB2](https://nmrshiftdb.nmr.uni-koeln.de) 公开预测，"
        "溶剂可选氘代氯仿 / 氘代 DMSO；**仅供参考，不能替代实测谱**。"
    )

    c1, c2, c3 = st.columns([2, 2, 2])
    with c1:
        solvent = st.selectbox(
            "氘代溶剂",
            options=list(SOLVENT_LABELS.keys()),
            format_func=lambda k: SOLVENT_LABELS[k],
            key=f"{key_prefix}_nmr_sol",
            index=0,
        )
    with c2:
        do_h = st.checkbox("¹H", value=True, key=f"{key_prefix}_nmr_h")
    with c3:
        do_c = st.checkbox("¹³C", value=True, key=f"{key_prefix}_nmr_c")

    if st.button(
        "预测主产物 NMR + 检索文献谱",
        type="secondary",
        key=f"{key_prefix}_nmr_go",
        use_container_width=True,
    ):
        with st.spinner(
            f"预测位移并检索文献谱（{SOLVENT_LABELS.get(solvent, solvent)}）…"
        ):
            both = predict_both(smiles, solvent, timeout=120.0)
            lit_query = {}
            ms_guide = {}
            lit = []
            try:
                from chem_names import literature_query_terms

                lit_query = literature_query_terms(smiles)
                lit = search_nmr_literature(smiles, solvent, limit=8)
                ms_guide = build_ms_scifinder_guide(smiles)
            except Exception as lit_exc:  # noqa: BLE001
                st.warning(f"文献检索部分失败（谱图仍可用）：{lit_exc}")
        payload = {
            "solvent": solvent,
            "smiles": smiles,
            "literature": lit,
            "lit_query": lit_query,
            "ms_guide": ms_guide,
        }
        if do_h:
            payload["1H"] = both["1H"].to_dict()
        if do_c:
            payload["13C"] = both["13C"].to_dict()
        lp = st.session_state.get("last_predict")
        if isinstance(lp, dict):
            lp = dict(lp)
            lp["nmr"] = payload
            st.session_state["last_predict"] = lp
        st.session_state[f"nmr_view_{key_prefix}"] = payload
        rid = st.session_state.get("active_record_id")
        if rid:
            full = load_record(rid)
            if full and isinstance(full.get("result"), dict):
                full["result"]["nmr"] = payload
                save_record(full, record_id=rid)
        st.rerun()

    view = cached_nmr or st.session_state.get(f"nmr_view_{key_prefix}")
    if not view:
        return

    st.caption(
        f"结构 `{view.get('smiles', smiles)}` · 溶剂 **"
        f"{SOLVENT_LABELS.get(view.get('solvent', ''), view.get('solvent', ''))}**"
        " · 谱图标题为英文（避免缺字方块）"
    )

    left, right = st.columns([3, 2])
    with left:
        for nuc in ("1H", "13C"):
            raw = view.get(nuc)
            if not raw:
                continue
            peaks = [
                NMRPeak(
                    **{
                        k: p.get(k)
                        for k in (
                            "ppm",
                            "multiplicity",
                            "atoms",
                            "n_h",
                            "note",
                            "origin",
                        )
                        if k in p
                    }
                )
                for p in (raw.get("peaks") or [])
                if isinstance(p, dict)
            ]
            spec = NMRSpectrum(
                nucleus=raw.get("nucleus", nuc),
                solvent_key=raw.get("solvent_key", view.get("solvent", "")),
                solvent_name=raw.get("solvent_name", ""),
                smiles=raw.get("smiles", smiles),
                peaks=peaks,
                source=raw.get("source", "NMRShiftDB2"),
                predicted=bool(raw.get("predicted", True)),
                error=raw.get("error", ""),
                raw_meta=raw.get("raw_meta") or {},
            )
            st.markdown(f"**{nuc} NMR（预测峰 + 溶剂残峰）**")
            if spec.error:
                st.error(spec.error)
                continue
            if nuc == "1H":
                tot = sum(
                    p.n_h
                    for p in spec.peaks
                    if (p.origin or "product") == "product" and p.n_h
                )
                exp = expected_h_count(smiles)
                tip = f"产物积分合计 **{tot} H**（不含溶剂残峰）"
                if exp is not None:
                    tip += f"；结构式期望约 **{exp} H**"
                    if tot != exp:
                        tip += "（差多来自交换氢/预测误差）"
                sol_key = view.get("solvent") or spec.solvent_key
                if sol_key == "CDCl3":
                    tip += " · 已标 **CDCl₃ 残峰 7.26**"
                elif sol_key == "DMSO-d6":
                    tip += " · 已标 **DMSO-d₆ 残峰 2.50**"
                st.caption(tip)
            st.code(format_peak_list_text(spec), language=None)
            rows = spectrum_to_rows(spec)
            if rows:
                st.dataframe(rows, use_container_width=True, hide_index=True)
            fig = plot_stick_spectrum(spec)
            if fig is not None:
                st.image(fig_to_png_bytes(fig), use_container_width=True)
                import matplotlib.pyplot as plt

                plt.close(fig)

    with right:
        st.markdown("**找别人做过的 NMR → SciFinder**")
        st.caption(
            "主推 SciFinder：复制下方结构 → Substances 粘贴 → "
            "Refine：**NMR / 1H NMR / 13C NMR**"
        )
        ms = view.get("ms_guide") or {}
        smi_sf = ms.get("smiles") or smiles
        st.link_button(
            "打开 SciFinder-n",
            ms.get("portal") or "https://scifinder-n.cas.org/",
            key=f"{key_prefix}_nmr_sf",
            use_container_width=True,
        )
        st.markdown("可复制 · SMILES")
        st.code(smi_sf, language=None)
        if ms.get("inchikey"):
            st.markdown("可复制 · InChIKey")
            st.code(ms["inchikey"], language=None)
        if ms.get("molfile"):
            st.download_button(
                "下载 .mol（SciFinder Import）",
                data=ms["molfile"].encode("utf-8"),
                file_name="nmr_scifinder.mol",
                mime="chemical/x-mdl-molfile",
                key=f"{key_prefix}_nmr_mol",
                use_container_width=True,
            )
        if ms.get("how_nmr") or ms.get("how"):
            st.caption(ms.get("how_nmr") or ms.get("how"))

        en = (
            ms.get("iupac_en")
            or (view.get("lit_query") or {}).get("iupac_en")
            or (name_info or {}).get("iupac_en")
            or ""
        )
        zh = (
            ms.get("iupac_zh")
            or (view.get("lit_query") or {}).get("iupac_zh")
            or (name_info or {}).get("iupac_zh")
            or ""
        )
        if en or zh:
            st.markdown("化合物名（也可在 SciFinder 按名搜）")
            if en:
                st.code(en, language=None)
            if zh:
                st.code(zh, language=None)

        lit_list = [x for x in (view.get("literature") or []) if x.get("kind") == "paper"]
        if lit_list:
            st.markdown("**相关论文标题**")
            for i, lit in enumerate(lit_list[:6], 1):
                title = lit.get("paper_title") or lit.get("title") or ""
                st.markdown(f"**{i}.** {title}")
                st.code(title, language=None)
                b1, b2 = st.columns(2)
                with b1:
                    if lit.get("url"):
                        st.link_button(
                            "百度学术",
                            lit["url"],
                            key=f"{key_prefix}_nmr_pap_bd_{i}",
                            use_container_width=True,
                        )
                with b2:
                    if lit.get("url_pubmed"):
                        st.link_button(
                            "PubMed",
                            lit["url_pubmed"],
                            key=f"{key_prefix}_nmr_pap_pm_{i}",
                            use_container_width=True,
                        )
        else:
            st.caption("完整论文列表见上方「相关文献」；点 NMR 按钮可刷新本侧。")


def page_predict():
    _init_state()
    st.subheader("反应预测")
    st.caption(
        "支持：历史回载修改重跑 · 无名产物作下一步原料 · 投料比/用量 · 文献链接"
    )

    toast = st.session_state.pop("_reactant_toast", None)
    if toast:
        st.success(toast)

    if st.session_state.get("last_predict_error"):
        st.error(f"上次结果无法显示：{st.session_state.pop('last_predict_error')}")

    result = _result_from_session()
    if result:
        st.success(
            f"已有预测结果（引擎 `{result.product_backend or '—'}`，"
            f"{len(result.products)} 个产物候选）。结果在页面下方「④ 预测结果」。"
        )

    st.markdown("### ① 两个原料")
    c1, c2 = st.columns(2)
    with c1:
        _resolve_box("a", "原料 A")
    with c2:
        _resolve_box("b", "原料 B")

    if st.button("一键解析两个原料", use_container_width=True):
        for side in ("a", "b"):
            ok, val, src = resolve_to_smiles(st.session_state.get(f"input_{side}", ""))
            if ok:
                st.session_state[f"smi_{side}"] = val
                st.session_state[f"src_{side}"] = src
            else:
                st.error(f"原料 {side.upper()}: {val}")
        st.rerun()

    st.markdown("### ② 反应条件")
    r1, r2, r3 = st.columns(3)
    with r1:
        st.text_input("溶剂", key="solvent")
        st.text_input("温度", key="temperature")
    with r2:
        st.text_input("催化剂", key="catalyst")
        st.text_input("碱", key="base")
    with r3:
        st.text_input("其他试剂（名或 SMILES）", key="reagents")
        st.text_input("时间", key="time_h")
    st.text_input("气氛", key="atmosphere")
    st.text_area("备注", key="notes", height=70)

    st.markdown("### ②½ 预测引擎（可切换）")
    has_rxn = bool((os.getenv("RXN4CHEM_API_KEY") or "").strip())
    try:
        from reactiont5_remote import resolve_reactiont5_base_url

        has_t5_url = bool(resolve_reactiont5_base_url())
    except Exception:
        has_t5_url = bool((os.getenv("REACTIONT5_API_URL") or "").strip())
    engine_labels = {
        "auto": "自动（优先专业反应模型 → 连不上再用大模型）",
        "reactiont5": "仅专业反应模型"
        + (" · 远程已配置" if has_t5_url else " · 本机或需配置远程 URL"),
        "llm": f"仅大模型 — `{st.session_state.get('ui_llm_model', os.getenv('CHEMCROW_MODEL', 'agnes-2.5-flash'))}`（可填自己的 Key）",
        "rxn": "IBM RXN（需 Key）" + ("" if has_rxn else " ⚠️ 未填 Key"),
    }
    engine_keys = list(engine_labels.keys())
    default_engine = "auto"
    product_engine = st.radio(
        "产物预测后端",
        options=engine_keys,
        format_func=lambda k: engine_labels[k],
        index=engine_keys.index(default_engine),
        horizontal=False,
        key="product_engine_radio",
        help="默认自动：先连专业反应模型（本机/远程）；失败则用侧栏大模型。也可填写自己的 OpenAI 兼容 Key。",
    )
    if product_engine in ("auto", "reactiont5"):
        try:
            from reactiont5_remote import cache_status

            cs = cache_status()
            if cs.get("remote"):
                st.caption(
                    f"默认走远程反应模型：`{cs.get('remote_url')}`"
                    " · 连不上会自动改用大模型"
                )
            elif cs.get("ready"):
                st.caption("本机反应模型缓存已就绪。")
            else:
                st.caption(
                    "本机反应模型缓存未就绪（首次会下载）。"
                    "Cloud 请在 Secrets 配置远程 API URL。"
                )
        except Exception:
            pass
    if product_engine == "llm":
        st.info(
            f"将仅用大模型 **`{st.session_state.get('ui_llm_model', 'agnes-2.5-flash')}`**。"
            "可在侧栏填写自己的 OpenAI 兼容 Key / Base URL。"
        )

    o1, o2, o3 = st.columns(3)
    with o1:
        top_n = st.slider("返回候选数", 1, 8, 5)
    with o2:
        optimize = st.checkbox("条件优化 + 投料比", value=True)
    with o3:
        fetch_lit = st.checkbox("检索相关文献链接", value=True)

    st.markdown("### ③ 预测并自动保存")
    save_mode = st.radio(
        "保存方式",
        ["覆盖当前记录" if st.session_state.get("active_record_id") else "新建记录", "强制另存为新记录"],
        horizontal=True,
    )

    if st.button("开始预测", type="primary", use_container_width=True):
        smi_a = st.session_state.get("smi_a", "").strip()
        smi_b = st.session_state.get("smi_b", "").strip()
        if not smi_a:
            ok, val, src = resolve_to_smiles(st.session_state.get("input_a", ""))
            if ok:
                smi_a = val
                st.session_state["smi_a"] = val
                st.session_state["src_a"] = src
        if not smi_b:
            ok, val, src = resolve_to_smiles(st.session_state.get("input_b", ""))
            if ok:
                smi_b = val
                st.session_state["smi_b"] = val
                st.session_state["src_b"] = src
        if not smi_a or not smi_b:
            st.error("请先填写并解析两个原料")
            return

        reagents_smi = st.session_state.get("reagents", "").strip()
        if reagents_smi and not validate_smiles(reagents_smi)[0]:
            ok, val, _ = resolve_to_smiles(reagents_smi)
            reagents_smi = val if ok else ""

        spin_msg = (
            "ReactionT5 推理中…"
            if product_engine in ("reactiont5", "auto")
            else "预测产物 / 投料 / 文献中…"
        )
        with st.spinner(spin_msg):
            try:
                pred = run_prediction(
                    smi_a,
                    smi_b,
                    reagents=reagents_smi,
                    solvent=st.session_state.get("solvent", ""),
                    temperature=st.session_state.get("temperature", ""),
                    catalyst=st.session_state.get("catalyst", ""),
                    base=st.session_state.get("base", ""),
                    time_h=st.session_state.get("time_h", ""),
                    atmosphere=st.session_state.get("atmosphere", ""),
                    notes=st.session_state.get("notes", ""),
                    top_n=top_n,
                    product_engine=product_engine,
                    llm_model=st.session_state.get("ui_llm_model"),
                    optimize_conditions=optimize,
                    fetch_literature=fetch_lit,
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"预测失败：{exc}")
                if product_engine in ("reactiont5", "auto"):
                    st.info(
                        "ReactionT5 失败常见原因：本机服务/隧道未开、URL 过期、首次下载中断。"
                        "可重试；或改选「仅大模型」并填写自己的 Key。"
                    )
                else:
                    st.info(
                        "若频繁出现 JSON 解析错误：多半是模型输出被截断。"
                        "可稍后重试，改选自动/ReactionT5，或填写 IBM RXN API Key；"
                        "也可先取消「检索相关文献」减轻请求。"
                    )
                return

        overwrite_id = None
        if (
            save_mode.startswith("覆盖")
            and st.session_state.get("active_record_id")
        ):
            overwrite_id = st.session_state["active_record_id"]

        payload = {
            "input_a": st.session_state.get("input_a", ""),
            "input_b": st.session_state.get("input_b", ""),
            "smi_a": smi_a,
            "smi_b": smi_b,
            "src_a": st.session_state.get("src_a", ""),
            "src_b": st.session_state.get("src_b", ""),
            "conditions": {
                "solvent": st.session_state.get("solvent", ""),
                "temperature": st.session_state.get("temperature", ""),
                "catalyst": st.session_state.get("catalyst", ""),
                "base": st.session_state.get("base", ""),
                "reagents": st.session_state.get("reagents", ""),
                "time_h": st.session_state.get("time_h", ""),
                "atmosphere": st.session_state.get("atmosphere", ""),
                "notes": st.session_state.get("notes", ""),
            },
            "result": pred.to_dict(),
        }
        old = load_record(overwrite_id) if overwrite_id else None
        if old:
            payload["created_at"] = old.get("created_at")
            payload["title"] = old.get("title")

        rid = save_record(payload, record_id=overwrite_id)
        st.session_state["active_record_id"] = rid
        st.session_state["last_predict"] = pred.to_dict()
        st.session_state.pop("last_predict_error", None)
        st.success(f"已保存记录 `{rid}`。结果见下方；也可在「历史记录」随时打开。")
        st.rerun()

    result = _result_from_session()
    if result:
        st.markdown("---")
        st.markdown("### ④ 预测结果")
        _show_result_panel(result, key_prefix="pred")


def page_history():
    st.subheader("历史记录")
    st.caption(
        "反应预测与分子对接均自动保存在本地 data/history/。"
        "可本页展开查看，或加载到对应页改条件重跑。"
    )

    records = list_records()
    if not records:
        st.info("暂无历史。去「反应预测」或「蛋白对接」跑一次即可。")
        return

    for rec in records:
        rid = rec["id"]
        is_dock = (rec.get("type") or "") == "docking"
        with st.container(border=True):
            left, mid, right = st.columns([3, 2, 2])
            with left:
                badge = "对接" if is_dock else "反应"
                st.markdown(f"**[{badge}] {rec.get('title', rid)}**")
                st.caption(
                    f"ID `{rid}` · 更新 {rec.get('updated_at','')} · {rec.get('engine','')}"
                )
                if is_dock:
                    st.code(
                        f"配体: {rec.get('smi_a') or rec.get('input_a') or ''}\n"
                        f"受体: {rec.get('input_b') or ''}\n"
                        f"最佳亲和力: {rec.get('best_affinity')} kcal/mol",
                        language=None,
                    )
                else:
                    st.code(
                        f"{rec.get('input_a','')} + {rec.get('input_b','')}\n"
                        f"主产物: {rec.get('main_product','')}",
                        language=None,
                    )
            with mid:
                if st.button("本页查看", key=f"view_{rid}", use_container_width=True):
                    st.session_state["history_view_id"] = rid
                    st.rerun()
                if is_dock:
                    if st.button(
                        "加载到对接页",
                        key=f"load_dock_{rid}",
                        use_container_width=True,
                    ):
                        full = load_record(rid)
                        if not full:
                            st.error("记录文件丢失")
                        else:
                            dock = full.get("dock") or {}
                            lig = dock.get("ligand_smiles") or full.get("smi_a") or ""
                            st.session_state["dock_ligand_smi"] = lig
                            st.session_state["protein_ligand_smi"] = lig
                            st.session_state["last_dock"] = dock
                            if dock.get("record_id") is None:
                                dock["record_id"] = rid
                            st.session_state["_dock_saved_id"] = rid
                            st.session_state["nav_goto"] = "蛋白对接"
                            st.success("已加载对接结果。请切换到「蛋白对接」。")
                            st.rerun()
                else:
                    if st.button(
                        "加载到预测页", key=f"load_{rid}", use_container_width=True
                    ):
                        full = load_record(rid)
                        if not full:
                            st.error("记录文件丢失")
                        else:
                            st.session_state["active_record_id"] = rid
                            st.session_state["_pending_reactant_a"] = {
                                "display": full.get("input_a", "") or full.get("smi_a", ""),
                                "smiles": full.get("smi_a", ""),
                                "src": full.get("src_a", "") or "history",
                            }
                            st.session_state["_pending_reactant_b"] = {
                                "display": full.get("input_b", "") or full.get("smi_b", ""),
                                "smiles": full.get("smi_b", ""),
                                "src": full.get("src_b", "") or "history",
                            }
                            cond = full.get("conditions") or {}
                            for k in (
                                "solvent",
                                "temperature",
                                "catalyst",
                                "base",
                                "reagents",
                                "time_h",
                                "atmosphere",
                                "notes",
                            ):
                                if k in cond:
                                    st.session_state[k] = cond[k]
                            st.session_state["last_predict"] = full.get("result")
                            st.session_state.pop("last_predict_error", None)
                            st.success("已加载。请切换到「反应预测」查看下方结果。")
                            st.rerun()
                if rec.get("main_product") and not is_dock:
                    b1, b2 = st.columns(2)
                    with b1:
                        st.button(
                            "产物→A",
                            key=f"hist_a_{rid}",
                            use_container_width=True,
                            on_click=_fill_reactant,
                            args=(rec["main_product"], "a", "历史主产物"),
                        )
                    with b2:
                        st.button(
                            "产物→B",
                            key=f"hist_b_{rid}",
                            use_container_width=True,
                            on_click=_fill_reactant,
                            args=(rec["main_product"], "b", "历史主产物"),
                        )
                elif is_dock and (rec.get("smi_a") or rec.get("main_product")):
                    smi = rec.get("smi_a") or rec.get("main_product")
                    if st.button(
                        "配体→对接页",
                        key=f"hist_dock_lig_{rid}",
                        use_container_width=True,
                    ):
                        st.session_state["dock_ligand_smi"] = smi
                        st.session_state["protein_ligand_smi"] = smi
                        st.session_state["nav_goto"] = "蛋白对接"
                        st.rerun()
            with right:
                if st.button("删除", key=f"del_{rid}", use_container_width=True):
                    delete_record(rid)
                    if st.session_state.get("active_record_id") == rid:
                        st.session_state["active_record_id"] = None
                    if st.session_state.get("history_view_id") == rid:
                        st.session_state["history_view_id"] = None
                    st.rerun()

    view_id = st.session_state.get("history_view_id")
    if view_id:
        st.markdown("---")
        st.markdown(f"### 查看记录 `{view_id}`")
        full = load_record(view_id)
        if not full:
            st.error("记录文件丢失")
        elif (full.get("type") or "") == "docking":
            dock = full.get("dock") or {}
            best = dock.get("best_affinity")
            st.metric("最佳结合能 (kcal/mol)", best)
            st.caption(
                f"配体：`{dock.get('ligand_smiles')}` · "
                f"双铜：{bool(dock.get('add_tyr_coppers'))} · "
                f"耗时 {dock.get('elapsed_s')} s"
            )
            poses = dock.get("poses") or []
            if poses:
                st.dataframe(poses, use_container_width=True, hide_index=True)
            box = dock.get("box") or {}
            if box:
                st.json({"box": box, "metal_info": dock.get("metal_info") or {}})
            pose_path = Path(dock.get("out_pdbqt") or "")
            if pose_path.is_file():
                st.download_button(
                    "下载 pose PDBQT",
                    data=pose_path.read_bytes(),
                    file_name=pose_path.name,
                    key=f"hist_dock_dl_{view_id}",
                )
            else:
                st.caption(f"工作目录：`{dock.get('work_dir')}`（本地文件可能已清理）")
        else:
            try:
                result_raw = full.get("result") or {}
                if result_raw.get("nmr"):
                    st.session_state[f"nmr_view_histview_{view_id}"] = result_raw["nmr"]
                res = _dict_to_result(result_raw)
                _show_result_panel(res, key_prefix=f"histview_{view_id}")
            except Exception as exc:  # noqa: BLE001
                # 勿吞掉 Streamlit 的 rerun / stop
                try:
                    from streamlit.runtime.scriptrunner import RerunException, StopException

                    if isinstance(exc, (RerunException, StopException)):
                        raise
                except ImportError:
                    if type(exc).__name__ in ("RerunException", "StopException", "RerunData"):
                        raise
                st.error(f"无法显示该记录：{exc}")
                st.json(full.get("result") or {})


def page_pathway():
    st.subheader("多步路径对比出图")
    text = st.text_area(
        "路径文本",
        value="# 路线 A\nCCO -> CC=O -> CC(=O)O\n\n# 路线 B\nCCO -> CCOC(=O)C -> CC(=O)O\n",
        height=180,
    )
    title = st.text_input("图标题", value="路径对比")
    if st.button("生成对比图", type="primary"):
        try:
            routes = parse_routes_text(text)
            img = render_comparison(routes, header=title)
            img.save(OUT / "ui_pathway.png")
            st.image(img, use_container_width=True)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            st.download_button(
                "下载 PNG",
                data=buf.getvalue(),
                file_name="pathway_compare.png",
                mime="image/png",
            )
        except Exception as exc:  # noqa: BLE001
            st.error(str(exc))


def page_db_lookup():
    st.subheader("分子库查询（PubChem / ChEMBL）")
    st.caption("免费 REST，无需 Key。支持中文名 / 英文名 / SMILES / CHEMBL ID。")
    q = st.text_input("查询内容", value="阿司匹林", placeholder="例如：对醛基苯甲酸 / aspirin / CCO / CHEMBL25")
    c1, c2, c3 = st.columns(3)
    with c1:
        do_pc = st.checkbox("查 PubChem", value=True)
    with c2:
        do_ch = st.checkbox("查 ChEMBL", value=True)
    with c3:
        sim = st.slider("ChEMBL 相似度阈值", 40, 100, 80)

    if st.button("开始查询", type="primary", use_container_width=True):
        if not q.strip():
            st.error("请输入查询内容")
            return
        from chem_apis import chembl_lookup, lookup_both, pubchem_lookup

        with st.spinner("正在查询公共数据库…"):
            if do_pc and do_ch:
                result = lookup_both(q.strip())
                pc, ch = result["pubchem"], result["chembl"]
            elif do_pc:
                pc, ch = pubchem_lookup(q.strip()), None
            else:
                pc, ch = None, chembl_lookup(q.strip(), similarity_cutoff=sim)

        if pc is not None:
            st.markdown("### PubChem")
            if not pc.get("ok"):
                st.warning(pc.get("error"))
            else:
                left, right = st.columns([1, 2])
                with left:
                    img = mol_image(pc.get("smiles") or "", size=(280, 220))
                    if img:
                        st.image(img, use_container_width=True)
                with right:
                    st.markdown(f"**CID:** [{pc.get('cid')}]({pc.get('url')})")
                    st.code(pc.get("smiles") or "", language=None)
                    st.write(
                        {
                            "分子式": pc.get("formula"),
                            "分子量": pc.get("mw"),
                            "IUPAC": pc.get("iupac"),
                            "XLogP": pc.get("xlogp"),
                            "TPSA": pc.get("tpsa"),
                            "HBD/HBA": f"{pc.get('hbd')}/{pc.get('hba')}",
                        }
                    )
                    if pc.get("synonyms"):
                        st.caption("同义词：" + "；".join(pc["synonyms"][:12]))
                    b1, b2, b3 = st.columns(3)
                    with b1:
                        st.button(
                            "用作原料 A",
                            key="pc_as_a",
                            on_click=_fill_reactant,
                            args=(pc["smiles"], "a", q.strip()),
                        )
                    with b2:
                        st.button(
                            "用作原料 B",
                            key="pc_as_b",
                            on_click=_fill_reactant,
                            args=(pc["smiles"], "b", q.strip()),
                        )
                    with b3:
                        st.button(
                            "添加为对接配体",
                            key="pc_as_dock",
                            type="primary",
                            on_click=_fill_dock_ligand,
                            args=(pc["smiles"], q.strip() or "PubChem"),
                        )

        if ch is not None:
            st.markdown("### ChEMBL")
            if not ch.get("ok"):
                st.warning(ch.get("error"))
            else:
                st.markdown(
                    f"**ID:** [{ch.get('chembl_id')}]({ch.get('url')})  ·  "
                    f"**名称:** {ch.get('pref_name') or '—'}"
                )
                st.code(ch.get("smiles") or "", language=None)
                if ch.get("similar"):
                    st.markdown("#### 相似分子")
                    st.dataframe(ch["similar"], use_container_width=True)
                if ch.get("activities"):
                    st.markdown("#### 活性记录（节选）")
                    st.dataframe(ch["activities"], use_container_width=True)


def page_protein():
    """蛋白/酶结构下载 + 便携 AutoDock Vina 对接。"""
    from protein_fetch import (
        fetch_alphafold,
        fetch_rcsb_pdb,
        list_presets,
        resolve_uniprot_query,
        search_rcsb_text,
    )

    st.subheader("蛋白 / 酶结构 + 分子对接（Vina）")
    st.caption(
        "从 RCSB PDB / AlphaFold 下载结构，再用便携 AutoDock Vina "
        "把**预测产物 SMILES**对接到蛋白口袋，输出结合能与 pose。"
    )

    # 当前预测主产物作为配体上下文
    ligand_smi = ""
    try:
        pred = _result_from_session()
        if pred and pred.products:
            main = next(
                (p for p in pred.products if getattr(p, "role", "") == "product"),
                pred.products[0],
            )
            ligand_smi = (main.smiles or "").strip()
    except Exception:  # noqa: BLE001
        ligand_smi = ""

    st.markdown("**配体（预测主产物，可选）**")
    ligand_smi = st.text_input(
        "配体 SMILES",
        value=ligand_smi or st.session_state.get("protein_ligand_smi", ""),
        key="protein_ligand_smi",
        help="默认取最近一次预测主产物；可手动改",
    )
    if ligand_smi.strip():
        img = mol_image(ligand_smi.strip(), size=(220, 160))
        if img:
            st.image(img, width=220)

    st.markdown("---")
    mode = st.radio(
        "结构来源",
        [
            "常用酶/蛋白酶预设",
            "PDB ID 下载",
            "AlphaFold（UniProt / 基因名）",
            "RCSB 关键词搜索",
        ],
        horizontal=True,
        key="protein_mode",
    )

    result = None
    presets = list_presets()

    if mode == "常用酶/蛋白酶预设":
        labels = {
            p["key"]: f"{p['name']}  ·  "
            + (f"PDB {p['pdb']}" if p.get("pdb") else "无实验 PDB")
            + f"  ·  UniProt {p['uniprot']}"
            for p in presets
        }
        key = st.selectbox(
            "选择靶点",
            options=[p["key"] for p in presets],
            format_func=lambda k: labels.get(k, k),
            key="protein_preset_key",
        )
        preset = next(p for p in presets if p["key"] == key)
        st.caption(preset.get("note") or "")
        src_opts = []
        if preset.get("pdb"):
            src_opts.append("RCSB 实验结构 (PDB)")
        src_opts.append("AlphaFold 预测结构（推荐人源 TYR）")
        src = st.radio(
            "下载哪一份",
            src_opts,
            horizontal=True,
            key="protein_preset_src",
        )
        fmt = "pdb"
        if src.startswith("RCSB"):
            fmt = st.selectbox("文件格式", ["pdb", "cif"], key="protein_fmt_preset")
        if st.button("下载结构", type="primary", key="protein_dl_preset", use_container_width=True):
            with st.spinner("正在从公共库下载…"):
                try:
                    if src.startswith("RCSB"):
                        if not preset.get("pdb"):
                            st.error("该预设无实验 PDB，请改选 AlphaFold")
                        else:
                            result = fetch_rcsb_pdb(preset["pdb"], fmt=fmt)
                            result["preset_name"] = preset["name"]
                    else:
                        result = fetch_alphafold(preset["uniprot"])
                        result["preset_name"] = preset["name"]
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

    elif mode == "PDB ID 下载":
        pdb_id = st.text_input("PDB ID", value="6LU7", key="protein_pdb_id")
        fmt = st.selectbox("文件格式", ["pdb", "cif"], key="protein_fmt_id")
        if st.button("从 RCSB 下载", type="primary", key="protein_dl_pdb", use_container_width=True):
            with st.spinner(f"下载 {pdb_id} …"):
                try:
                    result = fetch_rcsb_pdb(pdb_id, fmt=fmt)
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

    elif mode == "AlphaFold（UniProt / 基因名）":
        st.info(
            "**人源酪氨酸酶**请用 UniProt **`P14679`**（基因 **TYR**）。"
            "你输入的 `HTYR` 不是 Accession。"
            "也可填基因名 `TYR` / `酪氨酸酶` 点「解析」。"
        )
        uid = st.text_input(
            "UniProt Accession / 基因名 / 蛋白名",
            value="P14679",
            key="protein_uniprot",
            help="例：P14679、TYR、酪氨酸酶；不要填 HTYR",
        )
        c_res, c_dl = st.columns(2)
        with c_res:
            if st.button("解析基因/蛋白名 → UniProt", key="protein_resolve_uid"):
                with st.spinner("查询 UniProt…"):
                    hits = resolve_uniprot_query(uid)
                st.session_state["protein_uniprot_hits"] = hits
                if not hits:
                    st.warning("未找到。人源酪氨酸酶请试：TYR 或 P14679")
        hits = st.session_state.get("protein_uniprot_hits") or []
        if hits:
            st.dataframe(hits, use_container_width=True, hide_index=True)
            uid = st.selectbox(
                "选择 Accession 下载 AlphaFold",
                options=[h["uniprot"] for h in hits],
                key="protein_uid_pick",
            )
        with c_dl:
            pass
        if st.button(
            "从 AlphaFold 下载",
            type="primary",
            key="protein_dl_af",
            use_container_width=True,
        ):
            with st.spinner(f"下载 AlphaFold {uid} …"):
                try:
                    import re as _re

                    acc = (uid or "").strip()
                    from protein_fetch import _UNIPROT_ACC

                    raw = _re.sub(r"[^A-Za-z0-9]", "", acc).upper()
                    if not _UNIPROT_ACC.match(raw):
                        resolved = resolve_uniprot_query(acc)
                        if not resolved:
                            raise ValueError(
                                f"无法解析 {acc!r}。人源酪氨酸酶请用 P14679 或基因名 TYR"
                            )
                        acc = resolved[0]["uniprot"]
                        st.caption(
                            f"已解析为 UniProt `{acc}`（{resolved[0].get('name') or ''}）"
                        )
                    result = fetch_alphafold(acc)
                except Exception as exc:  # noqa: BLE001
                    st.error(str(exc))

    else:
        q = st.text_input(
            "RCSB 关键词",
            value="human tyrosinase",
            key="protein_search_q",
        )
        if st.button("搜索 PDB", type="secondary", key="protein_search_go"):
            with st.spinner("RCSB 检索中…"):
                hits = search_rcsb_text(q, limit=10)
            st.session_state["protein_search_hits"] = hits
        hits = st.session_state.get("protein_search_hits") or []
        if hits:
            st.dataframe(hits, use_container_width=True, hide_index=True)
            pick = st.selectbox(
                "选择条目下载",
                options=[h["pdb_id"] for h in hits],
                key="protein_search_pick",
            )
            st.caption(
                "提示：搜 human tyrosinase 常出 **TYRP1**（如 5M8O），"
                "不是 TYR 本身；TYR 请用 AlphaFold P14679。"
            )
            if st.button("下载选中 PDB", type="primary", key="protein_dl_search"):
                with st.spinner(f"下载 {pick} …"):
                    try:
                        result = fetch_rcsb_pdb(pick, fmt="pdb")
                    except Exception as exc:  # noqa: BLE001
                        st.error(str(exc))

    if result and result.get("ok"):
        st.session_state["last_protein"] = result
        lib = st.session_state.setdefault("protein_library", [])
        # 去重追加到可切换列表
        entry = {
            "label": (
                f"{result.get('preset_name') or result.get('pdb_id') or result.get('uniprot') or Path(result['path']).name}"
                f" · {Path(result['path']).name}"
            ),
            "path": result["path"],
            "format": result.get("format") or "pdb",
            "source": result.get("source") or "",
            "pdb_id": result.get("pdb_id") or "",
            "uniprot": result.get("uniprot") or "",
            "preset_name": result.get("preset_name") or "",
        }
        lib = [x for x in lib if x.get("path") != entry["path"]]
        lib.insert(0, entry)
        st.session_state["protein_library"] = lib[:20]
        st.session_state["dock_receptor_path"] = entry["path"]
        st.session_state["dock_receptor_select"] = entry["label"]
        # 不清除 last_dock：换酶后仍可改配体/再对接；旧结果已自动进历史
        st.success(
            f"已保存：`{result.get('path')}`  ·  {result.get('source')}  ·  "
            f"{result.get('bytes', 0)} bytes"
        )
        meta = result.get("meta") or {}
        if result.get("preset_name"):
            st.markdown(f"**预设：** {result['preset_name']}")
        if meta.get("title") or meta.get("uniprotDescription"):
            st.markdown(f"**标题/描述：** {meta.get('title') or meta.get('uniprotDescription')}")
        info_bits = []
        if result.get("pdb_id"):
            info_bits.append(f"PDB `{result['pdb_id']}`")
        if result.get("uniprot"):
            info_bits.append(f"UniProt `{result['uniprot']}`")
        if meta.get("method"):
            info_bits.append(f"方法 {meta['method']}")
        if meta.get("resolution"):
            info_bits.append(f"分辨率 {meta['resolution']}")
        if meta.get("organism"):
            info_bits.append(meta["organism"])
        if info_bits:
            st.caption(" · ".join(str(x) for x in info_bits))

        b1, b2, b3 = st.columns(3)
        with b1:
            if result.get("page"):
                st.link_button("打开数据库页", result["page"], use_container_width=True)
        with b2:
            if result.get("viewer"):
                st.link_button("3D 查看", result["viewer"], use_container_width=True)
        with b3:
            path = Path(result["path"])
            if path.is_file():
                st.download_button(
                    f"下载 .{result.get('format') or 'pdb'}",
                    data=path.read_bytes(),
                    file_name=path.name,
                    mime="chemical/x-pdb",
                    use_container_width=True,
                    key="protein_file_dl",
                )

        with st.expander("文件头预览", expanded=False):
            st.code(result.get("preview") or "", language=None)

    # —— 对接区：准备 → 计算 → 分析 ——
    st.markdown("---")
    st.markdown("### 分子对接（准备 → 计算 → 分析）")
    st.caption(
        "流程对齐 AutoDock / Vina 常规步骤："
        "**① 准备**受体·配体（去水、补氢、PDBQT、TYR 补双铜）→ "
        "**② 计算**文献 Grid Box + Vina → "
        "**③ 分析**结合能 / 口袋残基 / **PyMOL 可视化**。"
    )
    try:
        import importlib

        import docking as _dm0

        _dm0 = importlib.reload(_dm0)
        vina_path = _dm0.ensure_vina()
        st.caption(f"计算引擎：`{_dm0.vina_version()}` · `{vina_path}`")
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Vina 尚未就绪（点「开始对接」时会自动下载）：{exc}")

    try:
        _dv = _load_dock_viz()
        RECOMMENDED_BOX_SIZE = _dv.RECOMMENDED_BOX_SIZE
        if _dv.has_embedded_pymol():
            st.caption("出版图引擎：内嵌 PyMOL（pymol2）已就绪 · 对接后自动渲染 fig1/fig2 PNG")
        else:
            _pymol = _dv.find_pymol_exe()
            if _pymol:
                st.caption(f"PyMOL 已检测到：`{_pymol}`（分析阶段可一键打开）")
            else:
                st.caption("未检测到 PyMOL：将用分析示意图兜底。")
    except Exception:  # noqa: BLE001
        RECOMMENDED_BOX_SIZE = {
            "tyr_cu_mid": {"size": 25.0, "cite": "TYR 双铜口袋 25 Å"},
            "tyrp1_zn_5m8o": {"size": 22.0, "cite": "5M8O 双锌 22 Å"},
            "auto": {"size": 22.0, "cite": "通用 22 Å"},
            "manual": {"size": 25.0, "cite": "手动"},
        }

    lib = st.session_state.get("protein_library") or []
    # 兼容：只有 last_protein 时也放进列表
    last = st.session_state.get("last_protein")
    if last and last.get("path") and not any(
        x.get("path") == last["path"] for x in lib
    ):
        lib = [
            {
                "label": f"{last.get('pdb_id') or last.get('uniprot') or Path(last['path']).name}",
                "path": last["path"],
                "format": last.get("format") or "pdb",
                "source": last.get("source") or "",
                "pdb_id": last.get("pdb_id") or "",
                "uniprot": last.get("uniprot") or "",
                "preset_name": last.get("preset_name") or "",
            }
        ] + list(lib)
        st.session_state["protein_library"] = lib

    if not lib:
        st.info(
            "① 先在上方下载蛋白（人源 TYR 用 AlphaFold P14679；或 6LU7）→ "
            "② 在本区切换受体 / 修饰 → ③ 开始对接。"
        )
    else:
        labels = [x["label"] for x in lib]
        paths = [x["path"] for x in lib]
        cur = st.session_state.get("dock_receptor_path") or paths[0]
        if cur not in paths:
            cur = paths[0]
        idx = paths.index(cur)
        pick_label = st.selectbox(
            "对接用受体（可随时换酶，结果区不挡操作）",
            options=labels,
            index=idx,
            key="dock_receptor_select",
        )
        prot = lib[labels.index(pick_label)]
        st.session_state["dock_receptor_path"] = prot["path"]

        pdb_path = Path(prot["path"])
        if not pdb_path.is_file():
            st.warning(f"蛋白文件丢失：{pdb_path}")
        elif (prot.get("format") or "pdb").lower() == "cif":
            st.warning("对接目前支持 **PDB** 格式；请重新下载时选 pdb。")
        else:
            st.success(
                f"当前受体：`{pdb_path.name}` · {prot.get('source') or ''} · "
                f"{prot.get('preset_name') or prot.get('pdb_id') or prot.get('uniprot') or ''}"
            )

            st.markdown("#### ① 准备：受体与配体")
            st.caption(
                "对应 ADT：去水 / 去无关配体 → 加氢 → 保存 PDBQT；"
                "人源 TYR（AlphaFold）另需补双铜活性中心。"
            )
            looks_tyr = any(
                s in (pdb_path.name.upper() + str(prot.get("uniprot") or "").upper()
                      + str(prot.get("preset_name") or "").upper())
                for s in ("P14679", "TYR", "酪氨酸", "AF-P14679")
            )
            if "dock_add_cu" not in st.session_state:
                st.session_state["dock_add_cu"] = bool(looks_tyr)
            # 切到 TYR 时默认勾选；切到非 TYR 不强行取消（用户可手动关）
            if looks_tyr and not st.session_state.get("_dock_cu_tyr_hint"):
                st.session_state["dock_add_cu"] = True
                st.session_state["_dock_cu_tyr_hint"] = True
            add_cu = st.checkbox(
                "补人源酪氨酸酶双铜离子 CuA/CuB（His180/202/211 + His363/367/390）",
                key="dock_add_cu",
                help=(
                    "AlphaFold TYR 不含金属；文献活性口袋依赖双铜与底物结合。"
                    "开启后按配位 His 几何中心放置 2×Cu，并对准口袋中心对接。"
                    "Vina 中 Cu 以 Zn 原子类型近似（力和几何粗筛）。"
                ),
            )
            if add_cu:
                st.caption(
                    "将生成 `*_Cu2.pdb`（双铜 HETATM），"
                    "对接盒子默认对准两铜中点。结构补全 ≠ 量子化学精确配位。"
                )
            else:
                st.caption("未勾选时：去水去配体后由 Meeko 补极性氢 → PDBQT。")

            st.markdown("**配体准备**")
            if "dock_ligand_smi" not in st.session_state:
                st.session_state["dock_ligand_smi"] = (
                    ligand_smi or st.session_state.get("protein_ligand_smi") or ""
                ).strip()
            sync_c1, sync_c2 = st.columns([3, 1])
            with sync_c2:
                if st.button(
                    "← 用上方配体",
                    key="dock_sync_lig",
                    use_container_width=True,
                    help="把页顶「配体 SMILES」同步到此处",
                ):
                    top = (st.session_state.get("protein_ligand_smi") or "").strip()
                    if top:
                        st.session_state["dock_ligand_smi"] = top
                        st.rerun()
            with sync_c1:
                dock_lig = st.text_input(
                    "对接用 SMILES（加氢 · 多构象 · 扭转键由 Meeko 检测）",
                    key="dock_ligand_smi",
                    help="改这里即可换化合物再对接；不必清除下方结果",
                )
            if (dock_lig or "").strip():
                img2 = mol_image(dock_lig.strip(), size=(200, 140))
                if img2:
                    st.image(img2, width=200)

            with st.expander("前处理对照（vs AutoDock Tools）", expanded=False):
                st.markdown(
                    """
| 步骤 | ADT / PyMOL 手工 | 本工具自动 |
|------|------------------|------------|
| 去水 / 去共晶配体 | PyMOL 删 HOH、配体 | `_clean_receptor_pdb` |
| 只留研究链 | 手工删链 | 当前 PDB 原样（请下载时选好） |
| 加氢 | Edit → Hydrogens → Add | Meeko 补极性 H |
| 金属 | 手工保留 | 保留；TYR 可补双铜 |
| 配体扭转键 | Torsion Tree → Detect | Meeko 自动 |
| 输出 | `.pdbqt` | 同左 |
"""
                )

            st.markdown("#### ② 计算：Grid Box + Vina")
            st.caption(
                "对应 ADT：定义活性位点盒子 → 载入受体/配体 PDBQT → 运行 Vina。"
            )

            import importlib

            import docking as _docking_mod

            if not hasattr(_docking_mod, "BOX_STRATEGIES"):
                _docking_mod = importlib.reload(_docking_mod)
            BOX_STRATEGIES = getattr(_docking_mod, "BOX_STRATEGIES", None) or {
                "auto": {
                    "label": "自动推断（金属 → 共晶配体 → 蛋白几何中心）",
                    "cite": "本工具启发式；有金属时优先金属中心",
                },
                "tyr_cu_mid": {
                    "label": "人源 TYR：双铜中点（补 Cu 后）",
                    "size": 25.0,
                    "cite": "Cu–Cu 中点 · 25 Å（Vecura/gnina TYR 流程）",
                },
                "tyrp1_zn_5m8o": {
                    "label": "TYRP1 5M8O：晶体双锌中点",
                    "center": (-11.020, 0.347, -23.444),
                    "size": 22.0,
                    "cite": "PDB 5M8O Zn513/514 中点；Lai et al. 2017",
                },
                "manual": {
                    "label": "手动精确坐标 (Å)",
                    "cite": "用户指定 center / size",
                },
            }

            default_strat = "auto"
            stem_u = pdb_path.name.upper() + str(prot.get("pdb_id") or "").upper()
            if add_cu or looks_tyr:
                default_strat = "tyr_cu_mid"
            elif "5M8O" in stem_u or "5M8M" in stem_u:
                default_strat = "tyrp1_zn_5m8o"
            if "dock_box_strategy" not in st.session_state:
                st.session_state["dock_box_strategy"] = default_strat
            hint_key = f"_box_hint_{pdb_path.name}_{bool(add_cu)}"
            if not st.session_state.get(hint_key):
                st.session_state["dock_box_strategy"] = default_strat
                st.session_state[hint_key] = True

            strat_keys = list(BOX_STRATEGIES.keys())
            strat = st.selectbox(
                "活性口袋 / Grid Box 策略（文献支撑）",
                options=strat_keys,
                format_func=lambda k: BOX_STRATEGIES[k]["label"],
                key="dock_box_strategy",
            )
            try:
                _dv = _load_dock_viz()
                LITERATURE_BOXES = _dv.LITERATURE_BOXES
                lit = LITERATURE_BOXES.get(strat) or {}
            except Exception:  # noqa: BLE001
                lit = {}
            rec_box = RECOMMENDED_BOX_SIZE.get(strat) or RECOMMENDED_BOX_SIZE.get("auto")
            rec_size = float(
                (lit.get("size") or (None,))[0]
                if isinstance(lit.get("size"), (list, tuple))
                else ((rec_box or {}).get("size") or 22.0)
            )
            # 文献卡片：位置 + 大小 + 论文全名（必须精确）
            with st.container(border=True):
                st.markdown("##### 文献推荐 Grid Box（请优先一键套用）")
                st.markdown(
                    f"**尺寸（完美推荐）：`{rec_size:.0f} × {rec_size:.0f} × {rec_size:.0f} Å`**"
                )
                ctr = lit.get("center")
                if ctr:
                    st.markdown(
                        f"**中心（完美推荐）：`({ctr[0]:.3f}, {ctr[1]:.3f}, {ctr[2]:.3f})` Å**"
                    )
                    st.caption(lit.get("center_note") or "")
                else:
                    st.markdown(
                        f"**中心：** {lit.get('center_note') or '对接时由双铜/金属自动写入'}"
                    )
                st.markdown(
                    f"**文献全名：** *{lit.get('paper') or BOX_STRATEGIES.get(strat, {}).get('paper') or '—'}*"
                )
                st.caption(
                    f"{lit.get('authors') or ''} · {lit.get('journal') or ''} · "
                    f"{lit.get('year') or ''}"
                )
                if lit.get("doi_or_url"):
                    st.markdown(f"[打开文献 / DOI]({lit['doi_or_url']})")
                if lit.get("detail"):
                    st.caption(lit["detail"])
                for er in lit.get("extra_refs") or []:
                    st.caption(f"另见：*{er.get('paper')}* — {er.get('note')}")

                if st.button(
                    "一键套用文献精确盒子（中心+边长）",
                    type="primary",
                    key="dock_apply_lit_box",
                    use_container_width=True,
                    help="把滑块/手动坐标改成上方文献推荐值，避免盒子偏了",
                ):
                    st.session_state["dock_box"] = int(rec_size)
                    st.session_state[f"_size_hint_{strat}"] = True
                    if ctr:
                        st.session_state["dock_box_strategy"] = "manual"
                        st.session_state["dock_cx"] = float(ctr[0])
                        st.session_state["dock_cy"] = float(ctr[1])
                        st.session_state["dock_cz"] = float(ctr[2])
                        st.session_state["dock_sx"] = float(rec_size)
                        st.session_state["dock_sy"] = float(rec_size)
                        st.session_state["dock_sz"] = float(rec_size)
                        st.session_state["_lit_box_toast"] = (
                            f"已套用文献盒子 center=({ctr[0]:.3f},{ctr[1]:.3f},{ctr[2]:.3f}) "
                            f"size={rec_size:.0f}³ Å · {lit.get('paper','')[:60]}"
                        )
                    else:
                        # TYR / auto：保持策略，只锁定边长
                        st.session_state["_lit_box_toast"] = (
                            f"已锁定文献边长 {rec_size:.0f} Å；"
                            f"中心将按「{BOX_STRATEGIES.get(strat, {}).get('label')}」自动写入"
                        )
                    st.rerun()
                toast = st.session_state.pop("_lit_box_toast", None)
                if toast:
                    st.success(toast)

            # 策略变化时把滑块推到文献推荐值（仅推一次）
            size_hint = f"_size_hint_{strat}"
            if not st.session_state.get(size_hint):
                st.session_state["dock_box"] = int(rec_size)
                st.session_state[size_hint] = True

            c_ex, c_nm, c_box = st.columns(3)
            with c_ex:
                exhaust = st.slider(
                    "exhaustiveness（搜索充分度）",
                    1,
                    32,
                    16,
                    key="dock_ex",
                    help="对应 ADT「对接次数」思路：越大越可靠、越慢；建议 ≥16",
                )
            with c_nm:
                nmodes = st.slider("输出构象数", 1, 20, 9, key="dock_nm")
            with c_box:
                box_size = st.slider(
                    "盒子边长 Å（立方）",
                    12,
                    40,
                    int(rec_size),
                    key="dock_box",
                    help=f"文献推荐本策略用 {rec_size:.0f} Å",
                )

            box_center_arg = None
            box_size_xyz = None
            if strat == "manual":
                mc1, mc2, mc3 = st.columns(3)
                with mc1:
                    cx = st.number_input(
                        "center_x", value=-11.020, format="%.3f", key="dock_cx"
                    )
                with mc2:
                    cy = st.number_input(
                        "center_y", value=0.347, format="%.3f", key="dock_cy"
                    )
                with mc3:
                    cz = st.number_input(
                        "center_z", value=-23.444, format="%.3f", key="dock_cz"
                    )
                s1, s2, s3 = st.columns(3)
                with s1:
                    sx = st.number_input(
                        "size_x",
                        value=float(box_size),
                        min_value=8.0,
                        max_value=60.0,
                        key="dock_sx",
                    )
                with s2:
                    sy = st.number_input(
                        "size_y",
                        value=float(box_size),
                        min_value=8.0,
                        max_value=60.0,
                        key="dock_sy",
                    )
                with s3:
                    sz = st.number_input(
                        "size_z",
                        value=float(box_size),
                        min_value=8.0,
                        max_value=60.0,
                        key="dock_sz",
                    )
                box_center_arg = (float(cx), float(cy), float(cz))
                box_size_xyz = (float(sx), float(sy), float(sz))
                st.caption("可粘贴文献 grid；默认预填 5M8O 双锌中点便于对照。")
            elif strat == "tyr_cu_mid":
                st.caption(
                    "中心将在对接时由补铜后的 CuA/CuB 中点自动写入 "
                    f"（边长采用 {box_size} Å）。"
                )
            elif strat == "tyrp1_zn_5m8o":
                st.caption(
                    "中心固定为 5M8O 晶体 Zn 中点 (-11.020, 0.347, -23.444)，"
                    f"边长 {box_size} Å。"
                )

            b_run, b_clear = st.columns([3, 1])
            with b_run:
                do_run = st.button(
                    "🚀 运行对接计算（准备 PDBQT → Vina）",
                    type="primary",
                    key="dock_run",
                    use_container_width=True,
                    disabled=not bool((dock_lig or "").strip()),
                )
            with b_clear:
                if st.button("清除本页结果", key="dock_clear", use_container_width=True):
                    st.session_state.pop("last_dock", None)
                    st.rerun()

            if do_run:
                with st.spinner(
                    "对接中：①修饰 → ②蛋白/配体前处理 → ③Vina…"
                ):
                    try:
                        import importlib

                        import docking as _dm

                        _dm = importlib.reload(_dm)
                        run_docking = _dm.run_docking
                        vina_version = _dm.vina_version

                        st.caption(f"引擎：{vina_version()}")
                        dock = run_docking(
                            pdb_path,
                            dock_lig.strip(),
                            exhaustiveness=int(exhaust),
                            num_modes=int(nmodes),
                            box_size=float(box_size),
                            box_center=box_center_arg,
                            box_size_xyz=box_size_xyz,
                            box_strategy=str(strat),
                            add_tyr_coppers=bool(add_cu),
                            job_name=str(
                                prot.get("pdb_id")
                                or prot.get("uniprot")
                                or pdb_path.stem
                            ),
                        )
                        try:
                            rid = save_dock_record(dock)
                            dock["record_id"] = rid
                            st.session_state["_dock_saved_id"] = rid
                        except Exception as save_exc:  # noqa: BLE001
                            st.warning(f"对接完成但自动保存失败：{save_exc}")
                        st.session_state["last_dock"] = dock
                        hist = st.session_state.setdefault("dock_history", [])
                        hist.insert(
                            0,
                            {
                                "best": dock.get("best_affinity"),
                                "ligand": dock.get("ligand_smiles"),
                                "receptor": Path(
                                    str(
                                        dock.get("receptor_used")
                                        or dock.get("receptor_pdb")
                                        or ""
                                    )
                                ).name,
                                "cu": bool(dock.get("add_tyr_coppers")),
                                "box": (dock.get("box") or {}).get("source"),
                                "id": dock.get("record_id") or "",
                                "work": dock.get("work_dir") or "",
                            },
                        )
                        st.session_state["dock_history"] = hist[:30]
                        # 对接后立刻用内嵌 PyMOL 出出版图
                        try:
                            _dv = _load_dock_viz()
                            viz0 = _dv.prepare_dock_visualization(dock)
                            if _dv.has_embedded_pymol():
                                with st.spinner(
                                    "内嵌 PyMOL 正在射线追踪图1/图2（约 1–3 分钟）…"
                                ):
                                    wd = Path(dock.get("work_dir") or ".")
                                    for fn in ("fig1_overview.png", "fig2_pocket.png"):
                                        fp = wd / fn
                                        if fp.is_file() and fp.stat().st_size < 50000:
                                            fp.unlink(missing_ok=True)
                                    rr = _dv.render_publication_pngs_pymol2(
                                        wd,
                                        receptor_pdb=Path(
                                            dock.get("receptor_used")
                                            or dock.get("receptor_pdb")
                                            or ""
                                        ),
                                        ligand_path=Path(
                                            viz0.get("ligand_pdb")
                                            or wd / "lig_pose1.pdb"
                                        ),
                                        contacts=viz0.get("contacts") or {},
                                        width=1200,
                                        height=900,
                                        dpi=300,
                                    )
                                    dock["viz_render"] = rr
                                    st.session_state["last_dock"] = dock
                                    if rr.get("ok"):
                                        st.success(
                                            "PyMOL 出版图已生成（fig1_overview.png / fig2_pocket.png）"
                                        )
                                    else:
                                        st.warning(
                                            f"PyMOL 出图未完成：{rr.get('error') or rr}"
                                        )
                        except Exception as viz_exc:  # noqa: BLE001
                            st.warning(f"自动出图跳过：{viz_exc}")
                        st.rerun()
                    except Exception as exc:  # noqa: BLE001
                        st.error(f"对接失败：{exc}")

            dock = st.session_state.get("last_dock")
            if dock and dock.get("ok"):
                best = dock.get("best_affinity")
                saved = dock.get("record_id") or st.session_state.get(
                    "_dock_saved_id"
                )
                cur_lig = (dock_lig or "").strip()
                prev_lig = (dock.get("ligand_smiles") or "").strip()
                prev_rec = Path(
                    str(dock.get("receptor_pdb") or "")
                ).name
                cur_rec = pdb_path.name
                stale = (cur_lig and cur_lig != prev_lig) or (
                    cur_rec and prev_rec and cur_rec not in str(dock.get("receptor_pdb") or "")
                    and cur_rec not in str(dock.get("receptor_used") or "")
                )
                st.markdown("#### ③ 分析：结合能 · 口袋残基 · PyMOL 可视化")
                st.success(
                    (
                        f"最佳结合能 **{best} kcal/mol** · 耗时 {dock.get('elapsed_s')} s"
                        if best is not None
                        else f"完成 · 耗时 {dock.get('elapsed_s')} s"
                    )
                    + (f" · 已自动存档 `{saved}`" if saved else "")
                )
                if best is not None:
                    if best <= -7:
                        st.caption("经验参考：≤ −7 kcal/mol 通常较好（粗筛阈值，需实验验证）。")
                    elif best <= -6:
                        st.caption("经验参考：≤ −6 kcal/mol 可接受；可加大 exhaustiveness 或核对盒子。")
                    else:
                        st.caption(
                            "结合能偏弱（> −6）：核对双铜/文献盒子，或换 5M8O 对照；"
                            "Vina ≠ 实验 Ki。"
                        )
                st.caption(
                    f"该次用配体：`{prev_lig[:60]}` · 受体：`{prev_rec}`"
                    + (" · 含双铜修饰" if dock.get("add_tyr_coppers") else "")
                )
                if stale:
                    st.warning(
                        "上方配体或受体已改动，下列仍是**上一次**结果；"
                        "改完后点「运行对接」即可刷新（旧结果已在历史里）。"
                    )

                if dock.get("add_tyr_coppers"):
                    mi = dock.get("metal_info") or {}
                    st.info(
                        f"已补双铜 · CuA={tuple(round(x,2) for x in (mi.get('cu_a') or ()))} · "
                        f"CuB={tuple(round(x,2) for x in (mi.get('cu_b') or ()))}"
                    )
                box = dock.get("box") or {}
                center = box.get("center") or (0, 0, 0)
                size = box.get("size") or (22, 22, 22)
                st.markdown(
                    f"**Grid Box（本次实测）** · 策略 `{dock.get('box_strategy') or box.get('strategy') or '—'}` · "
                    f"来源 `{box.get('source')}`  \n"
                    f"- **中心** `({center[0]:.3f}, {center[1]:.3f}, {center[2]:.3f})` Å  \n"
                    f"- **边长** `({size[0]:.1f} × {size[1]:.1f} × {size[2]:.1f})` Å"
                )
                if box.get("paper") or box.get("cite"):
                    st.caption(
                        f"文献：*{box.get('paper') or ''}* · {box.get('cite') or ''}"
                    )
                prep = dock.get("prep") or {}
                if prep:
                    with st.expander("本次前处理报告", expanded=False):
                        rp = prep.get("receptor") or {}
                        lp = prep.get("ligand") or {}
                        st.write(
                            {
                                "受体": rp.get("note"),
                                "ATOM数": rp.get("n_atom"),
                                "金属数": rp.get("n_metals"),
                                "忽略有机HET": rp.get("n_het_ignored"),
                                "配体": lp.get("note"),
                                "构象数": lp.get("n_confs"),
                                "MMFF能量": lp.get("energy"),
                            }
                        )
                poses = dock.get("poses") or []
                if poses:
                    st.markdown("**构象表（按结合能排序，越负越好）**")
                    st.dataframe(poses, use_container_width=True, hide_index=True)

                # —— PyMOL 高颜值作图 / 氢键 / 残基 ——
                st.markdown("**③-B 结合模式可视化（PyMOL 出版图）**")
                st.caption(
                    "PyMOL 右侧菜单：A=Action · S=Show · H=Hide · L=Label · C=Color；"
                    "脚本已按「图1全景 + 图2口袋氢键」流程写好。"
                )
                try:
                    _dv = _load_dock_viz()
                    viz = _dv.prepare_dock_visualization(dock)
                    st.session_state["_dock_viz"] = viz
                    contacts = viz.get("contacts") or {}
                    key_res = contacts.get("key_residues") or []
                    hbonds = contacts.get("hbonds") or []

                    if key_res:
                        st.markdown(
                            f"**关键相互作用残基（4 Å 内最近 {len(key_res)} 个，作图保留）**"
                        )
                        st.dataframe(
                            [
                                {
                                    "残基": r["label"],
                                    "链": r["chain"],
                                    "最近距离 Å": r["min_dist_A"],
                                }
                                for r in key_res
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )
                    if hbonds:
                        st.markdown("**氢键 / 极性接触（键长 ≤ 3.5 Å）**")
                        st.dataframe(
                            [
                                {
                                    "蛋白原子": h["res_atom"],
                                    "配体原子": h["lig_atom"],
                                    "键长 Å": h["distance_A"],
                                }
                                for h in hbonds
                            ],
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.caption("未检测到 ≤3.5 Å 的 N/O/S 极性接触（仍可看 4 Å 残基）。")

                    # 已渲染 PNG 则展示（按钮出图后强制用最新路径）
                    _force = st.session_state.get("_dock_render_force") or {}
                    f1 = Path(
                        _force.get("fig1_png")
                        or viz.get("fig1_png")
                        or Path(dock.get("work_dir") or ".") / "fig1_overview.png"
                    )
                    f2 = Path(
                        _force.get("fig2_png")
                        or viz.get("fig2_png")
                        or Path(dock.get("work_dir") or ".") / "fig2_pocket.png"
                    )
                    eng = _force.get("engine") or (
                        (viz.get("render") or {}).get("engine") or ""
                    )
                    is_pymol = eng in ("pymol2", "cached") or bool(
                        viz.get("pymol_embedded") and eng != "fallback"
                    )
                    # 无 PyMOL 出版图时自动补分析示意图（Cloud 常态）
                    _work_png = Path(dock.get("work_dir") or ".")
                    if (
                        (not f1.is_file() or not f2.is_file() or f1.stat().st_size < 2000)
                        and eng != "pymol2"
                    ):
                        try:
                            _paths0 = _dv.render_fallback_pngs(
                                _work_png,
                                contacts=contacts,
                                affinity=best,
                                box=box,
                                title=prev_rec,
                            )
                            f1 = Path(_paths0.get("fig1_png") or (_work_png / "fig1_overview.png"))
                            f2 = Path(_paths0.get("fig2_png") or (_work_png / "fig2_pocket.png"))
                            if eng != "pymol2":
                                eng = eng or "fallback"
                        except Exception:  # noqa: BLE001
                            pass

                    if f1.is_file() or f2.is_file():
                        st.markdown("**出版图 / 分析图预览**")
                        if eng in ("pymol2", "cached", "pymol_exe") or (
                            is_pymol and f1.is_file() and f1.stat().st_size > 20000
                        ):
                            st.success(
                                "已用**内嵌 PyMOL** 射线追踪渲染。"
                            )
                        else:
                            st.caption(
                                "当前为 **matplotlib 分析示意图**（残基/氢键表）。"
                                "Cloud 无法装 PyMOL；本机 `pip install -r requirements-dock.txt` 可出 3D 射线图。"
                            )
                        ic1, ic2 = st.columns(2)
                        with ic1:
                            if f1.is_file():
                                st.image(
                                    f1.read_bytes(),
                                    caption="图1 (fig1_overview.png)",
                                )
                        with ic2:
                            if f2.is_file():
                                st.image(
                                    f2.read_bytes(),
                                    caption="图2 (fig2_pocket.png)",
                                )
                    else:
                        st.warning("尚未生成 PNG。请点下方「渲染出 PNG」。")

                    # 页内 3D（py3Dmol）
                    try:
                        import py3Dmol
                    except Exception:
                        py3Dmol = None  # type: ignore
                    lig_view = Path(viz.get("ligand_pdb") or "")
                    rec_view = Path(
                        dock.get("receptor_used") or dock.get("receptor_pdb") or ""
                    )
                    if py3Dmol is not None and lig_view.is_file() and rec_view.is_file():
                        with st.expander("页内 3D 预览（py3Dmol）", expanded=False):
                            try:
                                view = py3Dmol.view(width=640, height=420)
                                view.addModel(
                                    rec_view.read_text(encoding="utf-8", errors="replace"),
                                    "pdb",
                                )
                                view.setStyle(
                                    {"model": 0},
                                    {"cartoon": {"color": "lightgray"}},
                                )
                                view.addModel(
                                    lig_view.read_text(encoding="utf-8", errors="replace"),
                                    "pdb",
                                )
                                view.setStyle(
                                    {"model": 1},
                                    {"stick": {"colorscheme": "yellowCarbon"}},
                                )
                                view.zoomTo({"model": 1})
                                html = view._make_html()
                                st.components.v1.html(html, height=440, scrolling=False)
                            except Exception as e3d:  # noqa: BLE001
                                st.caption(f"3D 预览跳过：{e3d}")

                    b1, b2, b3, b4 = st.columns(4)
                    with b1:
                        try:
                            from cloud_env import is_streamlit_cloud as _cloud_render
                        except Exception:
                            _cloud_render = lambda: False  # type: ignore[assignment]
                        _help_render = (
                            "Cloud：生成分析示意图（无 PyMOL 射线追踪）。本机有 pymol-open-source 则出 3D 出版图。"
                            if _cloud_render()
                            else "优先内嵌 PyMOL 射线追踪；否则生成分析示意图。"
                        )
                        if st.button(
                            "渲染出 PNG",
                            type="primary",
                            key="dock_pymol_render",
                            use_container_width=True,
                            help=_help_render,
                        ):
                            _dv_r = _load_dock_viz()
                            ok = False
                            engine = ""
                            work_d = Path(dock.get("work_dir") or ".")
                            work_d.mkdir(parents=True, exist_ok=True)
                            spin_msg = (
                                "正在生成分析 PNG（Cloud 无 PyMOL，约数秒）…"
                                if _cloud_render() or not _dv_r.has_embedded_pymol()
                                else "内嵌 PyMOL 射线追踪 fig1+fig2（约 1–3 分钟）…"
                            )
                            with st.spinner(spin_msg):
                                for fn in ("fig1_overview.png", "fig2_pocket.png"):
                                    fp = work_d / fn
                                    if fp.is_file():
                                        try:
                                            fp.unlink()
                                        except Exception:
                                            pass
                                if _dv_r.has_embedded_pymol():
                                    rr = _dv_r.render_publication_pngs_pymol2(
                                        work_d,
                                        receptor_pdb=Path(
                                            dock.get("receptor_used")
                                            or dock.get("receptor_pdb")
                                            or ""
                                        ),
                                        ligand_path=Path(
                                            viz.get("ligand_pdb")
                                            or work_d / "lig_pose1.pdb"
                                        ),
                                        contacts=contacts,
                                        width=1200,
                                        height=900,
                                        dpi=300,
                                    )
                                    ok = bool(rr.get("ok"))
                                    engine = "pymol2" if ok else ""
                                    if ok:
                                        b1k = (rr.get("bytes") or {}).get("fig1", 0)
                                        b2k = (rr.get("bytes") or {}).get("fig2", 0)
                                        st.success(
                                            f"内嵌 PyMOL 已渲染 · fig1={b1k//1024}KB · fig2={b2k//1024}KB"
                                        )
                                    else:
                                        st.warning(
                                            rr.get("error") or "pymol2 渲染未完成"
                                        )
                                if not ok and not _cloud_render():
                                    batch = Path(viz.get("batch_pml") or "")
                                    if batch.is_file():
                                        rr2 = _dv_r.render_pymol_pngs(batch)
                                        ok = bool(rr2.get("ok"))
                                        if ok:
                                            engine = "pymol_exe"
                                if not ok:
                                    try:
                                        paths = _dv_r.render_fallback_pngs(
                                            work_d,
                                            contacts=contacts,
                                            affinity=best,
                                            box=box,
                                            title=prev_rec,
                                        )
                                        ok = bool(
                                            Path(paths.get("fig1_png") or "").is_file()
                                            or (work_d / "fig1_overview.png").is_file()
                                        )
                                        engine = "fallback"
                                        if ok:
                                            st.info(
                                                "已生成分析示意图（非 PyMOL 射线图）。"
                                                "向上滚动可看预览；Cloud 无法装 PyMOL。"
                                            )
                                        else:
                                            st.error("分析图写入失败：未找到 PNG 文件。")
                                    except Exception as exc_fb:  # noqa: BLE001
                                        st.error(f"出图失败：{exc_fb}")
                                        paths = {}
                                else:
                                    paths = {
                                        "fig1_png": str(work_d / "fig1_overview.png"),
                                        "fig2_png": str(work_d / "fig2_pocket.png"),
                                    }
                                if ok:
                                    st.session_state["_dock_render_force"] = {
                                        "fig1_png": paths.get("fig1_png")
                                        or str(work_d / "fig1_overview.png"),
                                        "fig2_png": paths.get("fig2_png")
                                        or str(work_d / "fig2_pocket.png"),
                                        "engine": engine or "fallback",
                                    }
                            st.rerun()
                    with b2:
                        if st.button(
                            "PyMOL 交互打开",
                            key="dock_pymol_launch",
                            use_container_width=True,
                        ):
                            launched = _dv.launch_pymol(Path(viz["pml"]))
                            if launched.get("ok"):
                                st.success(f"已启动：`{launched.get('exe')}`")
                            else:
                                st.error(launched.get("error") or "启动失败")
                    with b3:
                        p1 = Path(viz.get("fig1_pml") or "")
                        if p1.is_file():
                            st.download_button(
                                "图1脚本.pml",
                                data=p1.read_bytes(),
                                file_name=p1.name,
                                key="dock_dl_fig1pml",
                                use_container_width=True,
                            )
                    with b4:
                        p2 = Path(viz.get("fig2_pml") or "")
                        if p2.is_file():
                            st.download_button(
                                "图2脚本.pml",
                                data=p2.read_bytes(),
                                file_name=p2.name,
                                key="dock_dl_fig2pml",
                                use_container_width=True,
                            )

                    dl1, dl2, dl3, dl4 = st.columns(4)
                    with dl1:
                        if f1.is_file():
                            st.download_button(
                                "下载图1 PNG",
                                data=f1.read_bytes(),
                                file_name=f1.name,
                                mime="image/png",
                                key="dock_dl_fig1png",
                                use_container_width=True,
                            )
                    with dl2:
                        if f2.is_file():
                            st.download_button(
                                "下载图2 PNG",
                                data=f2.read_bytes(),
                                file_name=f2.name,
                                mime="image/png",
                                key="dock_dl_fig2png",
                                use_container_width=True,
                            )
                    with dl3:
                        tsv = Path(viz.get("tsv") or "")
                        if tsv.is_file():
                            st.download_button(
                                "残基/氢键表.tsv",
                                data=tsv.read_bytes(),
                                file_name=tsv.name,
                                key="dock_dl_tsv",
                                use_container_width=True,
                            )
                    with dl4:
                        lpq = Path(viz.get("ligand_pdbqt") or "")
                        if lpq.is_file():
                            st.download_button(
                                "构象1.pdbqt",
                                data=lpq.read_bytes(),
                                file_name=lpq.name,
                                key="dock_dl_pose1qt",
                                use_container_width=True,
                            )

                    if viz.get("pymol_embedded") or (
                        (viz.get("render") or {}).get("engine") in ("pymol2", "cached")
                    ):
                        st.caption(
                            "渲染引擎：**项目内嵌 PyMOL**（pip: pymol-open-source）· "
                            "对接结束后自动出图，也可点「渲染出 PNG」重渲。"
                        )
                    elif viz.get("pymol_exe"):
                        st.caption(f"PyMOL 可执行文件：`{viz.get('pymol_exe')}`")
                    else:
                        try:
                            from cloud_env import is_streamlit_cloud as _is_cloud
                        except Exception:
                            _is_cloud = lambda: False  # type: ignore[assignment]
                        if _is_cloud():
                            st.info(
                                "Cloud 环境无内嵌 PyMOL（当前平台 Python 无可用 wheel）。"
                                "三维结构请用上方 **py3Dmol**；出版级 PNG 请在本机对接页渲染。"
                            )
                        else:
                            st.warning(
                                "未检测到内嵌 pymol2。本机 venv 执行："
                                "`pip install -r requirements-dock.txt`"
                            )

                    with st.expander("作图说明（对应你的流程）", expanded=False):
                        st.markdown(
                            """
**文件**：清理后蛋白 `pro` + 第 1 构象 `lig`（.pdbqt）

**图1**：白底 · 蛋白 gray80 cartoon · 配体 yellow+按元素 · 关阴影 · Ray 300dpi → `fig1_overview.png`

**图2**：`select keyres`（4 Å 内最近约 9 个残基）sticks + palecyan；
`distance hbonds, lig, keyres, mode=2`（极性接触=氢键）；
其余蛋白 cartoon 透明度 0.8；残基 CA 标签；Ray → `fig2_pocket.png`

氢键键长见上方表格 / `hbonds_residues.tsv`，可复制到 PPT。
"""
                        )
                except Exception as viz_exc:  # noqa: BLE001
                    st.warning(f"可视化准备失败：{viz_exc}")
                pose_path = Path(dock.get("out_pdbqt") or "")
                if pose_path.is_file():
                    st.download_button(
                        "下载对接 pose（PDBQT）",
                        data=pose_path.read_bytes(),
                        file_name=pose_path.name,
                        mime="chemical/x-pdbqt",
                        key="dock_dl_poses",
                        use_container_width=True,
                    )
                lig_q = Path(dock.get("ligand_pdbqt") or "")
                rec_q = Path(dock.get("receptor_pdbqt") or "")
                rec_used = Path(dock.get("receptor_used") or "")
                d1, d2, d3 = st.columns(3)
                with d1:
                    if lig_q.is_file():
                        st.download_button(
                            "配体 PDBQT",
                            data=lig_q.read_bytes(),
                            file_name=lig_q.name,
                            key="dock_dl_lig",
                            use_container_width=True,
                        )
                with d2:
                    if rec_q.is_file():
                        st.download_button(
                            "受体 PDBQT",
                            data=rec_q.read_bytes(),
                            file_name=rec_q.name,
                            key="dock_dl_rec",
                            use_container_width=True,
                        )
                with d3:
                    if rec_used.is_file() and dock.get("add_tyr_coppers"):
                        st.download_button(
                            "含双铜 PDB",
                            data=rec_used.read_bytes(),
                            file_name=rec_used.name,
                            key="dock_dl_cu_pdb",
                            use_container_width=True,
                        )
                st.caption(f"工作目录：`{dock.get('work_dir')}`")
                log_path = Path(dock.get("log") or "")
                if log_path.is_file():
                    with st.expander("Vina 日志", expanded=False):
                        st.code(
                            log_path.read_text(encoding="utf-8", errors="replace"),
                            language=None,
                        )

            dh = st.session_state.get("dock_history") or []
            if dh:
                with st.expander(f"本会话对接记录（{len(dh)}）", expanded=False):
                    st.dataframe(dh, use_container_width=True, hide_index=True)

    # 历史最近一次蛋白
    last = st.session_state.get("last_protein")
    if last and last is not result and last.get("ok"):
        with st.expander("最近一次下载的蛋白", expanded=False):
            st.write(
                {
                    "source": last.get("source"),
                    "path": last.get("path"),
                    "pdb_id": last.get("pdb_id"),
                    "uniprot": last.get("uniprot"),
                }
            )


def page_help():
    st.subheader("使用说明")
    st.info("完整分步操作见右下角蓝色「手册」按钮（可拖动、任意页打开/关闭）。")
    st.markdown(
        """
### 功能位置

| 需求 | 位置 |
|------|------|
| PubChem / ChEMBL 查分子 | 「分子库查询」 |
| 预测存档、修改重跑 | 「历史记录」 |
| 无名产物当下一步原料 | 主产物上的「用作原料 A/B」 |
| 产物去做对接 | 主产物「添加为对接配体」→ 自动跳转蛋白对接 |
| 对接三阶段 | ①准备受体/配体 → ②文献 Grid Box + Vina → ③结合能/口袋残基/PyMOL |
| 推荐盒子 | 人源 TYR：**25×25×25 Å**（双铜中点）；TYRP1 5M8O：**22 Å**（晶体双锌） |
| PyMOL 可视化 | 对接结果区「用 PyMOL 打开」或下载 `.pml` / `complex.pdb` |
| 投料比 / 文献 | 「反应预测」结果区 |
| ReactionT5 本机产物预测 | 「反应预测」→ 选 ReactionT5（首次自动下载） |
| 产物 ¹H / ¹³C NMR | 结果区「预测主产物 NMR」· 溶剂 CDCl₃ / DMSO-d₆ |
| 蛋白酶结构（PDB/AlphaFold） | 「蛋白对接」· 上方下载 |
| 分子对接 Vina | 「蛋白对接」· ①补双铜修饰 → ②改 SMILES → ③开始对接（自动存历史） |
| 对接后换化合物/酶 | 直接改「对接用 SMILES」或受体下拉，不必清结果 |

### 产物引擎说明

- **大模型**：用 Agnes 等估计产物（快，但不等于专业反应模型）
- **ReactionT5 本机**：`sagawa/ReactionT5v2-forward`（该模型无 HF 远程 Inference，故本机跑；默认 hf-mirror 下载）
- **IBM RXN**：需自备 Key
- 条件优化与文献检索始终走侧边栏选的大模型

### 命令行调用 PubChem / ChEMBL

```powershell
cd G:\\Project\\DHH\\chemcrow-lab
.\\venv\\Scripts\\python.exe chem_apis.py 阿司匹林
.\\venv\\Scripts\\python.exe -c "from chem_apis import pubchem_lookup, chembl_lookup, lookup_both; import json; print(json.dumps(lookup_both('aspirin'), ensure_ascii=False, indent=2))"
```

无需 API Key。PubChem 请控制在约 5 次/秒以内。
"""
    )


def main():
    # 必须在任何 input_a / smi_a widget 之前应用「用作原料」写入
    _apply_pending_reactants()
    _apply_pending_dock_ligand()

    # 程序化跳转（预测→对接等）：须在 nav radio 之前写入
    NAV_PAGES = ["反应预测", "分子库查询", "蛋白对接", "历史记录", "路径出图", "说明"]
    if "nav_goto" in st.session_state:
        dest = st.session_state.pop("nav_goto")
        if dest in NAV_PAGES:
            st.session_state["nav_page"] = dest
    if "nav_page" not in st.session_state:
        st.session_state["nav_page"] = "反应预测"

    st.markdown(_chem_hero_html(), unsafe_allow_html=True)
    _sidebar_keys()

    page = st.radio(
        "导航",
        NAV_PAGES,
        horizontal=True,
        key="nav_page",
        label_visibility="collapsed",
    )

    toast = st.session_state.pop("_reactant_toast", None)
    if toast:
        st.info(toast)
    dock_toast = st.session_state.pop("_dock_toast", None)
    if dock_toast:
        st.success(dock_toast + " · 已跳转到蛋白对接页")

    if page == "反应预测":
        page_predict()
    elif page == "分子库查询":
        page_db_lookup()
    elif page == "蛋白对接":
        page_protein()
    elif page == "历史记录":
        page_history()
    elif page == "路径出图":
        page_pathway()
    else:
        page_help()

    # 全站浮动操作手册（盖住所有层，可拖拽/开关，与当前页无关）
    inject_ops_manual()


if __name__ == "__main__":
    main()
