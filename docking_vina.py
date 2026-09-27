"""兼容层：转发到 docking.run_docking。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from docking import ensure_vina, run_docking, vina_version


def dock_smiles_to_pdb(
    ligand_smiles: str,
    receptor_pdb,
    *,
    pdb_id: str = "",
    job_name: str = "",
    exhaustiveness: int = 8,
    num_modes: int = 9,
    box_size: float = 22.0,
) -> Dict[str, Any]:
    """旧 UI 入口。"""
    result = run_docking(
        receptor_pdb,
        ligand_smiles,
        exhaustiveness=exhaustiveness,
        num_modes=num_modes,
        box_size=box_size,
        job_name=job_name or pdb_id or "dock",
    )
    # 兼容旧字段名
    box = result.get("box") or {}
    c = box.get("center") or (0, 0, 0)
    s = box.get("size") or (22, 22, 22)
    result["poses_pdbqt"] = result.get("out_pdbqt") or ""
    result["box"] = {
        **box,
        "center_x": c[0],
        "center_y": c[1],
        "center_z": c[2],
        "size_x": s[0],
        "size_y": s[1],
        "size_z": s[2],
        "note": box.get("source") or "",
    }
    result["stdout"] = ""
    log = result.get("log") or ""
    if log and Path(log).is_file():
        result["stdout"] = Path(log).read_text(encoding="utf-8", errors="replace")
    return result


__all__ = ["dock_smiles_to_pdb", "ensure_vina", "vina_version", "run_docking"]
