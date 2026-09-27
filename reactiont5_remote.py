"""ReactionT5 正向预测：本机推理或远程 HTTP API。

模型 sagawa/ReactionT5v2-forward。
已缓存时强制离线加载；仅缺文件时才走 hf-mirror 下载。
远程：设置 REACTIONT5_API_URL（+ 可选 TOKEN）。
"""

from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from typing import Iterator, List, Optional, Tuple

MODEL_ID = "sagawa/ReactionT5v2-forward"
MODEL_LABEL = "ReactionT5v2-forward"

_lock = threading.Lock()
_tokenizer = None
_model = None
_device = "cpu"

_PROXY_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "HF_HTTPS_PROXY",
)
_OFFLINE_KEYS = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE")


@contextmanager
def _offline_env() -> Iterator[None]:
    """强制离线，禁止 huggingface_hub 探测外网。"""
    saved = {k: os.environ.get(k) for k in _OFFLINE_KEYS}
    try:
        for k in _OFFLINE_KEYS:
            os.environ[k] = "1"
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextmanager
def _download_env() -> Iterator[None]:
    """镜像下载：设 HF_ENDPOINT，并临时清掉代理（Clash 常搞挂 hf-mirror）。"""
    saved = {
        k: os.environ[k]
        for k in list(os.environ)
        if k in _PROXY_KEYS or k.lower() in ("no_proxy",) or k in _OFFLINE_KEYS
    }
    try:
        for k in _OFFLINE_KEYS:
            os.environ.pop(k, None)
        if not (os.getenv("HF_ENDPOINT") or "").strip():
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
        if (os.getenv("HF_USE_PROXY") or "").strip().lower() not in ("1", "true", "yes"):
            for k in list(os.environ):
                if k in _PROXY_KEYS or k.lower() == "no_proxy":
                    os.environ.pop(k, None)
            os.environ["NO_PROXY"] = "*"
            os.environ["no_proxy"] = "*"
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "45")
        yield
    finally:
        for k in list(_PROXY_KEYS) + ["NO_PROXY", "no_proxy"] + list(_OFFLINE_KEYS):
            os.environ.pop(k, None)
        os.environ.update({k: v for k, v in saved.items() if v is not None})


def _clean_token() -> Optional[str]:
    token = (os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN") or "").strip()
    token = token.strip().strip('"').strip("'")
    if not token or len(token) < 10 or not token.startswith("hf_"):
        return None
    return token


def _cache_ready(model_id: str) -> bool:
    """本地 hub 缓存是否可用（config + 权重）。"""
    try:
        from huggingface_hub import try_to_load_from_cache

        cfg = try_to_load_from_cache(model_id, "config.json")
        if cfg is None or not os.path.isfile(str(cfg)):
            return False
        for weight in ("model.safetensors", "pytorch_model.bin"):
            w = try_to_load_from_cache(model_id, weight)
            if w is not None and os.path.isfile(str(w)):
                return True
    except Exception:
        pass
    hub = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub")
    safe = "models--" + model_id.replace("/", "--")
    snap = os.path.join(hub, safe, "snapshots")
    if not os.path.isdir(snap):
        return False
    has_cfg = False
    has_w = False
    for root, _dirs, files in os.walk(snap):
        if "config.json" in files:
            has_cfg = True
        if "model.safetensors" in files or "pytorch_model.bin" in files:
            has_w = True
    return has_cfg and has_w


def _from_pretrained_local(cls, model_id: str):
    with _offline_env():
        return cls.from_pretrained(model_id, local_files_only=True)


def _from_pretrained_download(cls, model_id: str):
    token = _clean_token()
    last_exc: Optional[Exception] = None
    attempts: List[dict] = [{"local_files_only": False}]
    if token:
        attempts.append({"local_files_only": False, "token": token})
    with _download_env():
        for kwargs in attempts:
            try:
                return cls.from_pretrained(model_id, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
    raise RuntimeError(
        f"下载 {model_id} 失败（HF_ENDPOINT={os.getenv('HF_ENDPOINT') or 'https://hf-mirror.com'}）: "
        f"{last_exc}\n"
        "可：1) 关掉 Clash 系统代理后重试  2) 设 HF_USE_PROXY=1 走代理  "
        "3) 改选「大模型产物估计」继续预测。"
    )


def _load_model():
    global _tokenizer, _model, _device
    if _model is not None and _tokenizer is not None:
        return _tokenizer, _model, _device

    with _lock:
        if _model is not None and _tokenizer is not None:
            return _tokenizer, _model, _device

        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "本机 ReactionT5 需要: pip install torch transformers sentencepiece\n"
                f"缺少依赖: {exc}"
            ) from exc

        try:
            from cloud_env import reactiont5_allowed

            if not reactiont5_allowed():
                raise RuntimeError(
                    "当前为 Streamlit Cloud / 云端环境：无法在云端直接加载 ReactionT5。"
                    "请配置 REACTIONT5_API_URL 指向本机隧道，或改用大模型。"
                    "本机服务请设 ENABLE_REACTIONT5=1。"
                )
        except ImportError:
            pass

        if _cache_ready(MODEL_ID):
            try:
                _tokenizer = _from_pretrained_local(AutoTokenizer, MODEL_ID)
                _model = _from_pretrained_local(AutoModelForSeq2SeqLM, MODEL_ID)
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    f"本地缓存加载失败（未联网）：{exc}\n"
                    "可删掉 ~/.cache/huggingface/hub/models--sagawa--ReactionT5v2-forward 后重下，"
                    "或改选「大模型产物估计」。"
                ) from exc
        else:
            _tokenizer = _from_pretrained_download(AutoTokenizer, MODEL_ID)
            _model = _from_pretrained_download(AutoModelForSeq2SeqLM, MODEL_ID)

        _model.eval()
        if hasattr(torch, "cuda") and torch.cuda.is_available():
            _device = "cuda"
            _model.to(_device)
        else:
            _device = "cpu"

        return _tokenizer, _model, _device


def build_forward_input(reactants: str, reagents: str = "") -> str:
    reactants = (reactants or "").strip().replace(" ", "")
    reagents = (reagents or "").strip().replace(" ", "")
    return f"REACTANT:{reactants}REAGENT:{reagents}"


def predict_products_local(
    reactants: str,
    reagents: str = "",
    *,
    top_n: int = 5,
) -> List[Tuple[str, Optional[float]]]:
    """本机 beam search。返回 [(smiles, None), ...]。"""
    import torch

    tokenizer, model, device = _load_model()
    text = build_forward_input(reactants, reagents)
    enc = tokenizer(
        text, return_tensors="pt", padding=True, truncation=True, max_length=512
    )
    enc = {k: v.to(device) for k, v in enc.items()}

    n = max(1, min(10, int(top_n)))
    with torch.no_grad():
        outs = model.generate(
            **enc,
            max_new_tokens=128,
            num_beams=n,
            num_return_sequences=n,
            early_stopping=True,
            do_sample=False,
        )
    decoded = tokenizer.batch_decode(outs, skip_special_tokens=True)

    seen = set()
    result: List[Tuple[str, Optional[float]]] = []
    for t in decoded:
        s = (t or "").replace(" ", "").strip().rstrip(".")
        s = re.sub(r"^(PRODUCT:|product:)", "", s)
        if not s or s in seen:
            continue
        seen.add(s)
        result.append((s, None))
        if len(result) >= n:
            break
    return result


def predict_products_remote(
    reactants: str,
    reagents: str = "",
    *,
    top_n: int = 5,
    timeout: float = 300.0,
    max_wait_load: float = 240.0,
) -> List[Tuple[str, Optional[float]]]:
    """调用远程 ReactionT5 HTTP 服务（本机隧道 / 自建机）。

    环境变量:
      REACTIONT5_API_URL    如 https://xxxx.trycloudflare.com 或 http://host:8765
      REACTIONT5_API_TOKEN  与服务端一致的令牌（可选但强烈建议）
    """
    del max_wait_load
    import json
    import urllib.error
    import urllib.request

    base = (os.getenv("REACTIONT5_API_URL") or "").strip().rstrip("/")
    if not base:
        raise RuntimeError(
            "未配置 REACTIONT5_API_URL。请在本机启动 reactiont5_server，"
            "用 cloudflared/ngrok 暴露后，把公网 URL 写入 Streamlit Secrets。"
        )

    url = base + "/predict"
    payload = json.dumps(
        {
            "reactants": reactants,
            "reagents": reagents or "",
            "top_n": int(top_n),
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    token = (os.getenv("REACTIONT5_API_TOKEN") or "").strip()
    if token:
        req.add_header("X-API-Token", token)
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=float(timeout)) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"ReactionT5 远程 HTTP {exc.code}: {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            f"无法连接 ReactionT5 远程服务 `{base}`：{exc}\n"
            "请确认本机服务已启动，且隧道（cloudflared/ngrok）在线。"
        ) from exc

    products = data.get("products") or []
    out: List[Tuple[str, Optional[float]]] = []
    for p in products:
        if isinstance(p, dict):
            smi = (p.get("smiles") or "").strip()
            sc = p.get("score")
        else:
            continue
        if smi:
            out.append((smi, sc if isinstance(sc, (int, float)) else None))
    return out


def predict_products(
    reactants: str,
    reagents: str = "",
    *,
    top_n: int = 5,
) -> List[Tuple[str, Optional[float]]]:
    """优先远程 API；无 URL 时再本机推理。"""
    if (os.getenv("REACTIONT5_API_URL") or "").strip():
        return predict_products_remote(reactants, reagents, top_n=top_n)
    return predict_products_local(reactants, reagents, top_n=top_n)


def cache_status() -> dict:
    """给 UI 显示：缓存是否就绪 / 是否走远程。"""
    remote = (os.getenv("REACTIONT5_API_URL") or "").strip()
    if remote:
        return {
            "model_id": MODEL_ID,
            "ready": True,
            "mode": f"远程 API · {remote}",
            "remote": True,
            "remote_url": remote,
        }
    ready = _cache_ready(MODEL_ID)
    return {
        "model_id": MODEL_ID,
        "ready": ready,
        "mode": "离线本地缓存" if ready else "需从 hf-mirror 下载 ~800MB",
        "remote": False,
    }
