"""分子名（中文俗名 / 系统名 / 英文 / SMILES）→ 规范化 SMILES。

解析优先级:
1. 直接 SMILES
2. 本地词典 + 别名/俗名（含用户缓存）
3. 中文规则展开为英文候选名
4. NIH CIR
5. PubChem
6. Agnes（提高 max_tokens，防止 reasoning 截断）
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import requests
from rdkit import Chem

ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "data" / "name_cache.json"

# ---------- 本地俗名 / 别名词典 ----------
COMMON_NAME_TO_SMILES: Dict[str, str] = {
    # 溶剂 / 简单
    "水": "O",
    "乙醇": "CCO",
    "无水乙醇": "CCO",
    "甲醇": "CO",
    "丙酮": "CC(=O)C",
    "乙酸": "CC(=O)O",
    "醋酸": "CC(=O)O",
    "冰醋酸": "CC(=O)O",
    "乙醛": "CC=O",
    "甲醛": "C=O",
    "乙腈": "CC#N",
    "二氯甲烷": "CClCl",
    "DCM": "CClCl",
    "氯仿": "C(Cl)(Cl)Cl",
    "四氢呋喃": "C1CCOC1",
    "THF": "C1CCOC1",
    "DMF": "CN(C)C=O",
    "DMSO": "CS(C)=O",
    "三乙胺": "CCN(CC)CC",
    "TEA": "CCN(CC)CC",
    "DIPEA": "CCN(C(C)C)C(C)C",
    "二异丙基乙胺": "CCN(C(C)C)C(C)C",
    "DMAP": "CN(C)c1ccncc1",
    "4-二甲氨基吡啶": "CN(C)c1ccncc1",
    "对二甲氨基吡啶": "CN(C)c1ccncc1",
    "EDCI": "CCN=C=NCCCN(C)C",
    "EDC": "CCN=C=NCCCN(C)C",
    "HOAt": "Oc1nnn2ccccc12",
    "HOBt": "Oc1nnnc2ccccc12",
    "HATU": "CN(C)C(=[N+](C)C)On1nnc2ccccc21.F[P-](F)(F)(F)(F)F",
    "HBTU": "CN(C)C(=[N+](C)C)On1nnc2ccccc21.F[P-](F)(F)(F)(F)F",
    # 芳环基础
    "苯": "c1ccccc1",
    "甲苯": "Cc1ccccc1",
    "苯酚": "Oc1ccccc1",
    "苯胺": "Nc1ccccc1",
    "吡啶": "c1ccncc1",
    "噻吩": "c1ccsc1",
    "呋喃": "c1ccoc1",
    "咪唑": "c1c[nH]cn1",
    # 卤代 / 偶联
    "溴苯": "c1ccccc1Br",
    "氯苯": "c1ccccc1Cl",
    "碘苯": "c1ccccc1I",
    "氟苯": "c1ccccc1F",
    "苯硼酸": "B(O)(O)c1ccccc1",
    "苯基硼酸": "B(O)(O)c1ccccc1",
    "苯乙炔": "C#Cc1ccccc1",
    "苯乙烯": "C=Cc1ccccc1",
    "硝基苯": "O=[N+]([O-])c1ccccc1",
    "苯甲醇": "OCc1ccccc1",
    "苯甲醛": "O=Cc1ccccc1",
    "苯甲酸": "O=C(O)c1ccccc1",
    "苯甲酰氯": "O=C(Cl)c1ccccc1",
    "联苯": "c1ccc(-c2ccccc2)cc1",
    # 醛基苯甲酸类（俗名）
    "对醛基苯甲酸": "O=Cc1ccc(C(=O)O)cc1",
    "对甲酰基苯甲酸": "O=Cc1ccc(C(=O)O)cc1",
    "4-醛基苯甲酸": "O=Cc1ccc(C(=O)O)cc1",
    "4-甲酰基苯甲酸": "O=Cc1ccc(C(=O)O)cc1",
    "对羧基苯甲醛": "O=Cc1ccc(C(=O)O)cc1",
    "邻醛基苯甲酸": "O=Cc1ccccc1C(=O)O",
    "邻甲酰基苯甲酸": "O=Cc1ccccc1C(=O)O",
    "间醛基苯甲酸": "O=Cc1cccc(C(=O)O)c1",
    "间甲酰基苯甲酸": "O=Cc1cccc(C(=O)O)c1",
    # 氨基乙酸甲酯 / 甘氨酸酯
    "盐酸氨基乙酸甲酯": "Cl.COC(=O)CN",
    "氨基乙酸甲酯盐酸盐": "Cl.COC(=O)CN",
    "甘氨酸甲酯盐酸盐": "Cl.COC(=O)CN",
    "甘氨酸甲酯": "COC(=O)CN",
    "氨基乙酸甲酯": "COC(=O)CN",
    "盐酸甘氨酸甲酯": "Cl.COC(=O)CN",
    "氨基乙酸": "NCC(=O)O",
    "甘氨酸": "NCC(=O)O",
    # 其他常见
    "对氨基苯甲酸": "Nc1ccc(C(=O)O)cc1",
    "对硝基苯甲酸": "O=[N+]([O-])c1ccc(C(=O)O)cc1",
    "对羟基苯甲酸": "Oc1ccc(C(=O)O)cc1",
    "对甲苯磺酰氯": "Cc1ccc(S(=O)(=O)Cl)cc1",
    "TsCl": "Cc1ccc(S(=O)(=O)Cl)cc1",
    "Boc酸酐": "CC(C)(C)OC(=O)OC(=O)OC(C)(C)C",
    "二碳酸二叔丁酯": "CC(C)(C)OC(=O)OC(=O)OC(C)(C)C",
    "阿司匹林": "CC(=O)Oc1ccccc1C(=O)O",
    "乙酰水杨酸": "CC(=O)Oc1ccccc1C(=O)O",
    "布洛芬": "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
    "咖啡因": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
    # 英文
    "water": "O",
    "ethanol": "CCO",
    "methanol": "CO",
    "acetone": "CC(=O)C",
    "acetic acid": "CC(=O)O",
    "benzene": "c1ccccc1",
    "toluene": "Cc1ccccc1",
    "phenol": "Oc1ccccc1",
    "aniline": "Nc1ccccc1",
    "bromobenzene": "c1ccccc1Br",
    "chlorobenzene": "c1ccccc1Cl",
    "iodobenzene": "c1ccccc1I",
    "phenylboronic acid": "B(O)(O)c1ccccc1",
    "4-formylbenzoic acid": "O=Cc1ccc(C(=O)O)cc1",
    "p-formylbenzoic acid": "O=Cc1ccc(C(=O)O)cc1",
    "terephthalaldehydic acid": "O=Cc1ccc(C(=O)O)cc1",
    "methyl glycinate": "COC(=O)CN",
    "glycine methyl ester": "COC(=O)CN",
    "methyl glycinate hydrochloride": "Cl.COC(=O)CN",
    "glycine methyl ester hydrochloride": "Cl.COC(=O)CN",
    "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
    "ibuprofen": "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
}


def _load_cache() -> Dict[str, str]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache_entry(name: str, smiles: str) -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_cache()
    cache[name.strip()] = smiles
    cache[_normalize_name(name)] = smiles
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _looks_like_smiles(text: str) -> bool:
    text = text.strip()
    if not text or re.search(r"[\u4e00-\u9fff]", text):
        return False
    # 英文名称（含空格、多段字母）不当 SMILES
    if " " in text or re.search(r"[A-Za-z]{4,}", text) and not re.search(
        r"[\[\]=#@$%/\\]", text
    ):
        # 真正 SMILES 常含括号/环数字/键符号；纯英文单词或 “4-formyl...” 排除
        if not re.search(r"\(|\)|=|#|@|\\|/", text) and not re.search(
            r"[0-9].*[a-z]|[a-z].*[0-9]", text
        ):
            return False
        if re.fullmatch(r"[0-9A-Za-z\-\s]+", text) and " " in text:
            return False
        if re.fullmatch(r"[0-9]?-?[A-Za-z]+(-[A-Za-z]+)+(\s+[A-Za-z]+)*", text):
            return False
    mol = Chem.MolFromSmiles(text, sanitize=False)
    if mol is None:
        return False
    try:
        Chem.SanitizeMol(mol)
    except Exception:
        return False
    return True


def _normalize_name(name: str) -> str:
    s = name.strip()
    # 去掉零宽/不可见字符
    s = re.sub(r"[\u200b-\u200f\ufeff\u00a0]", "", s)
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("，", ",").replace("·", ".")
    s = s.replace("－", "-").replace("—", "-")
    # 全角数字/字母转半角
    out = []
    for ch in s:
        code = ord(ch)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    s = "".join(out)
    s = re.sub(r"\s+", "", s)
    return s.lower()


def lookup_local(name: str) -> Optional[str]:
    cache = _load_cache()
    candidates = [
        name.strip(),
        _normalize_name(name),
        re.sub(r"\s+", "", name.strip()),
    ]
    # 也用归一化后的键去撞词典里每一个归一化键
    norm_dict = {_normalize_name(k): v for k, v in COMMON_NAME_TO_SMILES.items()}
    norm_cache = {_normalize_name(k): v for k, v in cache.items()}

    for key in candidates:
        if key in cache:
            return cache[key]
        if key in COMMON_NAME_TO_SMILES:
            return COMMON_NAME_TO_SMILES[key]
        n = _normalize_name(key)
        if n in norm_cache:
            return norm_cache[n]
        if n in norm_dict:
            return norm_dict[n]

    # 别名展开后查本地
    for alias in expand_chinese_aliases(name):
        k = alias.strip()
        n = _normalize_name(alias)
        if k in COMMON_NAME_TO_SMILES:
            return COMMON_NAME_TO_SMILES[k]
        if n in norm_dict:
            return norm_dict[n]
        if k in cache:
            return cache[k]
        if n in norm_cache:
            return norm_cache[n]
    return None


def _canon_smiles(smi: str) -> Optional[str]:
    """允许盐形式如 Cl.COC(=O)CN。"""
    if not smi:
        return None
    if "." in smi:
        parts = []
        for p in smi.split("."):
            mol = Chem.MolFromSmiles(p)
            if mol is None:
                return None
            parts.append(Chem.MolToSmiles(mol))
        return ".".join(parts)
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol)


def expand_chinese_aliases(name: str) -> List[str]:
    """把中文俗名/系统名展开成更多检索候选（含英文）。"""
    raw = name.strip()
    aliases = [raw, _normalize_name(raw), re.sub(r"\s+", "", raw)]

    base = raw
    salt_prefix = False
    for token in ("盐酸", "氢溴酸", "氢碘酸", "硫酸", "三氟乙酸", "TFA"):
        if base.startswith(token):
            base = base[len(token) :]
            salt_prefix = True
            aliases.append(base)
            if token == "盐酸":
                aliases.append(base + "盐酸盐")
        if base.endswith(token) or base.endswith(token + "盐"):
            base2 = re.sub(rf"{re.escape(token)}盐?$", "", base)
            aliases.append(base2)
            salt_prefix = True

    replacements = [
        ("氨基乙酸", "甘氨酸"),
        ("甘氨酸", "氨基乙酸"),
        ("甲酰基", "醛基"),
        ("醛基", "甲酰基"),
        ("对羧基苯甲醛", "对醛基苯甲酸"),
        ("对醛基苯甲酸", "对羧基苯甲醛"),
    ]
    more: List[str] = []
    for a in list(aliases):
        for old, new in replacements:
            if old in a:
                more.append(a.replace(old, new))
    aliases.extend(more)

    orient_map = {
        "对": ("4-", "p-", "para-"),
        "邻": ("2-", "o-", "ortho-"),
        "间": ("3-", "m-", "meta-"),
    }
    group_map = {
        "醛基苯甲酸": "formylbenzoic acid",
        "甲酰基苯甲酸": "formylbenzoic acid",
        "羧基苯甲醛": "formylbenzoic acid",
        "氨基苯甲酸": "aminobenzoic acid",
        "硝基苯甲酸": "nitrobenzoic acid",
        "羟基苯甲酸": "hydroxybenzoic acid",
        "溴苯": "bromobenzene",
        "氯苯": "chlorobenzene",
        "碘苯": "iodobenzene",
        "苯硼酸": "phenylboronic acid",
        "苯基硼酸": "phenylboronic acid",
        "甘氨酸甲酯": "glycine methyl ester",
        "氨基乙酸甲酯": "methyl glycinate",
        "甘氨酸": "glycine",
        "氨基乙酸": "glycine",
    }

    for a in list(aliases):
        for cn_orient, en_orients in orient_map.items():
            for cn_group, en_group in group_map.items():
                if a.startswith(cn_orient) and cn_group in a:
                    for en_o in en_orients:
                        aliases.append(f"{en_o}{en_group}")
        for cn_group, en_group in group_map.items():
            if a == cn_group or a.endswith(cn_group):
                aliases.append(en_group)
                if salt_prefix or "盐酸" in raw:
                    aliases.append(f"{en_group} hydrochloride")

    seen = set()
    out: List[str] = []
    for x in aliases:
        x = x.strip()
        if not x:
            continue
        key = _normalize_name(x)
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def lookup_cir(name: str, timeout: float = 5.0) -> Optional[str]:
    """NIH Chemical Identifier Resolver。"""
    url = f"https://cactus.nci.nih.gov/chemical/structure/{quote(name.strip())}/smiles"
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return None
        smi = resp.text.strip()
        return _canon_smiles(smi)
    except Exception:
        return None


def lookup_pubchem(name: str, timeout: float = 5.0) -> Optional[str]:
    """兼容旧接口：只返回 SMILES。优先走 chem_apis 封装。"""
    try:
        from chem_apis import pubchem_lookup

        hit = pubchem_lookup(name, timeout=timeout)
        if hit.get("ok") and hit.get("smiles"):
            return _canon_smiles(hit["smiles"])
    except TypeError:
        # 旧签名无 timeout
        try:
            from chem_apis import pubchem_lookup

            hit = pubchem_lookup(name)
            if hit.get("ok") and hit.get("smiles"):
                return _canon_smiles(hit["smiles"])
        except Exception:
            pass
    except Exception:
        pass
    url = (
        "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/"
        f"{quote(name.strip())}/property/CanonicalSMILES,IsomericSMILES/JSON"
    )
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            return None
        props = resp.json()["PropertyTable"]["Properties"][0]
        smi = props.get("IsomericSMILES") or props.get("CanonicalSMILES")
        return _canon_smiles(smi) if smi else None
    except Exception:
        return None


def resolve_online_candidates(candidates: List[str]) -> Tuple[Optional[str], str]:
    """并行短超时：优先 PubChem（国内较稳），CIR 作辅；总等待 ≤3.5s。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    cands = [c for c in candidates if c][:3]
    if not cands:
        return None, ""

    def _one(cand: str, kind: str) -> Tuple[Optional[str], str]:
        if kind == "cir":
            smi = lookup_cir(cand, timeout=2.0)
            return smi, f"cir:{cand}" if smi else ""
        smi = lookup_pubchem(cand, timeout=2.5)
        return smi, f"pubchem:{cand}" if smi else ""

    tasks = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        # PubChem 优先提交
        for cand in cands:
            tasks.append(pool.submit(_one, cand, "pubchem"))
        for cand in cands[:2]:
            tasks.append(pool.submit(_one, cand, "cir"))
        try:
            for fut in as_completed(tasks, timeout=3.5):
                try:
                    smi, src = fut.result()
                except Exception:
                    continue
                if smi:
                    return smi, src
        except TimeoutError:
            pass
    return None, ""


def _extract_smiles_from_llm(text: str) -> Optional[str]:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    # JSON
    try:
        data = json.loads(text)
        smi = data.get("smiles") or data.get("SMILES")
        if smi:
            return _canon_smiles(str(smi))
    except json.JSONDecodeError:
        pass
    m = re.search(r'"smiles"\s*:\s*"([^"]+)"', text, flags=re.I)
    if m:
        return _canon_smiles(m.group(1))
    # 裸 SMILES 行
    for line in text.splitlines():
        line = line.strip().strip("`")
        if not line or " " in line:
            continue
        c = _canon_smiles(line)
        if c:
            return c
    return None


def lookup_agnes(name: str, aliases: Optional[Iterable[str]] = None) -> Optional[str]:
    try:
        import openai
        from dotenv import load_dotenv

        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            return None
        openai.api_key = api_key
        openai.api_base = (
            os.getenv("OPENAI_API_BASE")
            or os.getenv("OPENAI_BASE_URL")
            or "https://apihub.agnes-ai.com/v1"
        ).rstrip("/")
        model = os.getenv("CHEMCROW_MODEL", "agnes-2.5-flash")
        alias_txt = ", ".join(list(aliases or [])[:12])
        prompt = (
            "将化合物名称转为 RDKit 可解析的 SMILES。"
            "若为盐酸盐等，可用 Cl.有机分子 形式。"
            "只输出 JSON：{\"smiles\":\"...\",\"english_name\":\"...\"}\n"
            f"名称: {name}\n别名候选: {alias_txt}"
        )
        resp = openai.ChatCompletion.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a chemistry nomenclature expert. Output JSON only.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=1024,
        )
        msg = resp["choices"][0]["message"]
        content = msg.get("content") or ""
        # 有些模型把答案放 reasoning 里截断 content；再兜底扫一遍
        smi = _extract_smiles_from_llm(content)
        if smi:
            return smi
        reason = msg.get("reasoning_content") or ""
        return _extract_smiles_from_llm(reason)
    except Exception:
        return None


def resolve_to_smiles(user_input: str) -> Tuple[bool, str, str]:
    """
    Returns:
        (ok, smiles_or_error, source)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    text = (user_input or "").strip()
    if not text:
        return False, "输入为空", ""

    if _looks_like_smiles(text):
        c = _canon_smiles(text)
        if c:
            return True, c, "smiles"

    local = lookup_local(text)
    if local:
        c = _canon_smiles(local)
        if c:
            return True, c, "local/俗名"

    aliases = expand_chinese_aliases(text)
    has_zh = bool(re.search(r"[\u4e00-\u9fff]", text))

    # 中文名：在线与 LLM 并行，避免 PubChem/CIR 卡住再等一轮 LLM
    if has_zh:
        online_smi, online_src = None, ""
        ag_smi = None
        with ThreadPoolExecutor(max_workers=2) as pool:
            f_on = pool.submit(resolve_online_candidates, aliases)
            f_ag = pool.submit(lookup_agnes, text, aliases)
            try:
                for fut in as_completed([f_on, f_ag], timeout=18.0):
                    try:
                        if fut is f_on:
                            online_smi, online_src = fut.result()
                            if online_smi:
                                _save_cache_entry(text, online_smi)
                                for a in aliases[:5]:
                                    _save_cache_entry(a, online_smi)
                                return True, online_smi, online_src
                        else:
                            ag_smi = fut.result()
                            if ag_smi:
                                _save_cache_entry(text, ag_smi)
                                return True, ag_smi, "agnes"
                    except Exception:
                        continue
            except TimeoutError:
                pass
        if online_smi:
            return True, online_smi, online_src
        if ag_smi:
            return True, ag_smi, "agnes"
    else:
        online_smi, online_src = resolve_online_candidates(aliases)
        if online_smi:
            _save_cache_entry(text, online_smi)
            for a in aliases[:5]:
                _save_cache_entry(a, online_smi)
            return True, online_smi, online_src
        ag = lookup_agnes(text, aliases=aliases)
        if ag:
            _save_cache_entry(text, ag)
            return True, ag, "agnes"

    hint = "；已尝试别名: " + " / ".join(aliases[:6]) if aliases else ""
    return False, f"无法识别名称或 SMILES：{text}{hint}", ""
