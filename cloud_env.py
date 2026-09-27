"""运行环境探测：本机 vs Streamlit Community Cloud。"""

from __future__ import annotations

import os
from pathlib import Path


def is_streamlit_cloud() -> bool:
    """Streamlit Community Cloud 常见特征。"""
    if (os.getenv("STREAMLIT_RUNTIME_ENVIRONMENT") or "").lower() == "cloud":
        return True
    if Path("/mount/src").exists():
        return True
    # 显式开关
    flag = (os.getenv("CHEMAGENT_CLOUD") or os.getenv("IS_STREAMLIT_CLOUD") or "").strip().lower()
    return flag in ("1", "true", "yes", "cloud")


def reactiont5_allowed() -> bool:
    """云端默认关闭本机 ReactionT5（内存不够）；本机可用。"""
    force = (os.getenv("ENABLE_REACTIONT5") or "").strip().lower()
    if force in ("1", "true", "yes"):
        return True
    if force in ("0", "false", "no"):
        return False
    return not is_streamlit_cloud()


def heavy_viz_allowed() -> bool:
    """PyMOL 射线追踪等重可视化：云端默认关。"""
    force = (os.getenv("ENABLE_PYMOL_RENDER") or "").strip().lower()
    if force in ("1", "true", "yes"):
        return True
    if force in ("0", "false", "no"):
        return False
    return not is_streamlit_cloud()
