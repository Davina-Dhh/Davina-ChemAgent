"""预测历史持久化：保存 / 列表 / 加载 / 更新 / 删除。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "history"
INDEX_FILE = DATA_DIR / "index.json"


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not INDEX_FILE.exists():
        INDEX_FILE.write_text("[]", encoding="utf-8")


def _read_index() -> List[Dict[str, Any]]:
    _ensure_dir()
    try:
        return json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _write_index(items: List[Dict[str, Any]]) -> None:
    _ensure_dir()
    INDEX_FILE.write_text(
        json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _record_path(record_id: str) -> Path:
    return DATA_DIR / f"{record_id}.json"


def save_record(payload: Dict[str, Any], record_id: Optional[str] = None) -> str:
    """保存或覆盖一条预测记录，返回 record_id。"""
    _ensure_dir()
    rid = record_id or uuid.uuid4().hex[:12]
    now = _now()
    title = payload.get("title") or _auto_title(payload)
    record = {
        "id": rid,
        "title": title,
        "created_at": payload.get("created_at") or now,
        "updated_at": now,
        **payload,
    }
    record["id"] = rid
    record["title"] = title
    record["updated_at"] = now
    if "created_at" not in record or not record["created_at"]:
        record["created_at"] = now

    _record_path(rid).write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    index = [x for x in _read_index() if x.get("id") != rid]
    main_smi = ""
    products = record.get("result", {}).get("products") or []
    if products:
        main = next((p for p in products if p.get("role") == "product"), products[0])
        main_smi = main.get("smiles", "")
    index.insert(
        0,
        {
            "id": rid,
            "title": title,
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "engine": (record.get("result") or {}).get("engine", ""),
            "input_a": record.get("input_a", ""),
            "input_b": record.get("input_b", ""),
            "smi_a": record.get("smi_a", ""),
            "smi_b": record.get("smi_b", ""),
            "main_product": main_smi,
        },
    )
    _write_index(index)
    return rid


def _auto_title(payload: Dict[str, Any]) -> str:
    a = payload.get("input_a") or payload.get("smi_a") or "A"
    b = payload.get("input_b") or payload.get("smi_b") or "B"
    a = str(a)[:24]
    b = str(b)[:24]
    return f"{a} + {b}"


def list_records() -> List[Dict[str, Any]]:
    return _read_index()


def load_record(record_id: str) -> Optional[Dict[str, Any]]:
    path = _record_path(record_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_dock_record(dock: Dict[str, Any]) -> str:
    """对接结果单独存档，出现在历史列表（type=docking）。"""
    _ensure_dir()
    rid = uuid.uuid4().hex[:12]
    now = _now()
    smi = (dock.get("ligand_smiles") or "")[:48]
    rec_name = Path(str(dock.get("receptor_pdb") or "")).name
    best = dock.get("best_affinity")
    title = f"对接 {rec_name} · {smi or 'ligand'} · {best} kcal/mol"
    record = {
        "id": rid,
        "title": title,
        "type": "docking",
        "created_at": now,
        "updated_at": now,
        "dock": dock,
        "input_a": smi,
        "input_b": rec_name,
        "smi_a": dock.get("ligand_smiles") or "",
        "smi_b": "",
        "main_product": dock.get("ligand_smiles") or "",
        "result": {
            "engine": dock.get("vina") or "AutoDock Vina",
            "products": [
                {
                    "smiles": dock.get("ligand_smiles") or "",
                    "role": "product",
                    "note": f"dock best={best}",
                }
            ],
        },
    }
    _record_path(rid).write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    index = _read_index()
    index.insert(
        0,
        {
            "id": rid,
            "title": title,
            "type": "docking",
            "created_at": now,
            "updated_at": now,
            "engine": record["result"]["engine"],
            "input_a": smi,
            "input_b": rec_name,
            "smi_a": dock.get("ligand_smiles") or "",
            "smi_b": "",
            "main_product": dock.get("ligand_smiles") or "",
            "best_affinity": best,
        },
    )
    _write_index(index)
    return rid


def delete_record(record_id: str) -> bool:
    path = _record_path(record_id)
    if path.exists():
        path.unlink()
    index = [x for x in _read_index() if x.get("id") != record_id]
    _write_index(index)
    return True
