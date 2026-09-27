"""PubChem / ChEMBL 免费 REST API 封装（无需 API Key）。

限速：PubChem 建议 ≤5 req/s（模块内已节流并重试 503）。
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
CHEMBL = "https://www.ebi.ac.uk/chembl/api/data"
UA = {"User-Agent": "chemcrow-lab/1.0 (academic)"}

_last_pubchem = 0.0


def _throttle_pubchem(min_interval: float = 0.25) -> None:
    global _last_pubchem
    now = time.time()
    wait = min_interval - (now - _last_pubchem)
    if wait > 0:
        time.sleep(wait)
    _last_pubchem = time.time()


def _get_json(
    url: str,
    params: Optional[dict] = None,
    timeout: float = 25.0,
    retries: int = 5,
    throttle: bool = False,
) -> Any:
    last_exc: Optional[Exception] = None
    for i in range(retries):
        if throttle:
            _throttle_pubchem()
        try:
            resp = requests.get(url, params=params, headers=UA, timeout=timeout)
            if resp.status_code in (503, 429, 502):
                time.sleep(1.5 * (i + 1))
                last_exc = RuntimeError(f"HTTP {resp.status_code}: {resp.text[:120]}")
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            if "json" in resp.headers.get("Content-Type", "") or resp.text.lstrip().startswith(
                ("{", "[")
            ):
                return resp.json()
            return resp.text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(0.8 * (i + 1))
    if last_exc:
        raise last_exc
    return None


def _looks_like_smiles_query(q: str) -> bool:
    q = q.strip()
    if not q or " " in q or re.search(r"[\u4e00-\u9fff]", q):
        return False
    if q.upper().startswith("CHEMBL"):
        return False
    if re.fullmatch(r"[A-Za-z][A-Za-z\-]*", q) and not re.search(r"[0-9=#\(\)\[\]]", q):
        return False
    return bool(re.search(r"[0-9=#\(\)\[\]@/\\]", q) or (q[:1].islower() and any(c in q for c in "()=[]#")))


def pubchem_name_to_cid(name: str) -> Optional[int]:
    url = f"{PUBCHEM}/compound/name/{quote(name.strip())}/cids/JSON"
    data = _get_json(url, throttle=True)
    if not data:
        return None
    cids = data.get("IdentifierList", {}).get("CID") or []
    return int(cids[0]) if cids else None


def pubchem_smiles_to_cid(smiles: str) -> Optional[int]:
    # GET 对特殊字符不稳时用 POST
    _throttle_pubchem()
    url = f"{PUBCHEM}/compound/smiles/cids/JSON"
    for i in range(4):
        try:
            resp = requests.post(
                url,
                data={"smiles": smiles.strip()},
                headers=UA,
                timeout=25,
            )
            if resp.status_code in (503, 429):
                time.sleep(1.5 * (i + 1))
                continue
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
            cids = data.get("IdentifierList", {}).get("CID") or []
            return int(cids[0]) if cids else None
        except Exception:
            time.sleep(0.8 * (i + 1))
    return None


def pubchem_props_by_cid(cid: int) -> Dict[str, Any]:
    props = (
        "MolecularFormula,MolecularWeight,CanonicalSMILES,IsomericSMILES,"
        "IUPACName,XLogP,TPSA,HBondDonorCount,HBondAcceptorCount,"
        "RotatableBondCount,HeavyAtomCount,Complexity"
    )
    url = f"{PUBCHEM}/compound/cid/{cid}/property/{props}/JSON"
    data = _get_json(url, throttle=True)
    if not data:
        return {}
    rows = data.get("PropertyTable", {}).get("Properties") or []
    return rows[0] if rows else {}


def pubchem_synonyms(cid: int, limit: int = 20) -> List[str]:
    url = f"{PUBCHEM}/compound/cid/{cid}/synonyms/JSON"
    data = _get_json(url, throttle=True)
    if not data:
        return []
    info = data.get("InformationList", {}).get("Information") or []
    if not info:
        return []
    return list(info[0].get("Synonym") or [])[:limit]


def pubchem_lookup(query: str) -> Dict[str, Any]:
    """按名称或 SMILES 查询 PubChem。"""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "查询为空", "source": "pubchem"}

    cid = None
    try:
        if _looks_like_smiles_query(q):
            cid = pubchem_smiles_to_cid(q)
        if cid is None:
            cid = pubchem_name_to_cid(q)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"PubChem 暂时不可用（常为限流/繁忙）: {exc}",
            "source": "pubchem",
        }

    if cid is None:
        return {
            "ok": False,
            "error": f"PubChem 未找到或暂时繁忙: {q}（可稍后重试，或改用英文名/SMILES）",
            "source": "pubchem",
        }

    try:
        props = pubchem_props_by_cid(cid)
        syns = pubchem_synonyms(cid)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"PubChem 取属性失败: {exc}",
            "source": "pubchem",
            "cid": cid,
        }

    return {
        "ok": True,
        "source": "pubchem",
        "cid": cid,
        "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}",
        "smiles": props.get("IsomericSMILES") or props.get("CanonicalSMILES") or "",
        "formula": props.get("MolecularFormula"),
        "mw": props.get("MolecularWeight"),
        "iupac": props.get("IUPACName"),
        "xlogp": props.get("XLogP"),
        "tpsa": props.get("TPSA"),
        "hbd": props.get("HBondDonorCount"),
        "hba": props.get("HBondAcceptorCount"),
        "rotbonds": props.get("RotatableBondCount"),
        "synonyms": syns,
        "raw_props": props,
    }


# ---------------- ChEMBL ----------------


def chembl_search_name(name: str, limit: int = 5) -> List[Dict[str, Any]]:
    data = _get_json(
        f"{CHEMBL}/molecule/search.json",
        params={"q": name.strip(), "limit": limit},
    )
    if not data:
        return []
    return list(data.get("molecules") or [])[:limit]


def chembl_molecule_by_id(chembl_id: str) -> Optional[Dict[str, Any]]:
    return _get_json(f"{CHEMBL}/molecule/{chembl_id.upper()}.json")


def chembl_similarity(smiles: str, cutoff: int = 70, limit: int = 10) -> List[Dict[str, Any]]:
    if not _looks_like_smiles_query(smiles):
        return []
    cutoff = max(40, min(100, int(cutoff)))
    url = f"{CHEMBL}/similarity/{quote(smiles.strip(), safe='')}/{cutoff}.json"
    data = _get_json(url)
    if not data:
        return []
    out = []
    for m in (data.get("molecules") or [])[:limit]:
        structs = m.get("molecule_structures") or {}
        cid = m.get("molecule_chembl_id")
        out.append(
            {
                "chembl_id": cid,
                "pref_name": m.get("pref_name"),
                "smiles": structs.get("canonical_smiles"),
                "similarity": m.get("similarity"),
                "max_phase": m.get("max_phase"),
                "url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{cid}/"
                if cid
                else "",
            }
        )
    return out


def chembl_activities(chembl_id: str, limit: int = 15) -> List[Dict[str, Any]]:
    data = _get_json(
        f"{CHEMBL}/activity.json",
        params={"molecule_chembl_id": chembl_id, "limit": limit},
    )
    if not data:
        return []
    out = []
    for a in (data.get("activities") or [])[:limit]:
        out.append(
            {
                "assay_chembl_id": a.get("assay_chembl_id"),
                "target_chembl_id": a.get("target_chembl_id"),
                "target_pref_name": a.get("target_pref_name"),
                "standard_type": a.get("standard_type"),
                "standard_value": a.get("standard_value"),
                "standard_units": a.get("standard_units"),
                "pchembl_value": a.get("pchembl_value"),
            }
        )
    return out


def _smiles_from_molecule(molecule: Optional[Dict[str, Any]]) -> str:
    if not molecule:
        return ""
    structs = molecule.get("molecule_structures") or {}
    return structs.get("canonical_smiles") or ""


def chembl_lookup(query: str, similarity_cutoff: int = 80) -> Dict[str, Any]:
    """
    ChEMBL 查询：
    - CHEMBLxxxx → 直接取分子
    - SMILES → 相似搜索
    - 名称 → molecule/search；必要时借 PubChem 转 SMILES 再相似搜
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "查询为空", "source": "chembl"}

    molecule = None
    smiles = ""
    similar: List[Dict[str, Any]] = []

    try:
        if q.upper().startswith("CHEMBL"):
            molecule = chembl_molecule_by_id(q)
            smiles = _smiles_from_molecule(molecule)
        elif _looks_like_smiles_query(q):
            smiles = q
            similar = chembl_similarity(smiles, cutoff=similarity_cutoff, limit=8)
            if similar:
                molecule = chembl_molecule_by_id(similar[0]["chembl_id"] or "")
        else:
            hits = chembl_search_name(q, limit=5)
            if hits:
                molecule = hits[0]
                smiles = _smiles_from_molecule(molecule)
            else:
                # 名称搜不到时，借 PubChem 转 SMILES 再相似搜
                pc = pubchem_lookup(q)
                if pc.get("ok") and pc.get("smiles"):
                    smiles = pc["smiles"]
                    similar = chembl_similarity(
                        smiles, cutoff=similarity_cutoff, limit=8
                    )
                    if similar:
                        molecule = chembl_molecule_by_id(similar[0]["chembl_id"] or "")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"ChEMBL 请求失败: {exc}", "source": "chembl"}

    if smiles and not similar and _looks_like_smiles_query(smiles):
        try:
            similar = chembl_similarity(smiles, cutoff=similarity_cutoff, limit=8)
        except Exception:
            similar = []

    chembl_id = (molecule or {}).get("molecule_chembl_id") if molecule else None
    pref_name = (molecule or {}).get("pref_name") if molecule else None
    if not chembl_id and similar:
        chembl_id = similar[0].get("chembl_id")
        pref_name = similar[0].get("pref_name")
        if not smiles:
            smiles = similar[0].get("smiles") or ""

    activities: List[Dict[str, Any]] = []
    if chembl_id:
        try:
            activities = chembl_activities(chembl_id, limit=12)
        except Exception:
            activities = []

    if not molecule and not similar:
        return {
            "ok": False,
            "error": f"ChEMBL 未找到: {q}",
            "source": "chembl",
            "query_smiles": smiles,
        }

    return {
        "ok": True,
        "source": "chembl",
        "chembl_id": chembl_id,
        "pref_name": pref_name,
        "smiles": smiles or _smiles_from_molecule(molecule),
        "url": f"https://www.ebi.ac.uk/chembl/compound_report_card/{chembl_id}/"
        if chembl_id
        else "",
        "similar": similar,
        "activities": activities,
        "molecule": molecule,
    }


def lookup_both(query: str, similarity_cutoff: int = 80) -> Dict[str, Any]:
    """一次返回 PubChem + ChEMBL。"""
    pc_error = None
    try:
        pc = pubchem_lookup(query)
    except Exception as exc:  # noqa: BLE001
        pc = {"ok": False, "error": str(exc), "source": "pubchem"}
        pc_error = exc

    # ChEMBL：有 SMILES 更稳；名称可直接 search
    chembl_q = pc.get("smiles") if pc.get("ok") and pc.get("smiles") else query
    try:
        ch = chembl_lookup(chembl_q or query, similarity_cutoff=similarity_cutoff)
    except Exception as exc:  # noqa: BLE001
        ch = {"ok": False, "error": str(exc), "source": "chembl"}

    return {
        "query": query,
        "pubchem": pc,
        "chembl": ch,
        "note": str(pc_error) if pc_error else "",
    }


if __name__ == "__main__":
    import json
    import sys

    q = sys.argv[1] if len(sys.argv) > 1 else "aspirin"
    print(json.dumps(lookup_both(q), ensure_ascii=False, indent=2))
