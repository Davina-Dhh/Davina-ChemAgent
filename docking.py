"""便携 AutoDock Vina 对接：自动下载二进制 + Meeko 准备 + 出结合能/pose。"""

from __future__ import annotations

import os
import re
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
VINA_DIR = ROOT / "tools" / "vina"
OUT_DIR = ROOT / "outputs" / "docking"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 平台相关二进制（Windows / Linux Streamlit Cloud）
import platform as _platform

_IS_WIN = _platform.system().lower().startswith("win")
if _IS_WIN:
    VINA_EXE = VINA_DIR / "vina.exe"
    VINA_URL = (
        "https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/"
        "v1.2.5/vina_1.2.5_win.exe"
    )
else:
    VINA_EXE = VINA_DIR / "vina"
    VINA_URL = (
        "https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/"
        "v1.2.5/vina_1.2.5_linux_x86_64"
    )

# 常用靶点默认对接盒子（中心 Å）；未命中则用蛋白几何中心 / 共晶配体 / 金属
# cite: 文献或晶体依据说明（展示给用户）
PRESET_BOXES: Dict[str, Dict[str, Any]] = {
    "6LU7": {
        "center": (-10.235, 17.563, 67.358),
        "size": (22.0, 22.0, 22.0),
        "cite": "SARS-CoV-2 Mpro (6LU7) 共晶配体 N3 几何中心附近（Jin et al. Nature 2020）",
    },
    "1HPV": {
        "center": (2.0, 0.5, 5.0),
        "size": (22.0, 22.0, 22.0),
        "cite": "HIV 蛋白酶常见对接口袋粗中心",
    },
    # TYRP1 · tropolone 共晶；链 A 双锌中点（Lai et al. Angew. Chem. 2017, PDB 5M8O）
    "5M8O": {
        "center": (-11.020, 0.347, -23.444),
        "size": (22.0, 22.0, 22.0),
        "cite": (
            "人源 TYRP1 PDB 5M8O chain A：ZnA(513)+ZnB(514) 中点 "
            "(-11.02, 0.35, -23.44)；Lai et al. Angew. Chem. Int. Ed. 2017"
        ),
    },
    "5M8M": {
        "center": (-11.0, 0.3, -23.4),
        "size": (22.0, 22.0, 22.0),
        "cite": "TYRP1·曲酸共晶 5M8M，活性位点同 5M8O 双锌口袋（同源）",
    },
}

# 文献/工作流推荐的盒子策略（可在 UI 选择；与 dock_viz.LITERATURE_BOXES 对齐）
BOX_STRATEGIES: Dict[str, Dict[str, Any]] = {
    "auto": {
        "label": "自动推断 · 推荐 22 Å",
        "size": 22.0,
        "cite": "Trott & Olson, J. Comput. Chem. 2010 (AutoDock Vina)",
        "paper": "AutoDock Vina: improving the speed and accuracy of docking with a new scoring function, efficient optimization, and multithreading",
    },
    "tyr_cu_mid": {
        "label": "人源 TYR 双铜中点 · 推荐 25 Å ★",
        "size": 25.0,
        "cite": "Vecura humanized TYR docking (gnina) · His sites UniProt P14679",
        "paper": (
            "Vecura Biotech Insiders #03: Building a Humanized Tyrosinase Model "
            "for Structure-Based Docking"
        ),
    },
    "tyrp1_zn_5m8o": {
        "label": "TYRP1 5M8O 双锌中点 · 推荐 22 Å ★",
        "center": (-11.020, 0.347, -23.444),
        "size": 22.0,
        "cite": "Lai et al., Angew. Chem. Int. Ed. 2017, 56, 9812",
        "paper": (
            "Structure of Human Tyrosinase Related Protein 1 Reveals a "
            "Binuclear Zinc Active Site Important for Melanogenesis"
        ),
    },
    "mpro_6lu7": {
        "label": "SARS-CoV-2 Mpro 6LU7 · 推荐 22 Å",
        "center": (-10.235, 17.563, 67.358),
        "size": 22.0,
        "cite": "Jin et al., Nature 2020, 582, 289",
        "paper": "Structure of Mpro from SARS-CoV-2 and discovery of its inhibitors",
    },
    "manual": {
        "label": "手动精确坐标 (Å)",
        "cite": "用户指定；请旁注文献名",
        "paper": "—",
    },
}

# 人源酪氨酸酶 (UniProt P14679) 双铜中心配位 His（文献/UniProt 编号）
TYR_CU_A_HIS = (180, 202, 211)
TYR_CU_B_HIS = (363, 367, 390)
METAL_RES = {"CU", "CU1", "CU2", "ZN", "FE", "MG", "MN", "CA", "CO", "NI"}


def ensure_vina(timeout: float = 120.0) -> Path:
    """确保便携 vina 存在；没有则从 GitHub Release 下载（Win/Linux）。"""
    VINA_DIR.mkdir(parents=True, exist_ok=True)
    if VINA_EXE.is_file() and VINA_EXE.stat().st_size > 100_000:
        return VINA_EXE
    tmp = VINA_DIR / (VINA_EXE.name + ".part")
    try:
        req = urllib.request.Request(
            VINA_URL, headers={"User-Agent": "chemagent-lab/1.0"}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp, "wb") as f:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
        tmp.replace(VINA_EXE)
        if not _IS_WIN:
            try:
                os.chmod(VINA_EXE, 0o755)
            except Exception:
                pass
    except Exception as exc:  # noqa: BLE001
        if tmp.is_file():
            tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"下载便携 Vina 失败：{exc}\n"
            f"请手动下载 {VINA_URL} 保存为 {VINA_EXE}"
        ) from exc
    if not VINA_EXE.is_file():
        raise RuntimeError("Vina 下载后文件不存在")
    return VINA_EXE


def vina_version() -> str:
    exe = ensure_vina()
    try:
        p = subprocess.run(
            [str(exe), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return (p.stdout or p.stderr or "").strip().splitlines()[0]
    except Exception as exc:  # noqa: BLE001
        return f"(无法读版本: {exc})"


def _clean_receptor_pdb(
    pdb_path: Path,
    *,
    keep_metals: bool = True,
) -> Tuple[
    str,
    List[Tuple[float, float, float]],
    List[Tuple[float, float, float]],
    List[Tuple[float, float, float]],
]:
    """去掉水与普通 HETATM；可选保留金属。

    返回: cleaned PDB 文本、蛋白 CA、共晶有机配体坐标、金属坐标。
    """
    protein_ca: List[Tuple[float, float, float]] = []
    het_coords: List[Tuple[float, float, float]] = []
    metal_coords: List[Tuple[float, float, float]] = []
    lines: List[str] = []
    text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if line.startswith("ATOM"):
            res = line[17:20].strip()
            if res in ("HOH", "WAT", "DOD"):
                continue
            lines.append(line)
            if len(line) >= 54 and line[12:16].strip() == "CA":
                try:
                    protein_ca.append(
                        (float(line[30:38]), float(line[38:46]), float(line[46:54]))
                    )
                except ValueError:
                    pass
        elif line.startswith("HETATM"):
            res = line[17:20].strip().upper()
            elem = (line[76:78].strip() if len(line) >= 78 else "").upper()
            atom = line[12:16].strip().upper()
            is_metal = (
                res in METAL_RES
                or elem in ("CU", "ZN", "FE", "MG", "MN", "CA", "CO", "NI")
                or atom in ("CU", "ZN", "FE")
            )
            if res in ("HOH", "WAT", "DOD"):
                continue
            if is_metal:
                if keep_metals:
                    lines.append(line)
                    if len(line) >= 54:
                        try:
                            metal_coords.append(
                                (
                                    float(line[30:38]),
                                    float(line[38:46]),
                                    float(line[46:54]),
                                )
                            )
                        except ValueError:
                            pass
                continue
            # 其它 HETATM（共晶配体）坐标只用于推断盒子，不写入受体
            if len(line) >= 54:
                try:
                    het_coords.append(
                        (float(line[30:38]), float(line[38:46]), float(line[46:54]))
                    )
                except ValueError:
                    pass
        elif line.startswith(("END", "TER", "MASTER", "CONECT")):
            continue
    lines.append("END")
    return "\n".join(lines) + "\n", protein_ca, het_coords, metal_coords


def _centroid(coords: List[Tuple[float, float, float]]) -> Tuple[float, float, float]:
    n = max(1, len(coords))
    return (
        sum(c[0] for c in coords) / n,
        sum(c[1] for c in coords) / n,
        sum(c[2] for c in coords) / n,
    )


def _his_sidechain_n_coords(
    pdb_path: Path, resi_list: Tuple[int, ...]
) -> List[Tuple[float, float, float]]:
    """取指定 His 残基的 ND1/NE2 坐标（用于放置 Cu）。"""
    coords: List[Tuple[float, float, float]] = []
    want = set(resi_list)
    text = Path(pdb_path).read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        if not line.startswith("ATOM"):
            continue
        if line[17:20].strip() != "HIS":
            continue
        try:
            resi = int(line[22:26])
        except ValueError:
            continue
        if resi not in want:
            continue
        atom = line[12:16].strip()
        if atom not in ("ND1", "NE2"):
            continue
        try:
            coords.append(
                (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            )
        except ValueError:
            pass
    return coords


def _pdb_hetatm_cu(serial: int, resi: int, xyz: Tuple[float, float, float]) -> str:
    x, y, z = xyz
    # PDB HETATM；元素 CU
    return (
        f"HETATM{serial:5d}  CU  CU  A{resi:4d}    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00          CU\n"
    )


def add_tyrosinase_coppers(
    pdb_path: Path | str,
    *,
    out_path: Optional[Path] = None,
    cu_a_his: Tuple[int, ...] = TYR_CU_A_HIS,
    cu_b_his: Tuple[int, ...] = TYR_CU_B_HIS,
) -> Dict[str, Any]:
    """在人源 TYR 双铜位点放置 2 个 Cu（AlphaFold 无金属时必需）。

    CuA ← His180/202/211；CuB ← His363/367/390（P14679 编号）。
    """
    pdb_path = Path(pdb_path)
    n_a = _his_sidechain_n_coords(pdb_path, cu_a_his)
    n_b = _his_sidechain_n_coords(pdb_path, cu_b_his)
    if len(n_a) < 3:
        raise RuntimeError(
            f"CuA 位点 His{cu_a_his} 侧链 N 不足（找到 {len(n_a)}）；"
            "确认是人源 TYR / P14679 编号结构"
        )
    if len(n_b) < 3:
        raise RuntimeError(
            f"CuB 位点 His{cu_b_his} 侧链 N 不足（找到 {len(n_b)}）"
        )
    cu_a = _centroid(n_a)
    cu_b = _centroid(n_b)

    # 去掉旧水与旧铜，保留蛋白
    clean, _ca, _het, _met = _clean_receptor_pdb(pdb_path, keep_metals=False)
    body = "\n".join(
        ln for ln in clean.splitlines() if ln and not ln.startswith("END")
    )
    body += "\n"
    body += _pdb_hetatm_cu(9901, 901, cu_a)
    body += _pdb_hetatm_cu(9902, 902, cu_b)
    body += "END\n"

    if out_path is None:
        out_path = (
            pdb_path.parent / f"{pdb_path.stem}_Cu2{pdb_path.suffix or '.pdb'}"
        )
    out_path = Path(out_path)
    out_path.write_text(body, encoding="utf-8")
    mid = _centroid([cu_a, cu_b])
    return {
        "ok": True,
        "path": str(out_path),
        "cu_a": cu_a,
        "cu_b": cu_b,
        "box_center": mid,
        "cu_a_his": cu_a_his,
        "cu_b_his": cu_b_his,
        "note": "已按 His 三联体几何中心放置双铜；Vina 中 Cu 用 Zn 原子类型近似",
    }


def infer_box(
    pdb_path: Path,
    *,
    size: float = 22.0,
    preset_key: str = "",
) -> Dict[str, Any]:
    """推断对接盒子：预设 > 金属中心 > 共晶配体 > 蛋白 CA 几何中心。"""
    pid = Path(pdb_path).stem.upper()
    key = (preset_key or "").upper()
    if key in PRESET_BOXES:
        box = PRESET_BOXES[key]
        return {
            "center": box["center"],
            "size": box["size"],
            "source": f"preset:{preset_key}",
            "cite": box.get("cite") or "",
        }
    # AF-P14679-F1_Cu2 等
    for k, box in PRESET_BOXES.items():
        if k in pid:
            return {
                "center": box["center"],
                "size": box["size"],
                "source": f"preset:{k}",
                "cite": box.get("cite") or "",
            }

    _clean, ca, het, metals = _clean_receptor_pdb(pdb_path, keep_metals=True)
    if metals:
        c = _centroid(metals)
        return {
            "center": c,
            "size": (size, size, size),
            "source": "metal-center",
            "cite": "受体金属离子几何中心",
        }
    if het:
        c = _centroid(het)
        return {
            "center": c,
            "size": (size, size, size),
            "source": "co-crystal-ligand",
            "cite": "共晶有机配体几何中心",
        }
    if ca:
        c = _centroid(ca)
        return {
            "center": c,
            "size": (size, size, size),
            "source": "protein-CA-centroid",
            "cite": "蛋白 CA 几何中心（粗筛，建议改用金属/文献盒子）",
        }
    return {
        "center": (0.0, 0.0, 0.0),
        "size": (size, size, size),
        "source": "origin-fallback",
        "cite": "无法推断，落在原点",
    }


def prepare_ligand_pdbqt(smiles: str, out_pdbqt: Path) -> Dict[str, Any]:
    """SMILES → 加氢 → 多构象 ETKDG → MMFF 选优 → Meeko → PDBQT。

    返回 {"path", "n_confs", "energy", "atoms", "note"}。
    """
    from meeko import MoleculePreparation, PDBQTWriterLegacy
    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles((smiles or "").strip())
    if mol is None:
        raise ValueError(f"无效 SMILES：{smiles!r}")
    mol = Chem.AddHs(mol)
    params = AllChem.ETKDGv3()
    params.randomSeed = 0xC0FFEE
    params.numThreads = 0
    n_try = 20
    cids = AllChem.EmbedMultipleConfs(mol, numConfs=n_try, params=params)
    if not cids:
        # 回退单构象
        if AllChem.EmbedMolecule(mol, params) != 0:
            if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
                raise RuntimeError("配体 3D 构象生成失败")
        cids = [0]

    energies: List[Tuple[int, float]] = []
    for cid in cids:
        try:
            AllChem.MMFFOptimizeMolecule(mol, confId=int(cid), maxIters=400)
            props = AllChem.MMFFGetMoleculeProperties(mol)
            if props is None:
                AllChem.UFFOptimizeMolecule(mol, confId=int(cid), maxIters=400)
                energies.append((int(cid), 0.0))
            else:
                ff = AllChem.MMFFGetMoleculeForceField(mol, props, confId=int(cid))
                e = ff.CalcEnergy() if ff else 0.0
                energies.append((int(cid), float(e)))
        except Exception:
            try:
                AllChem.UFFOptimizeMolecule(mol, confId=int(cid), maxIters=400)
            except Exception:
                pass
            energies.append((int(cid), 9999.0))

    energies.sort(key=lambda x: x[1])
    best_cid, best_e = energies[0]
    # 只保留最优构象供 Meeko
    new = Chem.Mol(mol)
    new.RemoveAllConformers()
    conf = mol.GetConformer(best_cid)
    new.AddConformer(conf, assignId=True)

    prep = MoleculePreparation()
    setups = prep.prepare(new)
    if not setups:
        raise RuntimeError("Meeko 未能准备配体")
    pdbqt, ok, err = PDBQTWriterLegacy.write_string(setups[0])
    if not ok or not pdbqt:
        raise RuntimeError(f"写配体 PDBQT 失败：{err}")
    out_pdbqt.parent.mkdir(parents=True, exist_ok=True)
    out_pdbqt.write_text(pdbqt, encoding="utf-8")
    return {
        "path": str(out_pdbqt),
        "n_confs": len(list(cids)),
        "energy": round(best_e, 3),
        "atoms": new.GetNumAtoms(),
        "note": (
            f"加氢 → ETKDG×{len(list(cids))} → MMFF 选优 "
            f"(E≈{best_e:.1f}) → Meeko Gasteiger/可旋转键"
        ),
    }


def _append_metals_to_pdbqt(
    pdbqt_text: str,
    metal_xyz: List[Tuple[float, float, float]],
    *,
    ad_type: str = "Zn",
) -> str:
    """Meeko 常丢掉金属；把 Cu 以 Zn 原子类型追加进 PDBQT（Vina 原生支持 Zn）。"""
    lines = [ln for ln in (pdbqt_text or "").splitlines() if ln.strip() and not ln.startswith("END")]
    serial = 9000
    for i, (x, y, z) in enumerate(metal_xyz):
        serial += 1
        # PDBQT: atom name, resname, chain, resi, xyz, charge, type
        lines.append(
            f"HETATM{serial:5d}  CU  CU  A{901+i:4d}    "
            f"{x:8.3f}{y:8.3f}{z:8.3f}  0.00  0.00    +2.000 {ad_type}"
        )
    lines.append("END")
    return "\n".join(lines) + "\n"


def prepare_receptor_pdbqt(
    pdb_path: Path,
    out_pdbqt: Path,
    *,
    keep_metals: bool = True,
) -> Dict[str, Any]:
    """PDB → 去水/去有机配体（保留金属）→ Meeko → 再补回金属 PDBQT。"""
    from meeko import PDBQTWriterLegacy, Polymer

    clean, _ca, het, metals = _clean_receptor_pdb(
        Path(pdb_path), keep_metals=keep_metals
    )
    # Meeko 对金属支持差：先不带金属做 polymer，再手工追加
    clean_no_metal, ca, _, _ = _clean_receptor_pdb(Path(pdb_path), keep_metals=False)
    n_atom_lines = sum(
        1 for ln in clean_no_metal.splitlines() if ln.startswith("ATOM")
    )
    if n_atom_lines < 10:
        raise RuntimeError("受体 PDB 有效 ATOM 过少，无法对接")
    try:
        polymer = Polymer.from_pdb_string(clean_no_metal, allow_bad_res=True)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Meeko 准备受体失败：{exc}") from exc
    written = PDBQTWriterLegacy.write_string_from_polymer(polymer)
    pdbqt = written[0] if isinstance(written, tuple) else written
    _, _, _, metals2 = _clean_receptor_pdb(Path(pdb_path), keep_metals=True)
    use_metals = metals2 if metals2 else metals
    if keep_metals and use_metals:
        pdbqt = _append_metals_to_pdbqt(pdbqt, use_metals, ad_type="Zn")
    out_pdbqt.parent.mkdir(parents=True, exist_ok=True)
    out_pdbqt.write_text(pdbqt, encoding="utf-8")
    return {
        "path": str(out_pdbqt),
        "n_ca": len(ca),
        "n_atom": n_atom_lines,
        "n_metals": len(use_metals) if keep_metals else 0,
        "n_het_ignored": len(het),
        "note": (
            "去水/去共晶有机配体 → Meeko（补极性 H、Gasteiger）→ "
            f"保留/回写金属 {len(use_metals) if keep_metals else 0} 个"
            "（Cu 以 Zn AD 类型近似）"
        ),
    }


def resolve_docking_box(
    receptor_pdb: Path,
    *,
    strategy: str = "auto",
    box_size: float = 22.0,
    box_center: Optional[Tuple[float, float, float]] = None,
    box_size_xyz: Optional[Tuple[float, float, float]] = None,
    metal_info: Optional[Dict[str, Any]] = None,
    add_tyr_coppers: bool = False,
) -> Dict[str, Any]:
    """按策略解析对接盒子，附带文献/来源说明。"""
    strategy = (strategy or "auto").strip()
    size_t = box_size_xyz or (box_size, box_size, box_size)

    if strategy == "manual":
        if box_center is None:
            raise ValueError("手动盒子需要提供 center_x/y/z")
        return {
            "center": tuple(float(x) for x in box_center),
            "size": tuple(float(x) for x in size_t),
            "source": "manual",
            "cite": BOX_STRATEGIES["manual"]["cite"],
            "strategy": strategy,
        }

    if strategy == "tyrp1_zn_5m8o":
        meta = BOX_STRATEGIES["tyrp1_zn_5m8o"]
        s = float(box_size if box_size else meta.get("size") or 22.0)
        return {
            "center": tuple(meta["center"]),
            "size": (s, s, s) if not box_size_xyz else tuple(float(x) for x in box_size_xyz),
            "source": "lit:5M8O-Zn-mid",
            "cite": meta["cite"],
            "paper": meta.get("paper") or "",
            "strategy": strategy,
        }

    if strategy == "mpro_6lu7":
        meta = BOX_STRATEGIES["mpro_6lu7"]
        s = float(box_size if box_size else meta.get("size") or 22.0)
        return {
            "center": tuple(meta["center"]),
            "size": (s, s, s) if not box_size_xyz else tuple(float(x) for x in box_size_xyz),
            "source": "lit:6LU7-N3-pocket",
            "cite": meta["cite"],
            "paper": meta.get("paper") or "",
            "strategy": strategy,
        }

    if strategy == "tyr_cu_mid" or (add_tyr_coppers and strategy == "auto"):
        mi = metal_info or {}
        mid = mi.get("box_center")
        if mid is None and mi.get("cu_a") and mi.get("cu_b"):
            mid = _centroid([tuple(mi["cu_a"]), tuple(mi["cu_b"])])
        if mid is not None:
            s = float(BOX_STRATEGIES["tyr_cu_mid"].get("size") or 25.0)
            if box_size_xyz:
                size_out = tuple(float(x) for x in box_size_xyz)
            elif box_size:
                size_out = (box_size, box_size, box_size)
            else:
                size_out = (s, s, s)
            return {
                "center": tuple(float(x) for x in mid),
                "size": size_out,
                "source": "lit:TYR-Cu-mid",
                "cite": BOX_STRATEGIES["tyr_cu_mid"]["cite"],
                "paper": BOX_STRATEGIES["tyr_cu_mid"].get("paper") or "",
                "strategy": "tyr_cu_mid",
            }

    # auto / fallback
    box = infer_box(Path(receptor_pdb), size=float(size_t[0]))
    if box_size_xyz:
        box["size"] = tuple(float(x) for x in box_size_xyz)
    cite = ""
    src = str(box.get("source") or "")
    for k, preset in PRESET_BOXES.items():
        if k in src.upper() or k in Path(receptor_pdb).stem.upper():
            cite = str(preset.get("cite") or "")
            break
    if not cite:
        if "metal" in src:
            cite = "受体文件中的金属离子几何中心（晶体或已补金属）"
        elif "ligand" in src or "het" in src:
            cite = "共晶有机配体原子几何中心"
        else:
            cite = BOX_STRATEGIES["auto"]["cite"]
    box["cite"] = cite
    box["strategy"] = strategy
    return box


def _parse_vina_stdout(text: str) -> List[Dict[str, Any]]:
    """解析 Vina 文本表：mode | affinity | rmsd lb | rmsd ub"""
    poses: List[Dict[str, Any]] = []
    in_table = False
    for line in (text or "").splitlines():
        if "-----+------------" in line or "mode |   affinity" in line:
            in_table = True
            continue
        if not in_table:
            continue
        line = line.strip()
        if not line or line.startswith("Writing") or line.startswith("Scoring"):
            if poses and (line.startswith("Writing") or not line):
                break
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            try:
                poses.append(
                    {
                        "mode": int(parts[0]),
                        "affinity": float(parts[1]),
                        "rmsd_lb": float(parts[2]) if len(parts) > 2 else None,
                        "rmsd_ub": float(parts[3]) if len(parts) > 3 else None,
                    }
                )
            except ValueError:
                continue
    return poses


def run_docking(
    receptor_pdb: str | Path,
    ligand_smiles: str,
    *,
    exhaustiveness: int = 8,
    num_modes: int = 9,
    box_size: float = 22.0,
    box_center: Optional[Tuple[float, float, float]] = None,
    box_size_xyz: Optional[Tuple[float, float, float]] = None,
    box_strategy: str = "auto",
    job_name: str = "",
    cpu: int = 0,
    add_tyr_coppers: bool = False,
) -> Dict[str, Any]:
    """完整对接流程。返回分数、路径、盒子与前处理信息。

    add_tyr_coppers=True：按人源 TYR 双铜 His 位点补 Cu（AlphaFold 缺金属时用）。
    box_strategy: auto | tyr_cu_mid | tyrp1_zn_5m8o | manual
    """
    t0 = time.time()
    receptor_pdb = Path(receptor_pdb)
    if not receptor_pdb.is_file():
        raise FileNotFoundError(f"受体文件不存在：{receptor_pdb}")

    smi = (ligand_smiles or "").strip()
    if not smi:
        raise ValueError("配体 SMILES 为空")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    tag = re.sub(r"[^A-Za-z0-9_-]+", "_", job_name or receptor_pdb.stem)[:40]
    work = OUT_DIR / f"{tag}_{stamp}"
    work.mkdir(parents=True, exist_ok=True)

    metal_info: Dict[str, Any] = {}
    rec_use = receptor_pdb
    if add_tyr_coppers:
        metal_info = add_tyrosinase_coppers(
            receptor_pdb, out_path=work / f"{receptor_pdb.stem}_Cu2.pdb"
        )
        rec_use = Path(metal_info["path"])
        if box_strategy in ("auto", "tyr_cu_mid") and box_center is None:
            box_strategy = "tyr_cu_mid"

    vina = ensure_vina()
    rec_q = work / "receptor.pdbqt"
    lig_q = work / "ligand.pdbqt"
    out_q = work / "out.pdbqt"
    log_f = work / "vina.log"
    cfg_f = work / "config.txt"

    rec_prep = prepare_receptor_pdbqt(rec_use, rec_q, keep_metals=True)
    lig_prep = prepare_ligand_pdbqt(smi, lig_q)

    box = resolve_docking_box(
        rec_use,
        strategy=box_strategy,
        box_size=box_size,
        box_center=box_center,
        box_size_xyz=box_size_xyz,
        metal_info=metal_info,
        add_tyr_coppers=add_tyr_coppers,
    )

    cx, cy, cz = box["center"]
    sx, sy, sz = box["size"]
    cfg = (
        f"receptor = {rec_q.name}\n"
        f"ligand = {lig_q.name}\n"
        f"center_x = {cx:.3f}\n"
        f"center_y = {cy:.3f}\n"
        f"center_z = {cz:.3f}\n"
        f"size_x = {sx:.3f}\n"
        f"size_y = {sy:.3f}\n"
        f"size_z = {sz:.3f}\n"
        f"exhaustiveness = {int(exhaustiveness)}\n"
        f"num_modes = {int(num_modes)}\n"
        f"energy_range = 3\n"
    )
    if cpu and int(cpu) > 0:
        cfg += f"cpu = {int(cpu)}\n"
    cfg_f.write_text(cfg, encoding="utf-8")

    cmd = [
        str(vina),
        "--config",
        str(cfg_f.name),
        "--out",
        str(out_q.name),
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(work),
        capture_output=True,
        text=True,
        timeout=60 * 30,
        check=False,
    )
    stdout = (proc.stdout or "") + "\n" + (proc.stderr or "")
    log_f.write_text(stdout, encoding="utf-8")
    if proc.returncode != 0 and not out_q.is_file():
        raise RuntimeError(
            f"Vina 运行失败 (code={proc.returncode})：\n{stdout[-1500:]}"
        )

    poses = _parse_vina_stdout(stdout)
    # 也从 out.pdbqt REMARK VINA RESULT 解析
    if out_q.is_file():
        for m in re.finditer(
            r"REMARK VINA RESULT:\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)",
            out_q.read_text(encoding="utf-8", errors="replace"),
        ):
            aff = float(m.group(1))
            if not any(abs(p["affinity"] - aff) < 1e-6 for p in poses):
                poses.append(
                    {
                        "mode": len(poses) + 1,
                        "affinity": aff,
                        "rmsd_lb": float(m.group(2)),
                        "rmsd_ub": float(m.group(3)),
                    }
                )

    poses.sort(key=lambda p: p["affinity"])
    for i, p in enumerate(poses, 1):
        p["mode"] = i

    best = poses[0]["affinity"] if poses else None
    (work / "ligand.smi").write_text(smi + "\n", encoding="utf-8")
    (work / "summary.txt").write_text(
        f"receptor={receptor_pdb}\nligand={smi}\nbest={best}\n"
        f"box={box}\nrec_prep={rec_prep}\nlig_prep={lig_prep}\n"
        f"elapsed={time.time()-t0:.1f}s\n",
        encoding="utf-8",
    )

    return {
        "ok": True,
        "best_affinity": best,
        "poses": poses,
        "box": box,
        "prep": {"receptor": rec_prep, "ligand": lig_prep},
        "work_dir": str(work),
        "receptor_pdbqt": str(rec_q),
        "ligand_pdbqt": str(lig_q),
        "out_pdbqt": str(out_q) if out_q.is_file() else "",
        "log": str(log_f),
        "vina": vina_version(),
        "elapsed_s": round(time.time() - t0, 1),
        "ligand_smiles": smi,
        "receptor_pdb": str(receptor_pdb),
        "receptor_used": str(rec_use),
        "metal_info": metal_info,
        "add_tyr_coppers": bool(add_tyr_coppers),
        "box_strategy": box.get("strategy") or box_strategy,
    }
