"""本机 ReactionT5 HTTP 推理服务（供 Streamlit Cloud / 公网调用）。

启动（本机，需已缓存或可下载模型）:
  .\\.venv\\Scripts\\python.exe -m uvicorn reactiont5_server:app --host 0.0.0.0 --port 8765

可选环境变量:
  REACTIONT5_API_TOKEN   访问令牌（强烈建议设置；Cloud 与本机一致）
  REACTIONT5_PORT        默认 8765

公网暴露（任选其一）:
  cloudflared tunnel --url http://127.0.0.1:8765
  ngrok http 8765

然后在 Streamlit Cloud Secrets 填:
  REACTIONT5_API_URL = "https://xxxx.trycloudflare.com"
  REACTIONT5_API_TOKEN = "你的令牌"
"""

from __future__ import annotations

import os
import secrets
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from reactiont5_remote import MODEL_LABEL, cache_status, predict_products_local

app = FastAPI(
    title="ChemAgent ReactionT5 Server",
    description="本机 ReactionT5 正向预测 API",
    version="1.0.0",
)


class PredictRequest(BaseModel):
    reactants: str = Field(..., description="反应物 SMILES，用 . 连接")
    reagents: str = Field("", description="试剂 SMILES，可选")
    top_n: int = Field(5, ge=1, le=10)


class PredictHit(BaseModel):
    smiles: str
    score: Optional[float] = None


class PredictResponse(BaseModel):
    ok: bool = True
    model: str = MODEL_LABEL
    products: List[PredictHit]


def _expected_token() -> str:
    return (os.getenv("REACTIONT5_API_TOKEN") or "").strip()


def _check_auth(authorization: Optional[str], x_api_token: Optional[str]) -> None:
    expected = _expected_token()
    if not expected:
        # 未设令牌时允许本机调试，但公网暴露极不安全
        return
    got = ""
    if x_api_token:
        got = x_api_token.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        got = authorization[7:].strip()
    if not got or not secrets.compare_digest(got, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


@app.get("/health")
def health():
    cs = cache_status()
    return {
        "ok": True,
        "model": MODEL_LABEL,
        "cache_ready": bool(cs.get("ready")),
        "mode": cs.get("mode"),
        "auth_required": bool(_expected_token()),
    }


@app.post("/predict", response_model=PredictResponse)
def predict(
    body: PredictRequest,
    authorization: Optional[str] = Header(default=None),
    x_api_token: Optional[str] = Header(default=None, alias="X-API-Token"),
):
    _check_auth(authorization, x_api_token)
    reactants = (body.reactants or "").strip()
    if not reactants:
        raise HTTPException(status_code=400, detail="reactants 不能为空")
    try:
        hits = predict_products_local(
            reactants, body.reagents or "", top_n=body.top_n
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PredictResponse(
        products=[PredictHit(smiles=s, score=sc) for s, sc in hits]
    )


def main() -> None:
    import uvicorn

    port = int((os.getenv("REACTIONT5_PORT") or "8765").strip() or "8765")
    # 服务端自己跑推理，绕过 Cloud 禁用逻辑
    os.environ.setdefault("ENABLE_REACTIONT5", "1")
    uvicorn.run(
        "reactiont5_server:app",
        host="0.0.0.0",
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
