"""两原料 + 条件 → 产物/副产物候选 + 条件优化建议。

优先 IBM RXN4Chemistry；无 Key 时回退 Agnes（会明确标注为 LLM 估计）。
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from dotenv import load_dotenv
from rdkit import Chem
from rdkit.Chem import Draw


@dataclass
class MoleculeHit:
    smiles: str
    rank: int
    score: Optional[float] = None
    role: str = "product"  # product | alternative | byproduct_candidate
    source: str = "rxn"
    note: str = ""


@dataclass
class ConditionSuggestion:
    solvent: str = ""
    temperature_c: str = ""
    catalyst: str = ""
    base: str = ""
    additive: str = ""
    time_h: str = ""
    atmosphere: str = ""
    # 投料比与用量（以原料 A = 1.0 equiv / 1.0 mmol 为基准）
    reactant_a_equiv: str = "1.0"
    reactant_b_equiv: str = ""
    catalyst_mol_percent: str = ""
    base_equiv: str = ""
    additive_equiv: str = ""
    solvent_ml_per_mmol_a: str = ""
    concentration_m: str = ""
    scale_note: str = ""  # 例如：按 A=1 mmol 计算的绝对用量说明
    rationale: str = ""
    expected_effect: str = ""


@dataclass
class PredictResult:
    precursors: str
    input_conditions: Dict[str, str]
    products: List[MoleculeHit] = field(default_factory=list)
    condition_suggestions: List[ConditionSuggestion] = field(default_factory=list)
    literature: List[Dict[str, str]] = field(default_factory=list)
    engine: str = ""
    llm_model: str = ""
    product_backend: str = ""  # llm | rxn | reactiont5
    warnings: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def validate_smiles(smi: str) -> Tuple[bool, str]:
    smi = (smi or "").strip()
    if not smi:
        return False, "SMILES 为空"
    mol = Chem.MolFromSmiles(smi)
    if mol is None:
        return False, f"无法解析 SMILES: {smi}"
    return True, Chem.MolToSmiles(mol)


def mol_image(smiles: str, size: Tuple[int, int] = (280, 200)):
    ok, canon = validate_smiles(smiles)
    if not ok:
        return None
    mol = Chem.MolFromSmiles(canon)
    return Draw.MolToImage(mol, size=size)


def build_precursors(
    reactant_a: str,
    reactant_b: str,
    reagents: str = "",
) -> str:
    parts: List[str] = []
    for item in (reactant_a, reactant_b, reagents):
        item = (item or "").strip()
        if not item:
            continue
        # 允许多个试剂用 . 或 , 分隔
        for piece in re.split(r"[.,;]\s*", item):
            piece = piece.strip()
            if not piece:
                continue
            ok, canon = validate_smiles(piece)
            if not ok:
                raise ValueError(canon)
            parts.append(canon)
    if len(parts) < 2:
        raise ValueError("至少需要两个有效反应物 SMILES")
    return ".".join(parts)


class RXNPredictor:
    """IBM RXN 正向预测。"""

    def __init__(self, api_key: str, project_id: Optional[str] = None):
        from rxn4chemistry import RXN4ChemistryWrapper

        self.api_key = api_key
        self.client = RXN4ChemistryWrapper(api_key=api_key)
        self.project_id = project_id or os.getenv("RXN4CHEM_PROJECT_ID") or ""
        self._ensure_project()

    def _ensure_project(self) -> None:
        if self.project_id:
            self.client.set_project(self.project_id)
            return
        # 尝试复用已有项目，否则新建
        try:
            projects = self.client.list_all_projects()
            status = projects.get("response", {}).get("payload", {}).get("projects") or []
            if status:
                self.project_id = status[0].get("id") or status[0].get("_id") or ""
        except Exception:
            self.project_id = ""

        if not self.project_id:
            self.client.create_project("chemcrow-lab")
            self.project_id = getattr(self.client, "project_id", "") or ""
        else:
            self.client.set_project(self.project_id)

    def predict(self, precursors: str, top_n: int = 5) -> List[MoleculeHit]:
        response = self.client.predict_reaction(precursors)
        prediction_id = response.get("prediction_id")
        if not prediction_id:
            raise RuntimeError(f"RXN 未返回 prediction_id: {response}")

        attempts: List[dict] = []
        last_err: Optional[Exception] = None
        for _ in range(20):
            time.sleep(2)
            try:
                results = self.client.get_predict_reaction_results(prediction_id)
                payload = results.get("response", {}).get("payload", {})
                attempts = payload.get("attempts") or []
                if attempts:
                    break
            except Exception as exc:  # noqa: BLE001
                last_err = exc
        if not attempts:
            raise RuntimeError(f"RXN 预测超时或失败: {last_err}")

        hits: List[MoleculeHit] = []
        for i, att in enumerate(attempts[:top_n]):
            # attempts 结构: productMolecule.smiles 或 smiles 字段
            smi = (
                (att.get("productMolecule") or {}).get("smiles")
                or att.get("smiles")
                or ""
            )
            # 反应式里常带 >>，取产物侧
            if ">>" in smi:
                smi = smi.split(">>")[-1]
            # 多产物用 . 连接时拆开
            product_pieces = [p for p in smi.split(".") if p]
            confidence = att.get("confidence") or att.get("score")
            try:
                score = float(confidence) if confidence is not None else None
            except (TypeError, ValueError):
                score = None

            if not product_pieces:
                continue
            # 第一个当主产物片段集合；整串作为候选
            ok, canon = validate_smiles(product_pieces[0] if len(product_pieces) == 1 else smi)
            if not ok and product_pieces:
                # 逐个加入
                for j, piece in enumerate(product_pieces):
                    ok2, c2 = validate_smiles(piece)
                    if not ok2:
                        continue
                    role = "product" if i == 0 and j == 0 else "byproduct_candidate"
                    hits.append(
                        MoleculeHit(
                            smiles=c2,
                            rank=len(hits) + 1,
                            score=score,
                            role=role,
                            source="rxn",
                        )
                    )
                continue

            role = "product" if i == 0 else "alternative"
            if i >= 1:
                role = "byproduct_candidate"
            hits.append(
                MoleculeHit(
                    smiles=canon if ok else smi,
                    rank=i + 1,
                    score=score,
                    role=role if i == 0 else "byproduct_candidate",
                    source="rxn",
                )
            )
        return hits


def _agnes_chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.2,
    model: Optional[str] = None,
) -> str:
    """调用 OpenAI 兼容接口（默认 Agnes）；可指定 model。"""
    load_dotenv()
    import openai

    api_key = os.getenv("OPENAI_API_KEY", "")
    api_base = (
        os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or "https://apihub.agnes-ai.com/v1"
    )
    model = (model or os.getenv("CHEMCROW_MODEL") or "agnes-2.5-flash").strip()
    if not api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY（LLM）")

    openai.api_key = api_key
    openai.api_base = api_base.rstrip("/")

    last_text = ""
    for attempt in range(2):
        resp = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature if attempt == 0 else 0,
            max_tokens=4096,
        )
        msg = resp["choices"][0]["message"]
        content = (msg.get("content") or "").strip()
        reasoning = (msg.get("reasoning_content") or "").strip()
        candidates = [content, reasoning, f"{content}\n{reasoning}".strip()]
        for cand in candidates:
            if not cand:
                continue
            last_text = cand
            if "{" in cand and (
                "smiles" in cand
                or "products" in cand
                or "suggestions" in cand
                or "papers" in cand
            ):
                return cand
            if cand.startswith("{") or "```" in cand:
                return cand
        if attempt == 0:
            messages = [
                {
                    "role": "system",
                    "content": "Output ONLY a JSON object. No markdown. No explanation.",
                },
                messages[-1],
            ]
    return last_text


def current_llm_label(model: Optional[str] = None) -> str:
    model = (model or os.getenv("CHEMCROW_MODEL") or "agnes-2.5-flash").strip()
    base = (
        os.getenv("OPENAI_API_BASE")
        or os.getenv("OPENAI_BASE_URL")
        or "https://apihub.agnes-ai.com/v1"
    )
    return f"{model} @ {base.rstrip('/')}"


def predict_with_agnes(
    precursors: str,
    conditions: Dict[str, str],
    top_n: int = 5,
    llm_model: Optional[str] = None,
) -> List[MoleculeHit]:
    prompt = f"""根据反应物与条件预测主产物和副产物。只输出 JSON。

反应物(SMILES，`.`分隔): {precursors}
条件: {json.dumps(conditions, ensure_ascii=False)}

格式:
{{"products":[{{"smiles":"...","role":"product","note":"..."}}]}}

要求:
- 最多 {top_n} 个
- smiles 必须合法
- 第一个为主产物 role=product，其余 byproduct_candidate
"""
    text = _agnes_chat(
        [
            {"role": "system", "content": "Output ONLY valid JSON. No markdown fences."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        model=llm_model,
    )
    try:
        data = _extract_json(text)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"LLM 返回无法解析为 JSON（常见原因：模型推理占满输出）。原始片段: {text[:200]!r}"
        ) from exc

    used_model = (llm_model or os.getenv("CHEMCROW_MODEL") or "agnes-2.5-flash").strip()
    hits: List[MoleculeHit] = []
    for i, item in enumerate(data.get("products") or []):
        smi = (item.get("smiles") or "").strip()
        ok, canon = validate_smiles(smi)
        if not ok:
            continue
        role = item.get("role") or ("product" if i == 0 else "byproduct_candidate")
        hits.append(
            MoleculeHit(
                smiles=canon,
                rank=len(hits) + 1,
                score=None,
                role=role,
                source=f"llm:{used_model}",
                note=str(item.get("note") or ""),
            )
        )
    if not hits:
        raise RuntimeError(f"LLM 未给出有效产物 SMILES。原始: {text[:300]!r}")
    return hits


def suggest_conditions_with_agnes(
    precursors: str,
    conditions: Dict[str, str],
    products: Sequence[MoleculeHit],
    llm_model: Optional[str] = None,
) -> List[ConditionSuggestion]:
    prod_txt = ", ".join(f"{p.smiles}({p.role})" for p in products[:5]) or "未知"
    prompt = f"""你是有机合成条件与投料优化助手。给出最多3套方案，含投料比（A=1.0 mmol 基准）。只输出 JSON。

反应物: {precursors}
当前条件: {json.dumps(conditions, ensure_ascii=False)}
预测产物: {prod_txt}

格式:
{{"suggestions":[{{"solvent":"","temperature_c":"","catalyst":"","base":"","additive":"","time_h":"","atmosphere":"","reactant_a_equiv":"1.0","reactant_b_equiv":"1.2","catalyst_mol_percent":"5","base_equiv":"2.0","additive_equiv":"","solvent_ml_per_mmol_a":"5","concentration_m":"","scale_note":"","rationale":"","expected_effect":""}}]}}
"""
    text = _agnes_chat(
        [
            {"role": "system", "content": "Output ONLY valid JSON. No markdown fences."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        model=llm_model,
    )
    try:
        data = _extract_json(text)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"条件优化 JSON 解析失败: {text[:200]!r}") from exc

    out: List[ConditionSuggestion] = []
    for item in data.get("suggestions") or []:
        out.append(
            ConditionSuggestion(
                solvent=str(item.get("solvent") or ""),
                temperature_c=str(item.get("temperature_c") or ""),
                catalyst=str(item.get("catalyst") or ""),
                base=str(item.get("base") or ""),
                additive=str(item.get("additive") or ""),
                time_h=str(item.get("time_h") or ""),
                atmosphere=str(item.get("atmosphere") or ""),
                reactant_a_equiv=str(item.get("reactant_a_equiv") or "1.0"),
                reactant_b_equiv=str(item.get("reactant_b_equiv") or ""),
                catalyst_mol_percent=str(item.get("catalyst_mol_percent") or ""),
                base_equiv=str(item.get("base_equiv") or ""),
                additive_equiv=str(item.get("additive_equiv") or ""),
                solvent_ml_per_mmol_a=str(item.get("solvent_ml_per_mmol_a") or ""),
                concentration_m=str(item.get("concentration_m") or ""),
                scale_note=str(item.get("scale_note") or ""),
                rationale=str(item.get("rationale") or ""),
                expected_effect=str(item.get("expected_effect") or ""),
            )
        )
    return out


def _extract_json(text: str) -> dict:
    if text is None:
        raise ValueError("模型返回为空")
    text = str(text).strip()
    if not text:
        raise ValueError("模型返回为空字符串")

    # 去掉 markdown 围栏
    if "```" in text:
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        else:
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

    # 直接解析
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 截取最外层 {...}
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"未找到 JSON 对象: {text[:120]!r}")
    blob = m.group(0)
    try:
        obj = json.loads(blob)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        # 尝试修补截断的 JSON：常见于 Agnes reasoning 过长
        repaired = _repair_truncated_json(blob)
        if repaired is not None:
            return repaired
        raise ValueError(f"JSON 解析失败: {blob[:120]!r}")
    raise ValueError("JSON 根节点不是对象")


def _repair_truncated_json(blob: str) -> Optional[dict]:
    """尽力修复被截断的 JSON（补齐括号/引号）。"""
    s = blob.strip()
    # 若截断在字符串中间，先合上引号
    if s.count('"') % 2 == 1:
        s += '"'
    # 去掉末尾悬空逗号
    s = re.sub(r",\s*$", "", s)
    # 补齐括号
    opens = s.count("{") - s.count("}")
    opens_arr = s.count("[") - s.count("]")
    if opens < 0 or opens_arr < 0:
        return None
    s += "]" * opens_arr + "}" * opens
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


def run_prediction(
    reactant_a: str,
    reactant_b: str,
    *,
    reagents: str = "",
    solvent: str = "",
    temperature: str = "",
    catalyst: str = "",
    base: str = "",
    time_h: str = "",
    atmosphere: str = "",
    notes: str = "",
    top_n: int = 5,
    product_engine: str = "auto",  # auto | llm | rxn | reactiont5
    llm_model: Optional[str] = None,
    optimize_conditions: bool = True,
    fetch_literature: bool = True,
    rxn_api_key: Optional[str] = None,
) -> PredictResult:
    load_dotenv()
    llm_model = (llm_model or os.getenv("CHEMCROW_MODEL") or "agnes-2.5-flash").strip()
    # 写入环境，便于文献等子调用读到同一模型
    os.environ["CHEMCROW_MODEL"] = llm_model

    precursors = build_precursors(reactant_a, reactant_b, reagents)
    conditions = {
        "solvent": solvent.strip(),
        "temperature": temperature.strip(),
        "catalyst": catalyst.strip(),
        "base": base.strip(),
        "time_h": time_h.strip(),
        "atmosphere": atmosphere.strip(),
        "notes": notes.strip(),
        "reagents": reagents.strip(),
    }

    warnings: List[str] = []
    products: List[MoleculeHit] = []
    engine = ""
    product_backend = ""

    key = (rxn_api_key or os.getenv("RXN4CHEM_API_KEY") or "").strip()
    use_rxn = product_engine in ("auto", "rxn") and bool(key)
    force_llm = product_engine == "llm"
    force_rxn = product_engine == "rxn"
    force_t5 = product_engine == "reactiont5"

    if force_rxn and not key:
        raise RuntimeError("已选择 IBM RXN，但未填写 RXN4CHEM_API_KEY。")

    # --- ReactionT5 本机（仅手动选择；首次下载后本地推理）---
    if force_t5:
        try:
            from reactiont5_remote import MODEL_LABEL, predict_products_local

            parts = precursors.split(".")
            reac = ".".join(parts[:2]) if len(parts) >= 2 else precursors
            reags = ".".join(parts[2:]) if len(parts) > 2 else reagents.strip()
            hits = predict_products_local(reac, reags, top_n=top_n)
            for i, (smi, score) in enumerate(hits):
                ok, canon = validate_smiles(smi)
                if not ok:
                    for piece in smi.split("."):
                        ok2, c2 = validate_smiles(piece)
                        if ok2:
                            products.append(
                                MoleculeHit(
                                    smiles=c2,
                                    rank=len(products) + 1,
                                    score=score,
                                    role="product"
                                    if len(products) == 0
                                    else "byproduct_candidate",
                                    source="reactiont5-local",
                                )
                            )
                            break
                    continue
                products.append(
                    MoleculeHit(
                        smiles=canon,
                        rank=len(products) + 1,
                        score=score,
                        role="product" if i == 0 else "byproduct_candidate",
                        source="reactiont5-local",
                    )
                )
            if products:
                engine = (
                    f"ReactionT5 本机（{MODEL_LABEL}）"
                    f"+ LLM `{llm_model}`（条件/文献）"
                )
                product_backend = "reactiont5"
                warnings.append(
                    "ReactionT5 0.2B 本机推理（优先用本地缓存，无需每次联网）。"
                )
            else:
                raise RuntimeError("ReactionT5 未返回可解析的产物 SMILES")
        except Exception as exc:  # noqa: BLE001
            # 下载/加载失败时自动回退大模型，避免整次预测挂掉
            warnings.append(
                f"ReactionT5 本机不可用，已自动改用大模型 `{llm_model}`：{exc}"
            )
            force_t5 = False
            products = []
            # 不向上抛，继续走下面 LLM/RXN

    if use_rxn and not force_llm and not force_t5 and not products:
        try:
            products = RXNPredictor(key).predict(precursors, top_n=top_n)
            engine = f"IBM RXN4Chemistry（产物）+ LLM `{llm_model}`（条件/文献）"
            product_backend = "rxn"
        except Exception as exc:  # noqa: BLE001
            if force_rxn:
                raise RuntimeError(f"RXN 预测失败: {exc}") from exc
            warnings.append(f"RXN 预测失败，已回退 LLM `{llm_model}`: {exc}")

    if not products:
        try:
            products = predict_with_agnes(
                precursors, conditions, top_n=top_n, llm_model=llm_model
            )
            engine = f"LLM `{llm_model}`（产物估计，非专业反应模型）"
            product_backend = "llm"
            warnings.append(
                f"产物由大模型 `{llm_model}` 估计。可改选「ReactionT5 本机」或填写 RXN Key。"
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"LLM 产物预测失败: {exc}")
            raise RuntimeError(
                f"产物预测失败（模型 `{llm_model}`）。请换引擎/模型重试。"
            ) from exc

    suggestions: List[ConditionSuggestion] = []
    if optimize_conditions:
        try:
            suggestions = suggest_conditions_with_agnes(
                precursors, conditions, products, llm_model=llm_model
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"条件优化失败（可忽略，产物仍可用）: {exc}")

    literature: List[Dict[str, str]] = []
    if fetch_literature:
        try:
            from literature import collect_literature

            def _chat(messages, temperature=0.2):
                return _agnes_chat(messages, temperature=temperature, model=llm_model)

            literature = collect_literature(
                precursors,
                conditions,
                products,
                chat_fn=_chat,
                include_llm=True,
            )
            warnings.append("文献链接中，LLM 线索与 DOI 需人工核实；检索链接可直接打开。")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"文献检索失败: {exc}")

    return PredictResult(
        precursors=precursors,
        input_conditions=conditions,
        products=products,
        condition_suggestions=suggestions,
        literature=literature,
        engine=engine,
        llm_model=llm_model,
        product_backend=product_backend,
        warnings=warnings,
    )
