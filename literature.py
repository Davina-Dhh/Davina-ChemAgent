"""文献检索链接与可选 Semantic Scholar 命中。"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote_plus

import requests


def search_compound_papers(
    *,
    iupac_en: str = "",
    iupac_zh: str = "",
    inchikey: str = "",
    smiles: str = "",
    limit: int = 8,
) -> List[Dict[str, str]]:
    """检索「本化合物 / 相近结构」相关论文，返回具体标题 + 可打开链接。

    不用 doi.org（常打不开）；优先百度学术 / PubMed / Europe PMC 搜标题。
    """
    name = (iupac_en or iupac_zh or "").strip()
    queries: List[str] = []
    if name:
        queries.append(name)
        queries.append(f"{name} synthesis")
        queries.append(f"{name} NMR")
    if inchikey:
        queries.append(inchikey)
    if not queries and smiles:
        queries.append(smiles)

    papers: List[Dict[str, str]] = []
    seen_titles: set = set()

    def _add(title: str, year: str = "", venue: str = "", source: str = "") -> None:
        t = (title or "").strip()
        if len(t) < 12:
            return
        key = t.lower()[:120]
        if key in seen_titles:
            return
        seen_titles.add(key)
        # 可打开：百度学术搜标题 / PubMed 搜标题
        baidu = "https://xueshu.baidu.com/s?wd=" + quote_plus(t[:120])
        pubmed = "https://pubmed.ncbi.nlm.nih.gov/?term=" + quote_plus(f'"{t[:100]}"')
        papers.append(
            {
                "paper_title": t,
                "title": t,
                "year": str(year or ""),
                "venue": (venue or "")[:80],
                "source": source,
                "url": baidu,
                "url_pubmed": pubmed,
                "url_baidu": baidu,
                "note": f"{venue} {year}".strip(),
                "how": "点「百度学术」或「PubMed」打开检索页；也可复制标题去知网 / SciFinder",
            }
        )

    # Crossref：带引号搜系统名，更容易命中含该化合物的文章
    q0 = f'"{name}"' if name else (queries[0] if queries else "")
    if q0:
        try:
            resp = requests.get(
                "https://api.crossref.org/works",
                params={
                    "query.bibliographic": name or q0,
                    "query": q0,
                    "rows": max(limit, 6),
                    "select": "DOI,title,container-title,published-print,published-online,type",
                    "filter": "type:journal-article",
                },
                headers={"User-Agent": "chemcrow-lab/1.0 (mailto:research@localhost)"},
                timeout=12,
            )
            if resp.status_code == 200:
                for item in resp.json().get("message", {}).get("items") or []:
                    title = (item.get("title") or [""])[0].strip()
                    journal = ((item.get("container-title") or [""])[0] or "")
                    year = ""
                    for k in ("published-print", "published-online"):
                        parts = ((item.get(k) or {}).get("date-parts") or [[]])[0]
                        if parts:
                            year = str(parts[0])
                            break
                    _add(title, year=year, venue=journal, source="Crossref")
        except Exception:
            pass

    # Semantic Scholar
    if name and len(papers) < limit:
        for hit in search_semantic_scholar(name, limit=5):
            _add(
                hit.get("title") or "",
                year="",
                venue=hit.get("note") or "",
                source="SemanticScholar",
            )

    # Europe PMC
    if name and len(papers) < limit:
        try:
            r = requests.get(
                "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
                params={
                    "query": f'"{name}"',
                    "format": "json",
                    "pageSize": 5,
                    "resultType": "lite",
                },
                timeout=12,
            )
            if r.status_code == 200:
                for it in (r.json().get("resultList") or {}).get("result") or []:
                    _add(
                        it.get("title") or "",
                        year=str(it.get("pubYear") or ""),
                        venue=it.get("journalTitle") or "",
                        source="EuropePMC",
                    )
        except Exception:
            pass

    return papers[:limit]


def build_search_links(
    query: str,
    reactant_a: str = "",
    reactant_b: str = "",
    product: str = "",
) -> List[Dict[str, str]]:
    """始终生成可点的检索链接（不依赖是否找到具体论文）。"""
    q = query.strip() or " ".join(
        x for x in [reactant_a, reactant_b, product, "reaction"] if x
    )
    encoded = quote_plus(q)
    links = [
        {
            "title": f"SciFinder-n 登录后按反应/结构搜：{q[:80]}",
            "url": "https://scifinder-n.cas.org/",
            "source": "SciFinder-n",
            "note": "登录后用 Reactions 或 Substances；产物结构见 NMR 区可复制 SMILES/Molfile",
        },
        {
            "title": f"知网：{q[:60]}",
            "url": f"https://kns.cnki.net/kns8s/defaultresult/index?kw={encoded}",
            "source": "知网",
            "note": "国内可开；粘贴反应类型/系统名",
        },
        {
            "title": f"百度学术：{q[:60]}",
            "url": f"https://xueshu.baidu.com/s?wd={encoded}",
            "source": "百度学术",
            "note": "国内一般可开",
        },
        {
            "title": f"PubMed: {q[:60]}",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/?term={encoded}",
            "source": "PubMed",
            "note": "生物医学文献",
        },
        {
            "title": f"Bing: {q[:60]}",
            "url": f"https://www.bing.com/search?q={encoded}",
            "source": "Bing",
            "note": "网页检索",
        },
    ]
    return links


def search_semantic_scholar(query: str, limit: int = 5) -> List[Dict[str, str]]:
    """调用公开 S2 API（无需 key；有 key 更稳）。失败返回空列表。"""
    headers = {"User-Agent": "chemcrow-lab/1.0"}
    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    try:
        resp = requests.get(
            url,
            params={
                "query": query,
                "limit": limit,
                "fields": "title,url,externalIds,year,authors,abstract",
            },
            headers=headers,
            timeout=20,
        )
        if resp.status_code != 200:
            return []
        papers = []
        for item in resp.json().get("data") or []:
            title = item.get("title") or "Untitled"
            paper_url = item.get("url") or ""
            ext = item.get("externalIds") or {}
            doi = ext.get("DOI")
            if doi:
                paper_url = f"https://doi.org/{doi}"
            authors = ", ".join(
                a.get("name", "") for a in (item.get("authors") or [])[:3]
            )
            year = item.get("year") or ""
            papers.append(
                {
                    "title": title,
                    "url": paper_url,
                    "source": "semanticscholar",
                    "note": f"{authors} ({year})".strip(" ()"),
                    "doi": doi or "",
                }
            )
        return papers
    except Exception:
        return []


def suggest_literature_with_llm(
    precursors: str,
    conditions: Dict[str, Any],
    products: Sequence[Any],
    chat_fn,
) -> Dict[str, Any]:
    """
    让 LLM 给出反应类型关键词 + 可能相关的经典文献线索。
    注意：DOI/标题需人工核实，可能存在幻觉。
    """
    prod_txt = ", ".join(
        getattr(p, "smiles", p.get("smiles", "")) for p in list(products)[:3]
    )
    prompt = f"""你是有机合成文献助手。根据反应给出检索关键词，以及最多5条可能相关的文献线索。

反应物 SMILES: {precursors}
条件: {json.dumps(conditions, ensure_ascii=False)}
预测产物: {prod_txt}

只输出 JSON：
{{
  "reaction_type": "反应类型中英文，如 Suzuki coupling / 铃木偶联",
  "search_queries": ["英文检索词1", "英文检索词2"],
  "papers": [
    {{
      "title": "论文标题（尽量真实经典文献；不确定就写综述方向）",
      "authors": "作者或 et al.",
      "year": "年份或空",
      "doi": "DOI或空，不要编造看起来像真的假DOI",
      "why_relevant": "与本反应的相关性"
    }}
  ],
  "disclaimer": "文献线索需人工核实"
}}
规则：不确定 DOI 时必须留空；宁可少给也不要伪造 DOI。
"""
    text = chat_fn(
        [
            {"role": "system", "content": "Return valid JSON only. Never invent DOIs."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if not m:
            return {"reaction_type": "", "search_queries": [], "papers": []}
        return json.loads(m.group(0))


def collect_literature(
    precursors: str,
    conditions: Dict[str, Any],
    products: Sequence[Any],
    chat_fn=None,
    include_llm: bool = True,
) -> List[Dict[str, str]]:
    """汇总：LLM 线索 + S2 命中 + 固定检索链接。"""
    links: List[Dict[str, str]] = []
    queries: List[str] = []
    reaction_type = ""

    if include_llm and chat_fn is not None:
        try:
            meta = suggest_literature_with_llm(
                precursors, conditions, products, chat_fn
            )
            reaction_type = meta.get("reaction_type") or ""
            queries = list(meta.get("search_queries") or [])
            for p in meta.get("papers") or []:
                doi = (p.get("doi") or "").strip()
                url = f"https://doi.org/{doi}" if doi else ""
                if not url and p.get("title"):
                    url = (
                        "https://scholar.google.com/scholar?q="
                        + quote_plus(p["title"])
                    )
                links.append(
                    {
                        "title": p.get("title") or "（无标题）",
                        "url": url,
                        "source": "llm-hint",
                        "note": p.get("why_relevant")
                        or f"{p.get('authors','')} {p.get('year','')}".strip(),
                        "doi": doi,
                        "verify": "需核实",
                    }
                )
        except Exception:
            pass

    if not queries:
        parts = precursors.replace(".", " ")
        queries = [f"{reaction_type} {parts}".strip() or parts]

    # Semantic Scholar 真实命中
    for q in queries[:2]:
        for hit in search_semantic_scholar(q, limit=3):
            links.append(hit)

    # 固定检索入口
    main_q = queries[0] if queries else precursors
    prod = ""
    if products:
        p0 = products[0]
        prod = getattr(p0, "smiles", None) or (
            p0.get("smiles") if isinstance(p0, dict) else ""
        )
    links.extend(
        build_search_links(
            main_q if not reaction_type else f"{reaction_type} {main_q}",
            product=prod or "",
        )
    )

    # 去重 URL
    seen = set()
    uniq: List[Dict[str, str]] = []
    for item in links:
        u = item.get("url") or ""
        key = u or item.get("title")
        if key in seen:
            continue
        seen.add(key)
        uniq.append(item)
    return uniq
