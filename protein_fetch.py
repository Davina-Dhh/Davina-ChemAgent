"""从 RCSB PDB / AlphaFold DB 拉取蛋白酶结构（仅下载，不做对接）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "outputs" / "proteins"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROTEASE_PRESETS: List[Dict[str, str]] = [
    {
        "key": "sars2_mpro",
        "name": "SARS-CoV-2 主蛋白酶 (Mpro / 3CLpro)",
        "pdb": "6LU7",
        "uniprot": "P0DTD1",
        "organism": "SARS-CoV-2",
        "note": "COVID-19 药物靶点经典结构（含抑制剂 N3）",
    },
    {
        "key": "sars2_plpro",
        "name": "SARS-CoV-2 木瓜样蛋白酶 (PLpro)",
        "pdb": "6W9C",
        "uniprot": "P0DTD1",
        "organism": "SARS-CoV-2",
        "note": "多聚蛋白切割相关",
    },
    {
        "key": "hiv1_pr",
        "name": "HIV-1 蛋白酶",
        "pdb": "1HPV",
        "uniprot": "P03367",
        "organism": "HIV-1",
        "note": "经典抗病毒靶点",
    },
    {
        "key": "thrombin",
        "name": "人凝血酶 Thrombin",
        "pdb": "1PPB",
        "uniprot": "P00734",
        "organism": "Homo sapiens",
        "note": "丝氨酸蛋白酶",
    },
    {
        "key": "trypsin",
        "name": "牛胰蛋白酶 Trypsin",
        "pdb": "2PTN",
        "uniprot": "P00760",
        "organism": "Bos taurus",
        "note": "丝氨酸蛋白酶模式蛋白",
    },
    {
        "key": "factor_xa",
        "name": "人凝血因子 Xa",
        "pdb": "1FAX",
        "uniprot": "P00742",
        "organism": "Homo sapiens",
        "note": "抗凝靶点",
    },
    {
        "key": "dpp4",
        "name": "DPP-4（二肽基肽酶-4）",
        "pdb": "1N1M",
        "uniprot": "P27487",
        "organism": "Homo sapiens",
        "note": "糖尿病相关靶点",
    },
    {
        "key": "caspase3",
        "name": "Caspase-3",
        "pdb": "1CP3",
        "uniprot": "P42574",
        "organism": "Homo sapiens",
        "note": "凋亡相关半胱氨酸蛋白酶",
    },
    {
        "key": "cathepsin_b",
        "name": "组织蛋白酶 B (Cathepsin B)",
        "pdb": "1HUC",
        "uniprot": "P07858",
        "organism": "Homo sapiens",
        "note": "溶酶体半胱氨酸蛋白酶",
    },
    {
        "key": "ace",
        "name": "人血管紧张素转换酶 ACE",
        "pdb": "1O8A",
        "uniprot": "P12821",
        "organism": "Homo sapiens",
        "note": "金属蛋白酶；降压药靶点",
    },
    {
        "key": "human_tyr",
        "name": "人源酪氨酸酶 Tyrosinase (TYR)",
        "pdb": "",
        "uniprot": "P14679",
        "organism": "Homo sapiens",
        "note": "美白/黑色素相关靶点。人源 TYR 完整实验结构很少，推荐 AlphaFold（UniProt P14679）。基因名 TYR，不是 HTYR。",
    },
    {
        "key": "human_tyrp1",
        "name": "人源酪氨酸酶相关蛋白 1 (TYRP1)",
        "pdb": "5M8O",
        "uniprot": "P17643",
        "organism": "Homo sapiens",
        "note": "与酪氨酸酶同源；有晶体结构 5M8O（含抑制剂）。常作 TYR 家族结构参照。",
    },
]


def list_presets() -> List[Dict[str, str]]:
    return list(PROTEASE_PRESETS)


_UNIPROT_ACC = re.compile(
    r"^[OPQ][0-9][A-Z0-9]{3}[0-9]$|^[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2}$",
    re.I,
)


def _norm_pdb(pdb_id: str) -> str:
    pid = re.sub(r"[^A-Za-z0-9]", "", (pdb_id or "").strip()).upper()
    if len(pid) != 4:
        raise ValueError(f"PDB ID 应为 4 位，收到：{pdb_id!r}")
    return pid


def _norm_uniprot(uid: str) -> str:
    u = re.sub(r"[^A-Za-z0-9_]", "", (uid or "").strip()).upper()
    if _UNIPROT_ACC.match(u):
        return u
    raise ValueError(
        f"不像 UniProt Accession（如 P14679）。收到：{uid!r}。"
        "若是基因名（如 TYR / HTYR），请用「解析基因/蛋白名」或选预设「人源酪氨酸酶」。"
    )


def resolve_uniprot_query(
    query: str,
    *,
    organism_id: int = 9606,
    timeout: float = 25.0,
) -> List[Dict[str, str]]:
    """把基因名/中文名/英文名解析成 UniProt Accession。

    例：TYR、tyrosinase、酪氨酸酶、HTYR → P14679
    """
    q = (query or "").strip()
    if not q:
        return []

    # 已是 accession
    raw = re.sub(r"[^A-Za-z0-9]", "", q).upper()
    if _UNIPROT_ACC.match(raw):
        return [
            {
                "uniprot": raw,
                "name": raw,
                "gene": "",
                "organism": "",
                "note": "已是 UniProt Accession",
            }
        ]

    # 常见别名
    aliases = {
        "HTYR": "TYR",
        "酪氨酸酶": "TYR",
        "人源酪氨酸酶": "TYR",
        "HUMAN TYROSINASE": "TYR",
        "TYROSINASE": "TYR",
    }
    q_use = aliases.get(q.upper(), aliases.get(q, q))

    queries = [
        f"gene_exact:{q_use} AND organism_id:{organism_id} AND reviewed:true",
        f"gene:{q_use} AND organism_id:{organism_id} AND reviewed:true",
        f"({q_use}) AND organism_id:{organism_id} AND reviewed:true",
        f"({q}) AND reviewed:true",
    ]
    seen = set()
    out: List[Dict[str, str]] = []
    for uq in queries:
        try:
            r = requests.get(
                "https://rest.uniprot.org/uniprotkb/search",
                params={"query": uq, "format": "json", "size": 8},
                timeout=timeout,
            )
            if r.status_code != 200:
                continue
            for hit in r.json().get("results") or []:
                acc = (hit.get("primaryAccession") or "").upper()
                if not acc or acc in seen:
                    continue
                seen.add(acc)
                pname = (
                    ((hit.get("proteinDescription") or {}).get("recommendedName") or {})
                    .get("fullName", {})
                    .get("value")
                    or ""
                )
                genes = []
                for g in hit.get("genes") or []:
                    if isinstance(g, dict) and (g.get("geneName") or {}).get("value"):
                        genes.append(g["geneName"]["value"])
                org = (
                    (hit.get("organism") or {}).get("scientificName")
                    or (hit.get("organism") or {}).get("commonName")
                    or ""
                )
                out.append(
                    {
                        "uniprot": acc,
                        "name": pname,
                        "gene": ",".join(genes),
                        "organism": org,
                        "note": f"https://www.uniprot.org/uniprotkb/{acc}",
                    }
                )
            if out:
                break
        except Exception:
            continue
    return out


def fetch_rcsb_meta(pdb_id: str, timeout: float = 20.0) -> Dict[str, Any]:
    pid = _norm_pdb(pdb_id)
    try:
        r = requests.get(
            f"https://data.rcsb.org/rest/v1/core/entry/{pid}",
            timeout=timeout,
        )
        if r.status_code != 200:
            return {}
        data = r.json()
        struct = data.get("struct") or {}
        info = data.get("rcsb_entry_info") or {}
        return {
            "title": (struct.get("title") or "").strip(),
            "method": (((data.get("exptl") or [{}])[0] or {}).get("method") or ""),
            "resolution": info.get("resolution_combined"),
            "polymer_count": info.get("polymer_entity_count"),
            "deposited": (data.get("rcsb_accession_info") or {}).get("deposit_date"),
        }
    except Exception:
        return {}


def fetch_rcsb_pdb(
    pdb_id: str,
    *,
    fmt: str = "pdb",
    timeout: float = 60.0,
) -> Dict[str, Any]:
    pid = _norm_pdb(pdb_id)
    fmt = (fmt or "pdb").lower().strip()
    if fmt not in ("pdb", "cif"):
        raise ValueError("fmt 只能是 pdb 或 cif")

    url = f"https://files.rcsb.org/download/{pid}.{fmt}"
    r = requests.get(url, timeout=timeout)
    if r.status_code != 200 or not r.content or len(r.content) < 200:
        raise RuntimeError(f"RCSB 下载失败 {pid}.{fmt}：HTTP {r.status_code}")

    text = r.content.decode("utf-8", errors="replace")
    out_path = OUT_DIR / f"{pid}.{fmt}"
    out_path.write_bytes(r.content)

    return {
        "ok": True,
        "source": "RCSB PDB",
        "pdb_id": pid,
        "format": fmt,
        "url": url,
        "path": str(out_path),
        "bytes": len(r.content),
        "preview": text[:400],
        "meta": fetch_rcsb_meta(pid),
        "viewer": f"https://www.rcsb.org/3d-view/{pid}",
        "page": f"https://www.rcsb.org/structure/{pid}",
    }


def fetch_alphafold(uniprot_id: str, *, timeout: float = 60.0) -> Dict[str, Any]:
    uid = _norm_uniprot(uniprot_id)
    api = f"https://alphafold.ebi.ac.uk/api/prediction/{uid}"
    meta: Dict[str, Any] = {}
    pdb_url = ""
    try:
        mr = requests.get(api, timeout=min(timeout, 25))
        if mr.status_code == 200:
            arr = mr.json()
            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                meta = arr[0]
                pdb_url = meta.get("pdbUrl") or meta.get("pdb_url") or ""
    except Exception:
        meta = {}

    candidates = []
    if pdb_url:
        candidates.append(pdb_url)
    for ver in ("v4", "v3", "v2"):
        candidates.append(
            f"https://alphafold.ebi.ac.uk/files/AF-{uid}-F1-model_{ver}.pdb"
        )

    last_err = ""
    content = b""
    used = ""
    for url in candidates:
        try:
            r = requests.get(url, timeout=timeout)
            if r.status_code == 200 and r.content and len(r.content) > 200:
                content = r.content
                used = url
                break
            last_err = f"HTTP {r.status_code}"
        except Exception as exc:
            last_err = str(exc)

    if not content:
        raise RuntimeError(f"AlphaFold 下载失败 UniProt={uid}：{last_err or '无模型'}")

    out_path = OUT_DIR / f"AF-{uid}-F1.pdb"
    out_path.write_bytes(content)
    text = content.decode("utf-8", errors="replace")

    return {
        "ok": True,
        "source": "AlphaFold DB",
        "uniprot": uid,
        "format": "pdb",
        "url": used,
        "path": str(out_path),
        "bytes": len(content),
        "preview": text[:400],
        "meta": {
            "gene": meta.get("gene") or meta.get("geneName") or "",
            "organism": meta.get("organismScientificName") or meta.get("organism") or "",
            "uniprotDescription": meta.get("uniprotDescription") or meta.get("proteinName") or "",
            "modelCreated": meta.get("modelCreatedDate") or "",
            "latestVersion": meta.get("latestVersion") or "",
        },
        "viewer": f"https://alphafold.ebi.ac.uk/entry/{uid}",
        "page": f"https://alphafold.ebi.ac.uk/entry/{uid}",
    }


def search_rcsb_text(query: str, *, limit: int = 8, timeout: float = 25.0) -> List[Dict[str, str]]:
    q = (query or "").strip()
    if not q:
        return []
    payload = {
        "query": {
            "type": "terminal",
            "service": "full_text",
            "parameters": {"value": q},
        },
        "return_type": "entry",
        "request_options": {
            "paginate": {"start": 0, "rows": limit},
            "results_content_type": ["experimental"],
            "sort": [{"sort_by": "score", "direction": "desc"}],
        },
    }
    try:
        r = requests.post(
            "https://search.rcsb.org/rcsbsearch/v2/query",
            json=payload,
            timeout=timeout,
        )
        if r.status_code != 200:
            return []
        hits = []
        for item in r.json().get("result_set") or []:
            pid = (item.get("identifier") or "").upper()
            if pid:
                hits.append(
                    {
                        "pdb_id": pid,
                        "score": str(item.get("score") or ""),
                        "page": f"https://www.rcsb.org/structure/{pid}",
                    }
                )
        return hits
    except Exception:
        return []


def resolve_preset(key: str) -> Optional[Dict[str, str]]:
    for p in PROTEASE_PRESETS:
        if p["key"] == key:
            return dict(p)
    return None
