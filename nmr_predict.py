"""产物 ¹H / ¹³C NMR 化学位移预测（NMRShiftDB2 公开接口）。

溶剂常用：氘代氯仿 CDCl3、氘代 DMSO（DMSO-d6）。
返回峰表（ppm），并可选画简易谱图。预测值供参考，不等同实验谱。
"""

from __future__ import annotations

import io
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote
from xml.etree import ElementTree as ET

import requests

BASE = "https://nmrshiftdb.nmr.uni-koeln.de"

# NMRShiftDB 官方溶剂字符串
SOLVENTS: Dict[str, str] = {
    "CDCl3": "Chloroform-D1 (CDCl3)",
    "DMSO-d6": "Dimethylsulphoxide-D6 (DMSO-D6, C2D6SO)",
}

SOLVENT_LABELS = {
    "CDCl3": "氘代氯仿 (CDCl₃)",
    "DMSO-d6": "氘代 DMSO (DMSO-d₆)",
}

# 氘代溶剂残峰（不含水峰）
SOLVENT_RESIDUAL_PEAKS: Dict[str, Dict[str, List[Dict[str, Any]]]] = {
    "CDCl3": {
        "1H": [
            {
                "ppm": 7.26,
                "multiplicity": "s",
                "n_h": 0,
                "note": "CDCl3 残峰 (CHCl3)",
                "origin": "solvent",
            },
        ],
        "13C": [
            {
                "ppm": 77.16,
                "multiplicity": "t",
                "n_h": 0,
                "note": "CDCl3 溶剂峰",
                "origin": "solvent",
            },
        ],
    },
    "DMSO-d6": {
        "1H": [
            {
                "ppm": 2.50,
                "multiplicity": "p",
                "n_h": 0,
                "note": "DMSO-d6 残峰 (DMSO-d5)",
                "origin": "solvent",
            },
        ],
        "13C": [
            {
                "ppm": 39.52,
                "multiplicity": "sept",
                "n_h": 0,
                "note": "DMSO-d6 溶剂峰",
                "origin": "solvent",
            },
        ],
    },
}


def add_solvent_residual_peaks(
    peaks: List[NMRPeak],
    nucleus: str,
    solvent_key: str,
) -> List[NMRPeak]:
    """始终补上氘代溶剂残峰（不计入产物积分；不含水分峰）。"""
    key = solvent_key if solvent_key in SOLVENT_RESIDUAL_PEAKS else "CDCl3"
    extras = (SOLVENT_RESIDUAL_PEAKS.get(key) or {}).get(nucleus) or []
    # 先去掉旧溶剂/水峰，再强制加入标准残峰（避免漏标）
    out = [p for p in peaks if (p.origin or "product") not in ("solvent", "water")]
    for e in extras:
        out.append(
            NMRPeak(
                ppm=float(e["ppm"]),
                multiplicity=str(e.get("multiplicity") or ""),
                atoms="",
                n_h=0,
                note=str(e.get("note") or ""),
                origin=str(e.get("origin") or "solvent"),
            )
        )
    out.sort(key=lambda p: p.ppm, reverse=True)
    return out


@dataclass
class NMRPeak:
    ppm: float
    multiplicity: str = ""
    atoms: str = ""  # atomRefs
    n_h: int = 0  # ¹H: 该峰关联的 H 数近似
    note: str = ""
    origin: str = "product"  # product | solvent | water


@dataclass
class NMRSpectrum:
    nucleus: str  # 1H | 13C
    solvent_key: str
    solvent_name: str
    smiles: str
    peaks: List[NMRPeak] = field(default_factory=list)
    source: str = "NMRShiftDB2"
    predicted: bool = True
    error: str = ""
    raw_meta: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _strip_ns(root: ET.Element) -> ET.Element:
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _resolve_solvent(solvent: str) -> Tuple[str, str]:
    s = (solvent or "CDCl3").strip()
    # 允许别名
    aliases = {
        "cdcl3": "CDCl3",
        "chloroform": "CDCl3",
        "氘代氯仿": "CDCl3",
        "dmso": "DMSO-d6",
        "dmso-d6": "DMSO-d6",
        "dmso_d6": "DMSO-d6",
        "氘代dmso": "DMSO-d6",
        "氘代DMSO": "DMSO-d6",
    }
    key = aliases.get(s.lower(), s if s in SOLVENTS else "CDCl3")
    return key, SOLVENTS[key]


def _parse_peaks(root: ET.Element, nucleus: str) -> Tuple[List[NMRPeak], Dict[str, str]]:
    atoms = {a.get("id"): a.attrib for a in root.iter("atom")}
    meta: Dict[str, str] = {}
    for m in root.iter("metadata"):
        name = m.get("name") or ""
        content = m.get("content") or (m.text or "")
        if name:
            meta[name] = content

    raw_peaks: List[NMRPeak] = []
    for peak in root.iter("peak"):
        try:
            ppm = float(peak.get("xValue") or "nan")
        except ValueError:
            continue
        if ppm != ppm:  # NaN
            continue
        refs = (peak.get("atomRefs") or "").strip()
        ref_ids = refs.split() if refs else []
        mult = (peak.get("peakMultiplicity") or "").strip()
        n_h = 0
        notes = []
        for rid in ref_ids:
            a = atoms.get(rid) or {}
            et = (a.get("elementType") or "").upper()
            if et:
                notes.append(et)
            if et == "H":
                # 显式氢原子：每个算 1H
                n_h += 1
                continue
            hc = a.get("hydrogenCount")
            if hc is not None and str(hc).isdigit() and int(hc) > 0:
                # 指到 C/N/O 时用该原子上的氢数
                n_h += int(hc)
        # ¹H 且 refs 指向库里不存在的隐式氢 id：按 refs 个数计
        if nucleus == "1H" and n_h == 0 and ref_ids:
            n_h = len(ref_ids)
        if nucleus == "13C" and n_h == 0:
            for rid in ref_ids:
                a = atoms.get(rid) or {}
                hc = a.get("hydrogenCount")
                if hc is not None and str(hc).isdigit():
                    n_h = int(hc)
                    break
        raw_peaks.append(
            NMRPeak(
                ppm=round(ppm, 2),
                multiplicity=mult,
                atoms=refs,
                n_h=n_h,
                note=",".join(notes),
            )
        )

    if nucleus != "1H":
        raw_peaks.sort(key=lambda p: p.ppm, reverse=True)
        return raw_peaks, meta

    # ¹H：NMRShiftDB 常把等价氢拆成多条同 ppm 的 1H → 合并积分
    from collections import OrderedDict

    buckets: "OrderedDict[float, List[NMRPeak]]" = OrderedDict()
    for p in raw_peaks:
        # 0.02 ppm 内视为同一化学位移
        key = round(p.ppm * 50) / 50.0  # 0.02 格
        key = round(key, 2)
        buckets.setdefault(key, []).append(p)

    merged: List[NMRPeak] = []
    for ppm_key, group in buckets.items():
        # 每条峰至少贡献 1H（显式氢预测）
        total_h = 0
        for p in group:
            total_h += p.n_h if p.n_h and p.n_h > 0 else 1
        mults = [p.multiplicity for p in group if p.multiplicity]
        # 多数表决多重性
        mult = max(set(mults), key=mults.count) if mults else ""
        all_refs = " ".join(p.atoms for p in group if p.atoms).strip()
        avg_ppm = sum(p.ppm for p in group) / len(group)
        merged.append(
            NMRPeak(
                ppm=round(avg_ppm, 2),
                multiplicity=mult,
                atoms=all_refs,
                n_h=total_h,
                note=f"merged×{len(group)}" if len(group) > 1 else (group[0].note or ""),
            )
        )
    merged.sort(key=lambda p: p.ppm, reverse=True)
    meta["1H_merge"] = "equivalent shifts merged for integration"
    return merged, meta


def predict_nmr(
    smiles: str,
    nucleus: str = "1H",
    solvent: str = "CDCl3",
    *,
    timeout: float = 120.0,
) -> NMRSpectrum:
    """调用 NMRShiftDB searchorpredict，返回峰表。"""
    smiles = (smiles or "").strip()
    nucleus = "13C" if str(nucleus).upper().replace(" ", "") in ("13C", "C13", "CARBON") else "1H"
    key, sol_name = _resolve_solvent(solvent)
    if not smiles:
        return NMRSpectrum(
            nucleus=nucleus,
            solvent_key=key,
            solvent_name=sol_name,
            smiles="",
            error="SMILES 为空",
        )

    path = (
        f"/NmrshiftdbServlet/nmrshiftdbaction/searchorpredict/"
        f"smiles/{quote(smiles, safe='')}/spectrumtype/{nucleus}"
        f"/solvent/{quote(sol_name, safe='')}"
    )
    url = BASE + path
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        root = _strip_ns(ET.fromstring(resp.content))
        peaks, meta = _parse_peaks(root, nucleus)
        # 无溶剂时再试一次（部分结构溶剂路径失败）
        if not peaks:
            path2 = (
                f"/NmrshiftdbServlet/nmrshiftdbaction/searchorpredict/"
                f"smiles/{quote(smiles, safe='')}/spectrumtype/{nucleus}"
            )
            resp2 = requests.get(BASE + path2, timeout=timeout)
            resp2.raise_for_status()
            root2 = _strip_ns(ET.fromstring(resp2.content))
            peaks, meta = _parse_peaks(root2, nucleus)
            meta["solvent_fallback"] = "unreported"
        peaks = add_solvent_residual_peaks(peaks, nucleus, key)
        return NMRSpectrum(
            nucleus=nucleus,
            solvent_key=key,
            solvent_name=sol_name,
            smiles=smiles,
            peaks=peaks,
            predicted=True,
            raw_meta=meta,
            error="" if peaks else "未返回峰",
        )
    except Exception as exc:  # noqa: BLE001
        return NMRSpectrum(
            nucleus=nucleus,
            solvent_key=key,
            solvent_name=sol_name,
            smiles=smiles,
            error=str(exc),
        )

def predict_both(
    smiles: str,
    solvent: str = "CDCl3",
    *,
    timeout: float = 120.0,
) -> Dict[str, NMRSpectrum]:
    return {
        "1H": predict_nmr(smiles, "1H", solvent, timeout=timeout),
        "13C": predict_nmr(smiles, "13C", solvent, timeout=timeout),
    }


def spectrum_to_rows(spec: NMRSpectrum) -> List[Dict[str, Any]]:
    origin_cn = {"product": "产物", "solvent": "溶剂残峰", "water": "水峰"}
    rows = []
    for i, p in enumerate(spec.peaks, 1):
        origin = p.origin or "product"
        row: Dict[str, Any] = {
            "#": i,
            "归属": origin_cn.get(origin, origin),
            "δ / ppm": p.ppm,
            "多重性": p.multiplicity or "—",
            "说明": p.note or "—",
        }
        if spec.nucleus == "1H":
            if origin == "product":
                row["积分 (H数)"] = p.n_h if p.n_h else "—"
            else:
                row["积分 (H数)"] = "—（不计产物）"
        else:
            if origin == "product":
                row["类型"] = {0: "C", 1: "CH", 2: "CH₂", 3: "CH₃"}.get(p.n_h, "—")
            else:
                row["类型"] = "溶剂"
        rows.append(row)
    return rows


def expected_h_count(smiles: str) -> Optional[int]:
    """结构式应有的氢原子总数（含 OH/NH）。"""
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        mol = Chem.AddHs(mol)
        return sum(1 for a in mol.GetAtoms() if a.GetAtomicNum() == 1)
    except Exception:
        return None


def format_peak_list_text(spec: NMRSpectrum) -> str:
    """类似实验报告的一行峰列表。"""
    if spec.error:
        return f"{spec.nucleus} ({spec.solvent_key}): 失败 — {spec.error}"
    if not spec.peaks:
        return f"{spec.nucleus} ({spec.solvent_key}): 无峰"
    prod_bits = []
    sol_bits = []
    for p in spec.peaks:
        part = f"{p.ppm}"
        if p.multiplicity:
            part += f" ({p.multiplicity})"
        origin = p.origin or "product"
        if origin != "product":
            sol_bits.append(f"{part} [{p.note or origin}]")
            continue
        if spec.nucleus == "1H" and p.n_h:
            part += f", {p.n_h}H"
        elif spec.nucleus == "13C" and p.n_h is not None and p.n_h >= 0:
            lab = {0: "C", 1: "CH", 2: "CH₂", 3: "CH₃"}.get(p.n_h, f"CH{p.n_h}")
            part += f", {lab}"
        prod_bits.append(part)
    title = f"{spec.nucleus} NMR ({spec.solvent_key}, pred./NMRShiftDB) δ"
    text = title + " " + "; ".join(prod_bits) + "."
    if sol_bits:
        text += " solvent residual: " + "; ".join(sol_bits) + "."
    return text


def plot_stick_spectrum(spec: NMRSpectrum, *, title: Optional[str] = None):
    """简易 stick 谱图（matplotlib Figure），失败返回 None。

    标题只用 ASCII/英文，避免 Windows 默认字体缺中文导致方块（豆腐字）。
    """
    if not spec.peaks:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    if spec.nucleus == "1H":
        xmax, xmin = 12.0, -0.5
    else:
        xmax, xmin = 220.0, -5.0

    fig, ax = plt.subplots(figsize=(8, 2.8), dpi=120)
    max_h = 1.0
    for p in spec.peaks:
        origin = p.origin or "product"
        if origin == "solvent":
            color, h, lw = "#c0392b", 1.2, 2.2  # red: solvent
        elif origin == "water":
            color, h, lw = "#2980b9", 0.9, 1.8  # blue: water
        else:
            h = float(max(1, p.n_h)) if spec.nucleus == "1H" else 1.0
            color, lw = "#1f4e79", 1.6
        max_h = max(max_h, h)
        ax.vlines(p.ppm, 0, h, colors=color, linewidths=lw)
    ax.set_xlim(xmax, xmin)
    ax.set_ylim(0, max_h * 1.35)
    ax.set_xlabel("chemical shift / ppm")
    ax.set_yticks([])
    ax.set_title(
        title
        or f"{spec.nucleus} NMR ({spec.solvent_key}) · navy=product, red=solvent residual"
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    fig.tight_layout()
    return fig


def fig_to_png_bytes(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    buf.seek(0)
    return buf.read()


def _pubchem_cid_and_names(smiles: str) -> Tuple[Optional[int], List[str]]:
    """PubChem 查 CID + 英文名（检索文献用）。"""
    names: List[str] = []
    cid: Optional[int] = None
    try:
        from rdkit import Chem

        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None, []
        canon = Chem.MolToSmiles(mol)
        r = requests.post(
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/cids/JSON",
            data={"smiles": canon},
            timeout=25,
        )
        if r.status_code == 200:
            cids = (r.json().get("IdentifierList") or {}).get("CID") or []
            if cids:
                cid = int(cids[0])
        if cid:
            pr = requests.get(
                f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/"
                "IUPACName,Title/JSON",
                timeout=20,
            )
            if pr.status_code == 200:
                props = (pr.json().get("PropertyTable") or {}).get("Properties") or []
                if props:
                    for k in ("Title", "IUPACName"):
                        v = (props[0].get(k) or "").strip()
                        if v and v not in names:
                            names.append(v)
            syn = requests.get(
                f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/synonyms/JSON",
                timeout=20,
            )
            if syn.status_code == 200:
                info = (syn.json().get("InformationList") or {}).get("Information") or []
                syns = (info[0].get("Synonym") or []) if info else []
                for s in syns[:10]:
                    s = (s or "").strip()
                    if (
                        s
                        and 3 <= len(s) <= 80
                        and "=" not in s
                        and s not in names
                        and not s.lower().startswith("cid")
                    ):
                        names.append(s)
    except Exception:
        pass
    return cid, names


def _mol_names_and_id(smiles: str, nucleus: str = "13C") -> Tuple[str, List[str], Optional[str]]:
    """优先 PubChem 名；再补 NMRShiftDB 标题/ID。"""
    names: List[str] = []
    mol_id: Optional[str] = None
    _, pc_names = _pubchem_cid_and_names(smiles)
    names.extend(pc_names)

    try:
        path = (
            f"/NmrshiftdbServlet/nmrshiftdbaction/searchorpredict/"
            f"smiles/{quote(smiles, safe='')}/spectrumtype/{nucleus}"
        )
        resp = requests.get(BASE + path, timeout=60)
        resp.raise_for_status()
        root = _strip_ns(ET.fromstring(resp.content))
        for mol in root.iter("molecule"):
            mid = (mol.get("id") or "").replace("nmrshiftdb", "")
            if mid.isdigit():
                mol_id = mid
            title = (mol.get("title") or "").strip()
            if title:
                for n in title.split(";"):
                    n = n.strip()
                    if n and n not in names:
                        names.append(n)
            break
    except Exception:
        pass

    if not names:
        try:
            from rdkit import Chem

            mol = Chem.MolFromSmiles(smiles)
            if mol is not None:
                names.append(Chem.MolToSmiles(mol))
        except Exception:
            names.append(smiles)
    return smiles, names[:10], mol_id


def _is_bad_doi(doi: str, title: str) -> bool:
    """过滤补充材料 / 文件型 DOI（常 403）。"""
    d = (doi or "").lower()
    t = (title or "").lower().strip()
    if t.endswith((".pdf", ".docx", ".doc", ".zip", ".cif")):
        return True
    if d.endswith((".pdf", ".docx")):
        return True
    # 10.xxx/yyy.s001 类 SI
    if ".s" in d.split("/")[-1] and any(ch.isdigit() for ch in d.split("/")[-1]):
        tail = d.split("/")[-1]
        if ".s" in tail and tail.split(".s")[-1].isdigit():
            return True
    if t.startswith("figure ") and "nmr" not in t:
        return True
    return False





def search_nmr_literature(
    smiles: str,
    solvent: str = "CDCl3",
    *,
    limit: int = 8,
) -> List[Dict[str, str]]:
    """NMR 文献：SciFinder 结构检索为主 + 同/近结构论文标题（可跳转）。"""
    from urllib.parse import quote_plus

    from chem_names import literature_query_terms, scifinder_copy_block
    from literature import search_compound_papers

    key, _ = _resolve_solvent(solvent)
    sol_short = "CDCl3" if key == "CDCl3" else "DMSO-d6"
    terms = literature_query_terms(smiles)
    iupac_en = (terms.get("iupac_en") or terms.get("iupac") or "").strip()
    iupac_zh = (terms.get("iupac_zh") or "").strip()
    inchikey = (terms.get("inchikey") or "").strip()
    smiles_c = (terms.get("smiles") or smiles).strip()
    display_name = iupac_en or iupac_zh or inchikey or smiles_c

    hits: List[Dict[str, str]] = []

    # SciFinder：找别人做过的 NMR 谱（主推）
    hits.append(
        {
            "title": "SciFinder-n：用结构找别人做过的 NMR 谱（主推）",
            "url": "https://scifinder-n.cas.org/",
            "source": "SciFinder-n",
            "relevance": f"化合物：{display_name}",
            "note": "登录 → Substances 粘贴 SMILES → Refine：NMR / 1H NMR / 13C NMR",
            "copy_text": scifinder_copy_block(terms=terms),
            "how": (
                "1. 打开 SciFinder-n 登录\n"
                "2. Substances → 粘贴下方 SMILES（或 Import .mol）\n"
                "3. Refine → NMR / 1H NMR / 13C NMR → 查看实验谱与文献"
            ),
            "openable": "portal",
            "kind": "scifinder",
            "smiles": smiles_c,
            "inchikey": inchikey,
        }
    )

    # 具体论文（同名/相近结构）
    for p in search_compound_papers(
        iupac_en=iupac_en,
        iupac_zh=iupac_zh,
        inchikey=inchikey,
        smiles=smiles_c,
        limit=limit,
    ):
        hits.append(
            {
                "title": p.get("paper_title") or p.get("title") or "",
                "paper_title": p.get("paper_title") or "",
                "url": p.get("url_baidu") or p.get("url") or "",
                "url_pubmed": p.get("url_pubmed") or "",
                "source": p.get("source") or "paper",
                "relevance": f"可能含本化合物或相近结构 · {p.get('note') or ''}",
                "note": p.get("note") or "",
                "how": p.get("how") or "",
                "openable": "yes",
                "kind": "paper",
            }
        )

    # 快捷站
    if iupac_en:
        hits.append(
            {
                "title": f"PubMed 搜化合物名 + NMR：{iupac_en}",
                "url": (
                    "https://pubmed.ncbi.nlm.nih.gov/?term="
                    + quote_plus(f'"{iupac_en}" AND (NMR OR "1H NMR")')
                ),
                "source": "PubMed",
                "relevance": f"英文名：{iupac_en}",
                "copy_text": iupac_en,
                "openable": "yes",
                "kind": "pubmed",
            }
        )
    if iupac_zh or iupac_en:
        kw = iupac_zh or iupac_en
        hits.append(
            {
                "title": f"知网搜：{kw}",
                "url": "https://kns.cnki.net/kns8s/defaultresult/index?kw="
                + quote_plus(f"{kw} NMR"),
                "source": "知网",
                "relevance": f"检索词：{kw}",
                "copy_text": kw,
                "openable": "yes",
                "kind": "cnki",
            }
        )

    seen = set()
    out: List[Dict[str, str]] = []
    for h in hits:
        key_u = (h.get("url") or "") + "|" + (h.get("title") or "")
        if key_u in seen:
            continue
        seen.add(key_u)
        out.append(h)
        if len(out) >= limit + 4:
            break
    return out


def build_ms_scifinder_guide(smiles: str) -> Dict[str, str]:
    """质谱 / NMR：SciFinder 专用可复制包（不重复解析命名）。"""
    from chem_names import literature_query_terms, scifinder_copy_block

    t = literature_query_terms(smiles)
    return {
        "portal": "https://scifinder-n.cas.org/",
        "copy_block": scifinder_copy_block(terms=t),
        "smiles": t.get("smiles") or smiles,
        "inchi": t.get("inchi") or "",
        "inchikey": t.get("inchikey") or "",
        "molfile": t.get("molfile") or "",
        "iupac_en": t.get("iupac_en") or "",
        "iupac_zh": t.get("iupac_zh") or "",
        "how_nmr": (
            "登录 SciFinder-n → Substances → 粘贴 SMILES → "
            "Refine：NMR / 1H NMR / 13C NMR（查看别人做过的实验谱）"
        ),
        "how_ms": (
            "同一结构 → Refine：mass spectrum / HRMS / ESI-MS"
        ),
        "how": (
            "登录 SciFinder-n → Substances → 粘贴 SMILES/InChI 或 Import Molfile → "
            "NMR：Refine NMR；质谱：Refine HRMS / ESI-MS"
        ),
    }
