"""对接结果自动存档。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "docking_history"
INDEX_FILE = DATA_DIR / "index.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _ensure() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("[]", encoding="utf-8")


def save_dock_record(dock: Dict[str, Any], *, title: str = "") -> str:
    """保存一次对接结果，返回 id。"""
    _ensure()
    rid = uuid.uuid4().hex[:12]
    now = _now()
    smi = (dock.get("ligand_smiles") or "")[:80]
    rec_name = Path(dock.get("receptor_used") or dock.get("receptor_pdb") or "").name
    best = dock.get("best_affinity")
    auto = title or f"{rec_name} · {smi[:30]} · {best} kcal/mol"
    record = {
        "id": rid,
        "title": auto,
        "created_at": now,
        "updated_at": now,
        "best_affinity": best,
        "ligand_smiles": dock.get("ligand_smiles") or "",
        "receptor_pdb": dock.get("receptor_pdb") or "",
        "receptor_used": dock.get("receptor_used") or "",
        "add_tyr_coppers": bool(dock.get("add_tyr_coppers")),
        "box": dock.get("box") or {},
        "poses": dock.get("poses") or [],
        "work_dir": dock.get("work_dir") or "",
        "out_pdbqt": dock.get("out_pdbqt") or "",
        "ligand_pdbqt": dock.get("ligand_pdbqt") or "",
        "receptor_pdbqt": dock.get("receptor_pdbqt") or "",
        "log": dock.get("log") or "",
        "elapsed_s": dock.get("elapsed_s"),
        "vina": dock.get("vina") or "",
        "metal_info": dock.get("metal_info") or {},
    }
    (DATA_DIR / f"{rid}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    index = _list_index()
    index.insert(
        0,
        {
            "id": rid,
            "title": auto,
            "created_at": now,
            "best_affinity": best,
            "ligand_smiles": record["ligand_smiles"][:60],
            "receptor": rec_name,
            "add_tyr_coppers": record["add_tyr_coppers"],
        },
    )
    INDEX_FILE.write_text(
        json.dumps(index[:100], ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return rid


def _list_index() -> List[Dict[str, Any]]:
    _ensure()
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def list_dock_records(limit: int = 30) -> List[Dict[str, Any]]:
    return _list_index()[:limit]


def load_dock_record(record_id: str) -> Optional[Dict[str, Any]]:
    p = DATA_DIR / f"{record_id}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
