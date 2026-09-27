"""对接结果可视化：文献盒子、氢键/残基分析、PyMOL 高颜值双图 + PNG。"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 文献支撑的推荐 Grid Box（UI 展示用）
# ---------------------------------------------------------------------------
LITERATURE_BOXES: Dict[str, Dict[str, Any]] = {
    "tyr_cu_mid": {
        "label": "人源酪氨酸酶 TYR · 双铜中点",
        "center": None,  # 运行时由 CuA/CuB 中点填入
        "center_note": "CuA–CuB 几何中心（补铜后自动计算）",
        "size": (25.0, 25.0, 25.0),
        "paper": (
            "Vecura Biotech Insiders #03: Building a Humanized Tyrosinase Model "
            "for Structure-Based Docking"
        ),
        "authors": "Vecura / gnina workflow",
        "year": "2024",
        "journal": "Vecura Insights (method note)",
        "doi_or_url": "https://vecura.com/en/insights/vecura-biotech-insiders-03-building-a-humanized-tyrosinase-model-for-structure-based-docking",
        "detail": (
            "活性位点：CuA←His180/202/211，CuB←His363/367/390（UniProt P14679）；"
            "盒子中心取两铜中点，边长 25×25×25 Å（gnina/Vina 搜索）。"
        ),
        "extra_refs": [
            {
                "paper": (
                    "Histidine residues at the copper-binding site in human "
                    "tyrosinase are essential for its catalytic activities"
                ),
                "note": "确认人源 TYR 双铜配位 His 编号",
            },
            {
                "paper": "UniProtKB P14679 (TYRO_HUMAN)",
                "note": "序列与金属位点注释",
            },
        ],
    },
    "tyrp1_zn_5m8o": {
        "label": "人源 TYRP1 · PDB 5M8O 双锌中点",
        "center": (-11.020, 0.347, -23.444),
        "center_note": "链 A Zn513 + Zn514 中点（晶体坐标）",
        "size": (22.0, 22.0, 22.0),
        "paper": (
            "Structure of Human Tyrosinase Related Protein 1 Reveals a "
            "Binuclear Zinc Active Site Important for Melanogenesis"
        ),
        "authors": "Lai X, Wichers HJ, Soler-Lopez M, Dijkstra BW",
        "year": "2017",
        "journal": "Angew. Chem. Int. Ed. 56, 9812–9815",
        "doi_or_url": "https://doi.org/10.1002/anie.201704616",
        "detail": (
            "PDB 5M8O（tropolone 共晶）chain A：ZnA≈(-12.467,-0.306,-23.279)，"
            "ZnB≈(-9.572,0.999,-23.609)；中点 (-11.020,0.347,-23.444)；"
            "推荐盒子 22×22×22 Å（Vina 搜索覆盖双核金属口袋）。"
        ),
        "extra_refs": [
            {
                "paper": (
                    "Tyrp1 Mutant Variants Associated with OCA3: Computational "
                    "Characterization of Protein Stability and Ligand Binding"
                ),
                "note": "网格以双锌+桥接水为中心（Glide 内壳约 10 Å）",
            },
        ],
    },
    "mpro_6lu7": {
        "label": "SARS-CoV-2 Mpro · PDB 6LU7",
        "center": (-10.235, 17.563, 67.358),
        "center_note": "共晶抑制剂 N3 附近活性口袋",
        "size": (22.0, 22.0, 22.0),
        "paper": (
            "Structure of Mpro from SARS-CoV-2 and discovery of its inhibitors"
        ),
        "authors": "Jin Z, et al.",
        "year": "2020",
        "journal": "Nature 582, 289–293",
        "doi_or_url": "https://doi.org/10.1038/s41586-020-2223-y",
        "detail": "主蛋白酶底物结合口袋；推荐立方盒子约 22 Å。",
        "extra_refs": [],
    },
    "auto": {
        "label": "自动推断（金属 → 共晶配体 → CA 中心）",
        "center": None,
        "center_note": "由结构自动推断",
        "size": (22.0, 22.0, 22.0),
        "paper": "AutoDock Vina 常规实践（活性位点覆盖）",
        "authors": "Trott O, Olson AJ",
        "year": "2010",
        "journal": "J. Comput. Chem. 31, 455–461",
        "doi_or_url": "https://doi.org/10.1002/jcc.21334",
        "detail": "无专属文献坐标时用 22×22×22 Å 覆盖推断中心。",
        "extra_refs": [],
    },
    "manual": {
        "label": "手动精确坐标",
        "center": None,
        "center_note": "用户输入",
        "size": (25.0, 25.0, 25.0),
        "paper": "—（用户自定义，建议注明来源文献）",
        "authors": "—",
        "year": "—",
        "journal": "—",
        "doi_or_url": "",
        "detail": "请把文献 grid 的 center/size 填入右侧数值框。",
        "extra_refs": [],
    },
}

# 兼容旧名
RECOMMENDED_BOX_SIZE = {
    k: {
        "size": float(v["size"][0]),
        "cite": f"{v['paper']} ({v['year']}) · {v['size'][0]:.0f} Å · {v['detail']}",
        "paper": v["paper"],
        "journal": v.get("journal") or "",
        "doi_or_url": v.get("doi_or_url") or "",
    }
    for k, v in LITERATURE_BOXES.items()
}

DONOR_ACCEPTOR = {"N", "O", "S", "F"}


def pdbqt_to_pdb_text(pdbqt: str, *, model: int = 1) -> str:
    """取 Vina 多构象 PDBQT 中第 model 个 MODEL，写成简易 PDB。"""
    text = pdbqt or ""
    models = re.split(r"(?=^MODEL\s)", text, flags=re.M)
    chunks = [
        m
        for m in models
        if m.strip().startswith("MODEL") or "ATOM" in m or "HETATM" in m
    ]
    if not chunks:
        chunks = [text]
    idx = max(0, min(model - 1, len(chunks) - 1))
    block = chunks[idx]
    out: List[str] = []
    for line in block.splitlines():
        if line.startswith(("ATOM", "HETATM")):
            atom = line[:66].ljust(66)
            if len(line) >= 78:
                elem = line[77:79].strip() or line[12:14].strip()[:1]
            else:
                elem = line[12:14].strip()[:1] or "C"
            out.append(f"{atom}          {elem[:2]:<2s}")
        elif line.startswith("ENDMDL"):
            break
    out.append("END")
    return "\n".join(out) + "\n"


def extract_model_pdbqt(out_pdbqt: Path, dest: Path, *, model: int = 1) -> Path:
    """抽出第 model 个构象为单独 PDBQT（作图用第一个）。"""
    text = Path(out_pdbqt).read_text(encoding="utf-8", errors="replace")
    models = re.split(r"(?=^MODEL\s)", text, flags=re.M)
    chunks = [m for m in models if m.strip().startswith("MODEL")]
    if not chunks:
        Path(dest).write_text(text, encoding="utf-8")
        return Path(dest)
    idx = max(0, min(model - 1, len(chunks) - 1))
    block = chunks[idx]
    if not block.rstrip().endswith("ENDMDL"):
        block = block.rstrip() + "\nENDMDL\n"
    Path(dest).write_text(block, encoding="utf-8")
    return Path(dest)


def extract_best_pose_pdb(out_pdbqt: Path, dest: Path, *, model: int = 1) -> Path:
    text = Path(out_pdbqt).read_text(encoding="utf-8", errors="replace")
    dest = Path(dest)
    dest.write_text(pdbqt_to_pdb_text(text, model=model), encoding="utf-8")
    return dest


def has_embedded_pymol() -> bool:
    """当前 venv 是否可用 pymol2（无需单独装桌面版）。"""
    try:
        from pymol2 import PyMOL  # noqa: F401

        return True
    except Exception:
        return False


# 热重载兼容别名（Streamlit 偶发缺符号时仍可 getattr）
embedded_pymol_ready = has_embedded_pymol


def _pymol2_apply_beautify(cmd) -> None:
    cmd.bg_color("white")
    cmd.set("ray_shadows", 0)
    cmd.set("ray_shadow", 0)
    cmd.set("ray_transparency_shadows", 0)
    cmd.set("specular", 0)
    cmd.set("cartoon_highlight_color", "grey")
    cmd.set("ray_trace_depth_factor", 1)
    cmd.set("ray_trace_disco_factor", 1)
    cmd.set("ray_trace_mode", 1)
    cmd.set("antialias", 2)
    cmd.set("cartoon_fancy_helices", 1)
    cmd.set("stick_radius", 0.18)
    cmd.set("dash_width", 2.5)
    cmd.set("dash_color", "green")
    cmd.set("label_distance_digits", 2)
    cmd.set("label_size", 18)
    cmd.set("label_color", "black")
    cmd.set("ray_opaque_background", 1)


def _pymol2_color_by_element(cmd, sele: str) -> None:
    """等同 util.cnc，但绑定 pymol2 的 cmd 实例。"""
    try:
        from pymol import util as _util

        _util.cnc(sele, _self=cmd)
    except Exception:
        cmd.color("atomic", f"(({sele}) and not elem C)")


def render_publication_pngs_pymol2(
    work_dir: Path | str,
    *,
    receptor_pdb: Path | str,
    ligand_path: Path | str,
    contacts: Dict[str, Any],
    width: int = 1400,
    height: int = 1050,
    dpi: int = 300,
) -> Dict[str, Any]:
    """用内嵌 pymol2 直接渲染 fig1/fig2 PNG（无需 pymol.exe）。

    全蛋白射线追踪约 1–3 分钟；默认 1400×1050。
    """
    from pymol2 import PyMOL

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    rec = Path(receptor_pdb).resolve()
    lig = Path(ligand_path).resolve()
    fig1 = work / "fig1_overview.png"
    fig2 = work / "fig2_pocket.png"

    key = (contacts.get("key_residues") or [])[:9]
    if key:
        parts = []
        by_chain: Dict[str, List[int]] = {}
        for r in key:
            by_chain.setdefault(r.get("chain") or "A", []).append(int(r["resi"]))
        for ch, ids in by_chain.items():
            parts.append(f"(chain {ch} and resi {'+'.join(str(i) for i in ids)})")
        key_sele = " or ".join(parts)
    else:
        key_sele = "(byres (pro within 4 of lig))"

    p = PyMOL()
    p.start()
    cmd = p.cmd
    try:
        # —— 图1 全景 ——
        cmd.delete("all")
        _pymol2_apply_beautify(cmd)
        cmd.load(str(rec), "pro")
        cmd.load(str(lig), "lig")
        cmd.hide("everything", "all")
        cmd.show("cartoon", "pro")
        cmd.color("gray80", "pro")
        _pymol2_color_by_element(cmd, "pro")
        cmd.show("sticks", "lig")
        cmd.color("yellow", "lig")
        _pymol2_color_by_element(cmd, "lig")
        cmd.show("spheres", "pro and elem Cu+Zn")
        cmd.color("orange", "pro and elem Cu")
        cmd.color("marine", "pro and elem Zn")
        cmd.set("sphere_scale", 0.4, "pro and elem Cu+Zn")
        cmd.orient("lig")
        cmd.zoom("lig", 25)
        cmd.center("lig")
        cmd.png(str(fig1), width, height, dpi=dpi, ray=1)

        # —— 图2 口袋 + 氢键键长 ——
        cmd.delete("all")
        _pymol2_apply_beautify(cmd)
        cmd.load(str(rec), "pro")
        cmd.load(str(lig), "lig")
        cmd.hide("everything", "all")
        cmd.show("cartoon", "pro")
        cmd.color("gray80", "pro")
        cmd.set("cartoon_transparency", 0.8)
        cmd.select("keyres", f"({key_sele}) and polymer")
        cmd.show("sticks", "keyres")
        cmd.color("palecyan", "keyres")
        _pymol2_color_by_element(cmd, "keyres")
        cmd.show("sticks", "lig")
        cmd.color("yellow", "lig")
        _pymol2_color_by_element(cmd, "lig")
        cmd.show("spheres", "pro and elem Cu+Zn")
        cmd.color("orange", "pro and elem Cu")
        cmd.set("sphere_scale", 0.35, "pro and elem Cu+Zn")

        hbonds = contacts.get("hbonds") or []
        if hbonds:
            for i, h in enumerate(hbonds[:12], 1):
                pro_sel = h.get("pymol_pro") or f"(pro and resi {h.get('resi')})"
                lig_sel = h.get("pymol_lig") or "(lig)"
                try:
                    cmd.distance(f"hb{i}", pro_sel, lig_sel, 3.6, 0)
                    cmd.color("green", f"hb{i}")
                except Exception:
                    continue
        else:
            try:
                cmd.distance("hbonds", "lig", "keyres", 3.6, 2)
                cmd.color("green", "hbonds")
            except Exception:
                pass
        cmd.set("label_distance_digits", 2)
        try:
            cmd.label("keyres and name CA", '"%s%s" % (resn,resi)')
        except Exception:
            pass
        cmd.orient("lig")
        try:
            cmd.zoom("keyres", 5)
        except Exception:
            cmd.zoom("lig", 12)
        cmd.center("lig")
        cmd.png(str(fig2), width, height, dpi=dpi, ray=1)

        ok = fig1.is_file() and fig1.stat().st_size > 1000 and fig2.is_file()
        return {
            "ok": bool(ok),
            "engine": "pymol2",
            "fig1_png": str(fig1),
            "fig2_png": str(fig2),
            "bytes": {
                "fig1": fig1.stat().st_size if fig1.is_file() else 0,
                "fig2": fig2.stat().st_size if fig2.is_file() else 0,
            },
        }
    finally:
        try:
            p.stop()
        except Exception:
            pass


def find_pymol_exe() -> Optional[Path]:
    for name in ("pymol", "pymol.exe", "PyMOLWin.exe"):
        hit = shutil.which(name)
        if hit:
            return Path(hit)
    # 内嵌 pymol 包自带的可执行入口（若有）
    try:
        import pymol as _pm

        root = Path(_pm.__file__).resolve().parent
        for cand in root.rglob("pymol.exe"):
            if cand.is_file():
                return cand
    except Exception:
        pass
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "schrodinger",
        Path(r"C:\Program Files\PyMOL"),
        Path(r"C:\Program Files (x86)\PyMOL"),
        Path(r"C:\PyMOL"),
        Path(os.environ.get("USERPROFILE", "")) / "AppData" / "Local" / "Programs",
    ]
    for root in candidates:
        if not root or not root.exists():
            continue
        for p in root.rglob("pymol*.exe"):
            if p.is_file():
                return p
    return None


def _parse_atoms(
    path: Path, *, protein_only: bool = False, ligand_het: bool = False
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(("ATOM", "HETATM")):
            continue
        if protein_only and not line.startswith("ATOM"):
            # 仍保留金属
            res = line[17:20].strip().upper()
            if res not in {"CU", "ZN", "FE", "MG", "MN", "CA", "CO", "NI"}:
                continue
        try:
            name = line[12:16].strip()
            res = line[17:20].strip()
            chain = line[21].strip() or "A"
            resi = int(line[22:26])
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
            elem = (line[76:78].strip() if len(line) >= 78 else "") or name[:1]
            elem = elem.upper()
        except ValueError:
            continue
        if ligand_het and line.startswith("ATOM"):
            continue
        rows.append(
            {
                "name": name,
                "res": res,
                "chain": chain,
                "resi": resi,
                "x": x,
                "y": y,
                "z": z,
                "elem": elem,
                "line": line.startswith("ATOM") and "ATOM" or "HETATM",
            }
        )
    return rows


def analyze_contacts(
    receptor_pdb: Path | str,
    ligand_pdb: Path | str,
    *,
    cutoff: float = 4.0,
    hbond_cutoff: float = 3.5,
    top_n: int = 9,
) -> Dict[str, Any]:
    """口袋残基（默认 4 Å）+ 氢键候选（N/O/S，默认 ≤3.5 Å）及键长。"""
    rec = _parse_atoms(Path(receptor_pdb), protein_only=False)
    lig = _parse_atoms(Path(ligand_pdb))
    if not lig:
        return {"residues": [], "hbonds": [], "cutoff": cutoff}

    # 残基最短距离
    hit: Dict[Tuple[str, str, int], float] = {}
    for a in rec:
        if a["elem"] == "H":
            continue
        if a["line"] == "HETATM" and a["res"].upper() not in {
            "CU",
            "ZN",
            "FE",
            "MG",
            "MN",
            "CA",
            "CO",
            "NI",
        }:
            continue
        for b in lig:
            if b["elem"] == "H":
                continue
            d = math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
            if d <= cutoff:
                key = (a["chain"], a["res"], a["resi"])
                if key not in hit or d < hit[key]:
                    hit[key] = d

    residues = [
        {
            "chain": k[0],
            "res": k[1],
            "resi": k[2],
            "label": f"{k[1]}{k[2]}",
            "min_dist_A": round(v, 2),
            "sele": f"chain {k[0]} and resi {k[2]}",
        }
        for k, v in sorted(hit.items(), key=lambda kv: kv[1])
        if k[1].upper() not in {"CU", "ZN", "FE", "MG", "MN", "CA", "CO", "NI"}
    ]
    key_residues = residues[:top_n]

    # 氢键：配体极性原子 ↔ 蛋白极性原子
    hbonds: List[Dict[str, Any]] = []
    for a in rec:
        if a["elem"] not in DONOR_ACCEPTOR:
            continue
        if a["line"] == "HETATM" and a["res"].upper() not in {
            "CU",
            "ZN",
            "FE",
            "MG",
            "MN",
            "CA",
            "CO",
            "NI",
        }:
            # 跳过普通有机 HET（已清洗则很少）
            if a["res"].upper() not in {"CU", "ZN"}:
                continue
        for b in lig:
            if b["elem"] not in DONOR_ACCEPTOR:
                continue
            d = math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))
            if d <= hbond_cutoff:
                hbonds.append(
                    {
                        "res_atom": f"{a['res']}{a['resi']}.{a['name']}",
                        "lig_atom": b["name"],
                        "distance_A": round(d, 2),
                        "resi": a["resi"],
                        "res": a["res"],
                        "chain": a["chain"],
                        "pro_name": a["name"],
                        "lig_name": b["name"],
                        "pymol_pro": (
                            f"(pro and chain {a['chain']} and resi {a['resi']} "
                            f"and name {a['name']})"
                        ),
                        "pymol_lig": f"(lig and name {b['name']})",
                    }
                )
    hbonds.sort(key=lambda x: x["distance_A"])
    # 去重：每个残基原子对保留最短
    seen = set()
    uniq = []
    for h in hbonds:
        key = (h["res_atom"], h["lig_atom"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    hbonds = uniq[:20]

    return {
        "residues": residues,
        "key_residues": key_residues,
        "hbonds": hbonds,
        "cutoff": cutoff,
        "hbond_cutoff": hbond_cutoff,
    }


def write_pymol_publication_scripts(
    work_dir: Path | str,
    *,
    receptor_pdb: Path | str,
    ligand_pdbqt_or_pdb: Path | str,
    contacts: Dict[str, Any],
    box: Optional[Dict[str, Any]] = None,
    affinity: Optional[float] = None,
) -> Dict[str, Path]:
    """按高颜值作图流程写 fig1（全景）+ fig2（口袋/氢键）+ 一键出图脚本。"""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    rec = Path(receptor_pdb).resolve()
    lig = Path(ligand_pdbqt_or_pdb).resolve()
    aff = f"{affinity:.2f}" if affinity is not None else "n/a"

    # 关键残基选择（最多 9 个）
    key = contacts.get("key_residues") or contacts.get("residues") or []
    key = key[:9]
    if key:
        resi_list = "+".join(str(r["resi"]) for r in key)
        chain0 = key[0].get("chain") or "A"
        key_sele = f"(chain {chain0} and resi {resi_list})"
        # 多链时并集
        parts = []
        by_chain: Dict[str, List[int]] = {}
        for r in key:
            by_chain.setdefault(r.get("chain") or "A", []).append(int(r["resi"]))
        for ch, ids in by_chain.items():
            parts.append(f"(chain {ch} and resi {'+'.join(str(i) for i in ids)})")
        key_sele = " or ".join(parts)
    else:
        key_sele = "(byres (pro within 4 of lig))"

    # 氢键标签（距离）
    hbond_lines = []
    for i, h in enumerate((contacts.get("hbonds") or [])[:12], 1):
        hbond_lines.append(
            f"# H-bond {i}: {h['res_atom']} — {h['lig_atom']} = {h['distance_A']} Å"
        )
    hbond_comment = "\n".join(hbond_lines) if hbond_lines else "# (no polar contacts ≤3.5 Å)"

    # 公共美化设置
    beautify = """
bg_color white
set ray_shadows, 0
set ray_shadow, 0
set ray_transparency_shadows, 0
set specular, 0
set cartoon_highlight_color, grey
set ray_trace_depth_factor, 1
set ray_trace_disco_factor, 1
set ray_trace_mode, 1
set antialias, 2
set cartoon_fancy_helices, 1
set stick_radius, 0.18
set dash_width, 2.5
set dash_gap, 0.2
set dash_length, 0.15
set label_distance_digits, 2
set dash_color, green
set label_size, 18
set label_font_id, 7
set label_color, black
"""

    # 逐条氢键：显示实测键长（Å）
    hb_cmds: List[str] = []
    for i, h in enumerate((contacts.get("hbonds") or [])[:12], 1):
        pro_sel = h.get("pymol_pro") or f"(pro and resi {h.get('resi')})"
        lig_sel = h.get("pymol_lig") or "(lig)"
        hb_cmds.append(
            f"distance hb{i}, {pro_sel}, {lig_sel}, 3.6, 0\n"
            f"color green, hb{i}"
        )
    if hb_cmds:
        hb_block = (
            "\n".join(hb_cmds)
            + "\nset label_distance_digits, 2\n"
            + "show labels\n"
        )
    else:
        hb_block = (
            "distance hbonds, lig, keyres, mode=2\n"
            "color green, hbonds\n"
            "set label_distance_digits, 2\n"
            "show labels, hbonds\n"
        )

    fig1 = work / "fig1_overview.pml"
    fig1.write_text(
        f"""# ChemCrow Lab · 图1 全景（蛋白灰 + 配体黄）
# affinity = {aff} kcal/mol
# Display>Background>White · C>grays>gray80 · C>yellows>yellow · by element
reinitialize
{beautify}

load {rec.as_posix()}, pro
load {lig.as_posix()}, lig

hide everything, all
show cartoon, pro
color gray80, pro
util.cnc pro

show sticks, lig
color yellow, lig
util.cnc lig
show spheres, (pro and elem Cu+Zn)
color orange, (pro and elem Cu)
color marine, (pro and elem Zn)
set sphere_scale, 0.4, (pro and elem Cu+Zn)

orient lig
zoom lig, 25
center lig

ray 1800, 1400
png { (work / 'fig1_overview.png').resolve().as_posix() }, dpi=300
""",
        encoding="utf-8",
    )

    fig2 = work / "fig2_pocket.pml"
    fig2.write_text(
        f"""# ChemCrow Lab · 图2 口袋关键残基 + 氢键键长标注
# affinity = {aff} kcal/mol
# select keyres ≈ byres lig around 4（取最近约 9 个）
# 关键残基: {', '.join(r.get('label','') for r in key)}
{hbond_comment}

reinitialize
{beautify}

load {rec.as_posix()}, pro
load {lig.as_posix()}, lig

hide everything, all
show cartoon, pro
color gray80, pro
# S>Transparency>Cartoon>80%
set cartoon_transparency, 0.8

select pocket4, byres (pro within 4 of lig) and polymer
select keyres, {key_sele} and polymer

# 关键残基 sticks + palecyan + by element
show sticks, keyres
color palecyan, keyres
util.cnc keyres
show sticks, lig
color yellow, lig
util.cnc lig
show spheres, (pro and elem Cu+Zn)
color orange, (pro and elem Cu)
set sphere_scale, 0.35, (pro and elem Cu+Zn)

# 氢键（A>find>polar contacts）+ 键长 Å 标签
{hb_block}

# L>Residues 残基标签
label (keyres and name CA), "%s%s" % (resn, resi)

orient lig
zoom keyres, 5
center lig

ray 1800, 1400
png { (work / 'fig2_pocket.png').resolve().as_posix() }, dpi=300
""",
        encoding="utf-8",
    )

    # 交互查看（不出图，可手动 Ray）
    interactive = work / "viz_interactive.pml"
    cx = cy = cz = 0.0
    sx = sy = sz = 25.0
    if box:
        c = box.get("center") or (0, 0, 0)
        s = box.get("size") or (25, 25, 25)
        cx, cy, cz = map(float, c)
        sx, sy, sz = map(float, s)
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    corners = [
        (cx - hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz),
        (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz),
        (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz),
        (cx - hx, cy + hy, cz + hz),
    ]
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7),
    ]
    cgo = ["from pymol.cgo import *", "box = ["]
    for a, b in edges:
        x1, y1, z1 = corners[a]
        x2, y2, z2 = corners[b]
        cgo.append(
            f"  LINEWIDTH, 2.0, BEGIN, LINES, COLOR, 1.0, 0.85, 0.1, "
            f"VERTEX, {x1:.3f}, {y1:.3f}, {z1:.3f}, "
            f"VERTEX, {x2:.3f}, {y2:.3f}, {z2:.3f}, END,"
        )
    cgo.append("]")
    cgo.append('cmd.load_cgo(box, "grid_box")')

    key_names = ", ".join(r.get("label", "") for r in key) or "(none)"
    hb_summary = "; ".join(
        f"{h['res_atom']}-{h['lig_atom']}={h['distance_A']}"
        for h in (contacts.get("hbonds") or [])[:8]
    ) or "(none)"
    cgo_block = "\n".join(cgo)

    interactive.write_text(
        "\n".join(
            [
                "# ChemCrow Lab interactive view (A/S/H/L/C)",
                "# A=Action S=Show H=Hide L=Label C=Color",
                "reinitialize",
                beautify.strip(),
                f"load {rec.as_posix()}, pro",
                f"load {lig.as_posix()}, lig",
                "hide everything",
                "show cartoon, pro",
                "color gray80, pro",
                "show sticks, lig",
                "color yellow, lig",
                "util.cnc lig",
                "select pocket4, byres (pro within 4 of lig) and polymer",
                f"select keyres, {key_sele} and polymer",
                "show sticks, keyres",
                "color palecyan, keyres",
                "util.cnc keyres",
                "set cartoon_transparency, 0.8",
                hb_block.strip(),
                'label (keyres and name CA), "%s%s" % (resn, resi)',
                cgo_block,
                "orient lig",
                "zoom keyres, 6",
                f'print "key residues: {key_names}"',
                f'print "H-bonds (A): {hb_summary}"',
                "",
            ]
        ),
        encoding="utf-8",
    )

    # 无界面批量出两张 PNG
    batch = work / "render_both.pml"
    batch.write_text(
        f"""# 无界面渲染两张出版图
@{(fig1).resolve().as_posix()}
@{(fig2).resolve().as_posix()}
""",
        encoding="utf-8",
    )

    # 氢键键长表（给 PPT）
    tsv = work / "hbonds_residues.tsv"
    lines = ["type\tlabel\tdetail\tdistance_A"]
    for r in key:
        lines.append(
            f"residue\t{r['label']}\t{r.get('sele','')}\t{r['min_dist_A']}"
        )
    for h in contacts.get("hbonds") or []:
        lines.append(
            f"hbond\t{h['res_atom']}\tlig:{h['lig_atom']}\t{h['distance_A']}"
        )
    tsv.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "fig1_pml": fig1,
        "fig2_pml": fig2,
        "interactive_pml": interactive,
        "batch_pml": batch,
        "tsv": tsv,
        "fig1_png": work / "fig1_overview.png",
        "fig2_png": work / "fig2_pocket.png",
    }


def render_fallback_pngs(
    work_dir: Path | str,
    *,
    contacts: Dict[str, Any],
    affinity: Optional[float] = None,
    box: Optional[Dict[str, Any]] = None,
    title: str = "Docking",
) -> Dict[str, str]:
    """无 PyMOL 时用 matplotlib 生成可交 PPT 的分析图（残基+氢键键长）。"""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    fig1 = work / "fig1_overview.png"
    fig2 = work / "fig2_pocket.png"
    aff = f"{affinity:.2f} kcal/mol" if affinity is not None else "n/a"
    box = box or {}
    c = box.get("center") or (0, 0, 0)
    s = box.get("size") or (25, 25, 25)
    cite = box.get("cite") or box.get("paper") or ""

    # —— 图1：汇总卡 ——
    fig, ax = plt.subplots(figsize=(10, 7), dpi=200)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.add_patch(
        FancyBboxPatch(
            (0.4, 0.4), 9.2, 6.2,
            boxstyle="round,pad=0.05,rounding_size=0.2",
            facecolor="#f7f7f7",
            edgecolor="#333333",
            linewidth=1.5,
        )
    )
    ax.text(5, 6.2, "Docking Overview · Fig.1", ha="center", fontsize=16, fontweight="bold")
    ax.text(5, 5.5, title[:60], ha="center", fontsize=11, color="#444")
    ax.text(5, 4.7, f"Best affinity: {aff}", ha="center", fontsize=14, color="#1a5f2a")
    ax.text(
        5,
        3.9,
        f"Grid Box center = ({float(c[0]):.3f}, {float(c[1]):.3f}, {float(c[2]):.3f}) Å",
        ha="center",
        fontsize=11,
    )
    ax.text(
        5,
        3.3,
        f"Grid Box size = ({float(s[0]):.1f} × {float(s[1]):.1f} × {float(s[2]):.1f}) Å",
        ha="center",
        fontsize=11,
    )
    ax.text(5, 2.4, "Literature / source:", ha="center", fontsize=10, color="#666")
    ax.text(5, 1.7, (cite or "—")[:90], ha="center", fontsize=9, wrap=True)
    ax.text(
        5,
        0.8,
        "Open-source fallback figure (install PyMOL for 3D ray-traced PNG)",
        ha="center",
        fontsize=8,
        color="#888",
    )
    fig.savefig(fig1, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    # —— 图2：关键残基 + 氢键键长 ——
    key = (contacts.get("key_residues") or [])[:9]
    hbonds = (contacts.get("hbonds") or [])[:12]
    n_rows = max(len(key), len(hbonds), 1)
    fig_h = max(6.0, 1.2 + 0.45 * n_rows)
    fig, axes = plt.subplots(1, 2, figsize=(12, fig_h), dpi=200)
    fig.patch.set_facecolor("white")

    ax0 = axes[0]
    ax0.set_title("Key residues within 4 Å", fontsize=12, fontweight="bold")
    ax0.axis("off")
    if key:
        ys = list(range(len(key)))[::-1]
        dists = [r["min_dist_A"] for r in key]
        labels = [r["label"] for r in key]
        ax0.barh(ys, dists, color="#7fdbda", edgecolor="#2a9d8f")
        ax0.set_yticks(ys)
        ax0.set_yticklabels(labels, fontsize=10)
        ax0.set_xlabel("min distance (Å)")
        ax0.set_xlim(0, max(dists) * 1.25 if dists else 4)
        for y, d in zip(ys, dists):
            ax0.text(d + 0.05, y, f"{d:.2f}", va="center", fontsize=9)
    else:
        ax0.text(0.5, 0.5, "No residues ≤4 Å", ha="center", transform=ax0.transAxes)

    ax1 = axes[1]
    ax1.set_title("H-bonds / polar contacts (Å)", fontsize=12, fontweight="bold")
    ax1.axis("off")
    if hbonds:
        lines = [
            f"{h['res_atom']}  ···  {h['lig_atom']}   =  {h['distance_A']:.2f} Å"
            for h in hbonds
        ]
        ax1.text(
            0.05,
            0.95,
            "\n".join(lines),
            va="top",
            ha="left",
            family="monospace",
            fontsize=10,
            transform=ax1.transAxes,
            linespacing=1.6,
        )
    else:
        ax1.text(
            0.5,
            0.5,
            "No polar contact ≤3.5 Å",
            ha="center",
            transform=ax1.transAxes,
        )
    fig.suptitle(f"Pocket interactions · affinity {aff}", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(fig2, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    return {"fig1_png": str(fig1), "fig2_png": str(fig2)}


def render_pymol_pngs(
    batch_or_fig_pml: Path, *, exe: Optional[Path] = None, timeout: float = 180.0
) -> Dict[str, Any]:
    """渲染 PNG：优先内嵌 pymol2；否则外部 pymol.exe -cq。"""
    work = Path(batch_or_fig_pml).parent
    # 若同目录已有对接文件，用 pymol2 重渲（调用方也可直接调 render_publication_pngs_pymol2）
    if has_embedded_pymol():
        rec = work / ".."  # placeholder – 仅当有显式文件时由上层调用
        # 外部入口保留 exe 路径；内嵌渲染由 prepare / 按钮显式调用
        pass

    exe = exe or find_pymol_exe()
    if exe is None and not has_embedded_pymol():
        return {
            "ok": False,
            "error": "未找到 PyMOL（桌面版或内嵌 pymol2）",
        }
    if exe is None:
        return {"ok": False, "error": "请改用 render_publication_pngs_pymol2"}

    pml = Path(batch_or_fig_pml)
    try:
        proc = subprocess.run(
            [str(exe), "-cq", str(pml)],
            cwd=str(pml.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": proc.returncode == 0,
            "exe": str(exe),
            "code": proc.returncode,
            "log": ((proc.stdout or "") + "\n" + (proc.stderr or ""))[-2000:],
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "exe": str(exe)}


def launch_pymol(pml_path: Path, *, exe: Optional[Path] = None) -> Dict[str, Any]:
    exe = exe or find_pymol_exe()
    if exe is None:
        return {
            "ok": False,
            "error": (
                "未找到 PyMOL。安装：https://pymol.org/ 或 "
                "conda install -c conda-forge pymol-open-source\n"
                "也可下载 .pml → PyMOL → File → Run Script。"
            ),
        }
    try:
        subprocess.Popen(
            [str(exe), str(pml_path)],
            cwd=str(Path(pml_path).parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"ok": True, "exe": str(exe), "pml": str(pml_path)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "exe": str(exe)}


def prepare_dock_visualization(dock: Dict[str, Any]) -> Dict[str, Any]:
    """生成 lig.pdbqt/pdb、接触分析、出版级 PyMOL 脚本；若有 PyMOL 则尝试渲染 PNG。"""
    work = Path(dock.get("work_dir") or ".")
    out_q = Path(dock.get("out_pdbqt") or "")
    rec = Path(dock.get("receptor_used") or dock.get("receptor_pdb") or "")
    if not out_q.is_file():
        raise FileNotFoundError("缺少 out.pdbqt")
    if not rec.is_file():
        raise FileNotFoundError("缺少受体 PDB")

    lig_pdbqt = work / "lig_pose1.pdbqt"
    lig_pdb = work / "lig_pose1.pdb"
    extract_model_pdbqt(out_q, lig_pdbqt, model=1)
    extract_best_pose_pdb(out_q, lig_pdb, model=1)

    # complex
    complex_pdb = work / "complex_best.pdb"
    rec_txt = rec.read_text(encoding="utf-8", errors="replace")
    lig_txt = lig_pdb.read_text(encoding="utf-8", errors="replace")
    body = "\n".join(
        ln for ln in rec_txt.splitlines() if ln and not ln.startswith("END")
    )
    body += "\n" + "\n".join(
        ln for ln in lig_txt.splitlines() if ln.startswith(("ATOM", "HETATM"))
    )
    body += "\nEND\n"
    complex_pdb.write_text(body, encoding="utf-8")

    contacts = analyze_contacts(rec, lig_pdb, cutoff=4.0, hbond_cutoff=3.5, top_n=9)
    scripts = write_pymol_publication_scripts(
        work,
        receptor_pdb=rec,
        ligand_pdbqt_or_pdb=lig_pdbqt,
        contacts=contacts,
        box=dock.get("box") or {},
        affinity=dock.get("best_affinity"),
    )

    pml = scripts["interactive_pml"]
    rendered: Dict[str, Any] = {"ok": False}
    exe = find_pymol_exe()
    fig1_p = Path(scripts["fig1_png"])
    fig2_p = Path(scripts["fig2_png"])

    # 已有合格 PNG → 直接缓存；默认不在页面刷新时重渲（太慢）
    # 真正出图：对接结束后的 spinner /「渲染出 PNG」按钮
    already = (
        fig1_p.is_file()
        and fig2_p.is_file()
        and fig1_p.stat().st_size > 8000
        and fig2_p.stat().st_size > 8000
    )
    if already:
        rendered = {
            "ok": True,
            "engine": "cached",
            "fig1_png": str(fig1_p),
            "fig2_png": str(fig2_p),
            "bytes": {
                "fig1": fig1_p.stat().st_size,
                "fig2": fig2_p.stat().st_size,
            },
        }

    return {
        "ok": True,
        "ligand_pdb": str(lig_pdb),
        "ligand_pdbqt": str(lig_pdbqt),
        "complex_pdb": str(complex_pdb),
        "pml": str(pml),
        "fig1_pml": str(scripts["fig1_pml"]),
        "fig2_pml": str(scripts["fig2_pml"]),
        "batch_pml": str(scripts["batch_pml"]),
        "tsv": str(scripts["tsv"]),
        "fig1_png": str(scripts["fig1_png"]),
        "fig2_png": str(scripts["fig2_png"]),
        "contacts": contacts,
        "pymol_exe": str(exe or ""),
        "pymol_embedded": has_embedded_pymol(),
        "render": rendered,
    }
