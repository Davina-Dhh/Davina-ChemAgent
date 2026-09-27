"""结构标识与系统命名（中英 IUPAC）+ SciFinder 可复制检索串。

速度优先：本地 RDKit 立刻返回 → 并行短超时查库 → 缺名时只打 1 次 LLM。
"""

from __future__ import annotations

import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import requests

_CACHE: Dict[str, Dict[str, str]] = {}

# 网络命名短超时（秒）——卡住就走 LLM / 结构检索
_NET_TIMEOUT = 5.0


def clear_name_cache(smiles: Optional[str] = None) -> None:
    """清除系统命名缓存。"""
    if smiles is None:
        _CACHE.clear()
        return
    smi = (smiles or "").strip()
    _CACHE.pop(smi, None)
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smi)
        if mol is not None:
            _CACHE.pop(Chem.MolToSmiles(mol), None)
    except Exception:
        pass


def structure_ids(smiles: str) -> Dict[str, str]:
    """返回 canon SMILES / InChI / InChIKey / Molfile（本地，毫秒级）。"""
    out = {"smiles": "", "inchi": "", "inchikey": "", "molfile": ""}
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles((smiles or "").strip())
        if mol is None:
            return out
        out["smiles"] = Chem.MolToSmiles(mol)
        out["inchi"] = Chem.MolToInchi(mol) or ""
        out["inchikey"] = Chem.MolToInchiKey(mol) or ""
        try:
            out["molfile"] = Chem.MolToMolBlock(mol) or ""
        except Exception:
            out["molfile"] = ""
    except Exception:
        out["smiles"] = (smiles or "").strip()
    return out


def _cactus_iupac(smiles: str, timeout: float = _NET_TIMEOUT) -> Optional[str]:
    url = f"https://cactus.nci.nih.gov/chemical/structure/{quote(smiles, safe='')}/iupac_name"
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200:
            name = (r.text or "").strip()
            if name and "<" not in name and "Page not found" not in name:
                return name
    except Exception:
        return None
    return None


def _pubchem_iupac(
    smiles: str, timeout: float = _NET_TIMEOUT
) -> Tuple[Optional[str], Optional[int]]:
    """返回 (IUPACName or Title, CID)。503 不重试，直接放弃。"""
    try:
        r = requests.post(
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/property/"
            "IUPACName,Title/JSON",
            data={"smiles": smiles},
            timeout=timeout,
        )
        if r.status_code != 200:
            return None, None
        props = (r.json().get("PropertyTable") or {}).get("Properties") or []
        if not props:
            return None, None
        p0 = props[0]
        cid = p0.get("CID")
        name = (p0.get("IUPACName") or p0.get("Title") or "").strip()
        return (name or None), (int(cid) if cid else None)
    except Exception:
        return None, None


def _pubchem_chinese_synonym(cid: int, timeout: float = 4.0) -> Optional[str]:
    if not cid:
        return None
    try:
        r = requests.get(
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON",
            timeout=timeout,
        )
        if r.status_code != 200:
            return None
        info = (r.json().get("InformationList") or {}).get("Information") or []
        syns = (info[0].get("Synonym") or []) if info else []
        zh_cands: List[str] = []
        for s in syns:
            s = (s or "").strip()
            if not s or not re.search(r"[\u4e00-\u9fff]", s):
                continue
            if len(s) < 2 or len(s) > 120:
                continue
            if any(x in s for x in ("http", "CAS", "UNII", "InChI")):
                continue
            zh_cands.append(s)
        if not zh_cands:
            return None
        zh_cands.sort(key=lambda x: (-len(x), x))
        return zh_cands[0]
    except Exception:
        return None


def _llm_iupac_pair(smiles: str) -> Tuple[Optional[str], Optional[str]]:
    """一次调用同时粗拟英文 + 中文系统名（只打这一次，不再二次请求）。"""
    try:
        from reaction_predict import _agnes_chat
    except Exception:
        return None, None
    if not (os.getenv("OPENAI_API_KEY") or "").strip():
        return None, None
    prompt = (
        "为下面有机分子给出系统命名。只输出一行 JSON，不要其它文字：\n"
        '{"en":"English IUPAC name","zh":"中文系统命名"}\n'
        f"SMILES: {smiles}"
    )
    try:
        text = _agnes_chat(
            [
                {
                    "role": "system",
                    "content": "Organic nomenclature expert. Return one JSON object only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        raw = (text or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        m = re.search(r"\{.*\}", raw, flags=re.S)
        if not m:
            return None, None
        data = json.loads(m.group(0))
        en = (data.get("en") or "").strip().strip('"').strip("'")
        zh = (data.get("zh") or "").strip().strip('"').strip("'")
        if en and (len(en) < 4 or len(en) > 200 or re.search(r"[\u4e00-\u9fff]", en)):
            en = ""
        if zh and (
            len(zh) < 2 or len(zh) > 120 or not re.search(r"[\u4e00-\u9fff]", zh)
        ):
            zh = ""
        return (en or None), (zh or None)
    except Exception:
        return None, None


def resolve_systematic_name(
    smiles: str, *, allow_llm: bool = True, want_zh: bool = True
) -> Dict[str, str]:
    """
    解析中英系统命名与结构 ID（速度优先）。

    流程：缓存 → 本地 RDKit → 并行 Cactus/PubChem（≤5s）→
    无英文时 1 次 LLM；want_zh 且缺中文时再补 1 次（可选）。
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass

    smi = (smiles or "").strip()
    if not smi:
        return {
            "error": "SMILES 为空",
            "smiles": "",
            "iupac": "",
            "iupac_en": "",
            "iupac_zh": "",
            "inchikey": "",
            "molfile": "",
        }
    if smi in _CACHE:
        return dict(_CACHE[smi])

    ids = structure_ids(smi)
    canon = ids.get("smiles") or smi
    result = {
        "smiles": canon,
        "inchi": ids.get("inchi") or "",
        "inchikey": ids.get("inchikey") or "",
        "molfile": ids.get("molfile") or "",
        "iupac": "",
        "iupac_en": "",
        "iupac_zh": "",
        "source": "",
        "source_zh": "",
        "cid": "",
        "error": "",
    }

    # 并行短超时：谁先给英文名用谁
    with ThreadPoolExecutor(max_workers=2) as pool:
        futs = {
            pool.submit(_cactus_iupac, canon): "cactus",
            pool.submit(_pubchem_iupac, canon): "pubchem",
        }
        try:
            for fut in as_completed(futs, timeout=_NET_TIMEOUT + 1.5):
                tag = futs[fut]
                try:
                    val = fut.result()
                except Exception:
                    continue
                if tag == "cactus" and val and not result["iupac_en"]:
                    result["iupac_en"] = val
                    result["source"] = "NIH Cactus"
                elif tag == "pubchem" and isinstance(val, tuple):
                    name2, cid = val
                    if cid and not result["cid"]:
                        result["cid"] = str(cid)
                    if name2 and not result["iupac_en"]:
                        result["iupac_en"] = name2
                        result["source"] = "PubChem"
                # 已有英文名且（无 CID 需求或已有 CID）可提前结束
                if result["iupac_en"] and (result["cid"] or tag == "cactus"):
                    # 有英文即可；CID 没有也行（中文可走 LLM）
                    if result["iupac_en"]:
                        break
        except TimeoutError:
            pass

    # 有 CID 时快速取中文同义词（4s，失败就算）
    if result["cid"] and not result["iupac_zh"]:
        try:
            zh = _pubchem_chinese_synonym(int(result["cid"]))
        except Exception:
            zh = None
        if zh:
            result["iupac_zh"] = zh
            result["source_zh"] = "PubChem 同义词"

    # 缺英文时才打 LLM（一次出中英）。已有英文时：want_zh=True 才补中文
    if allow_llm and not result["iupac_en"]:
        en_llm, zh_llm = _llm_iupac_pair(canon)
        if en_llm:
            result["iupac_en"] = en_llm
            result["source"] = "LLM拟名（请人工核对）"
        if zh_llm and not result["iupac_zh"]:
            result["iupac_zh"] = zh_llm
            result["source_zh"] = "LLM中文拟名（请人工核对）"
    elif allow_llm and want_zh and result["iupac_en"] and not result["iupac_zh"]:
        _, zh_llm = _llm_iupac_pair(canon)
        if zh_llm:
            result["iupac_zh"] = zh_llm
            result["source_zh"] = "LLM中文拟名（请人工核对）"

    result["iupac"] = result["iupac_en"]

    if not result["iupac_en"] and not result["iupac_zh"]:
        result["error"] = (
            "未能解析系统名；请用下方 SMILES / InChI / InChIKey 在 SciFinder 按结构检索"
        )
    else:
        result["error"] = ""

    _CACHE[smi] = dict(result)
    _CACHE[canon] = dict(result)
    return result


def literature_query_terms(smiles: str) -> Dict[str, str]:
    """文献 / SciFinder 检索用：中英名 + 结构标识（不用分子式）。"""
    info = resolve_systematic_name(smiles, allow_llm=True)
    return {
        "iupac": info.get("iupac_en") or info.get("iupac") or "",
        "iupac_en": info.get("iupac_en") or "",
        "iupac_zh": info.get("iupac_zh") or "",
        "inchikey": info.get("inchikey") or "",
        "inchi": info.get("inchi") or "",
        "smiles": info.get("smiles") or smiles,
        "molfile": info.get("molfile") or "",
        "cid": info.get("cid") or "",
        "source": info.get("source") or "",
        "source_zh": info.get("source_zh") or "",
        "error": info.get("error") or "",
    }


def scifinder_copy_block(
    smiles: str = "", terms: Optional[Dict[str, str]] = None
) -> str:
    """生成可整段复制到 SciFinder 的检索块（NMR / 质谱）。"""
    t = terms or literature_query_terms(smiles)
    lines = [
        "===== SciFinder 复制块（NMR / 质谱用结构搜）=====",
        f"英文 IUPAC: {t.get('iupac_en') or '（无）'}",
        f"中文系统名: {t.get('iupac_zh') or '（无）'}",
        f"SMILES: {t.get('smiles') or ''}",
        f"InChIKey: {t.get('inchikey') or ''}",
        f"InChI: {t.get('inchi') or ''}",
        "",
        "用法：https://scifinder-n.cas.org/ → Substances",
        "  1) 粘贴 SMILES（推荐）或 InChIKey；或 Import 下方 Molfile",
        "  2) 找别人做过的 NMR：Refine → NMR / 1H NMR / 13C NMR",
        "  3) 质谱：Refine → mass spectrum / HRMS / ESI-MS",
        "==============================================",
    ]
    return "\n".join(lines)
