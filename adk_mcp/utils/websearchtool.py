# -*- coding: utf-8 -*-
"""
Hybrid Web Search Toolset (Brave + Exa) for Google ADK
- 내부 DB 없이, 순수 웹 검색만 수행
- Brave: web/news/images/videos
- Exa: 의미 기반 보강 검색 + (옵션) 상위 문서 contents 요약/텍스트 추출
"""

from __future__ import annotations
import os, time, math, json, hashlib
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ADK
from google.adk.tools import FunctionTool, ToolContext
from google.adk.tools.base_toolset import BaseToolset


# -----------------------------
# 설정
# -----------------------------
BRAVE_KEY = (os.environ.get("BRAVE_API_KEY") or "").strip()
EXA_KEY   = (os.environ.get("EXA_API_KEY") or "").strip()

BRAVE_BASE = "https://api.search.brave.com/res/v1"
BRAVE_ENDPOINTS = {
    "web":    f"{BRAVE_BASE}/web/search",
    "news":   f"{BRAVE_BASE}/news/search",
    "images": f"{BRAVE_BASE}/images/search",
    "videos": f"{BRAVE_BASE}/videos/search",
}

EXA_SEARCH   = "https://api.exa.ai/search"
EXA_CONTENTS = "https://api.exa.ai/contents"


# -----------------------------
# 유틸
# -----------------------------
def _rrf(items_groups: List[List[Dict[str, Any]]], weights: Optional[List[float]] = None, k: int = 60, top_k: int = 10) -> List[Dict[str, Any]]:
    """
    Reciprocal Rank Fusion
    score = sum_i (w_i / (k + rank_i))
    키는 URL을 우선 사용(없으면 title/id)
    """
    if weights is None:
        weights = [1.0] * len(items_groups)

    scores: Dict[str, float] = {}
    payload: Dict[str, Dict[str, Any]] = {}

    def key_of(item: Dict[str, Any]) -> str:
        return item.get("url") or item.get("id") or item.get("title", "")

    for group, w in zip(items_groups, weights):
        for r in group:
            key = key_of(r)
            if not key:
                continue
            R = int(r.get("rank", 1000))
            scores[key] = scores.get(key, 0.0) + (w / (k + R))
            # 더 풍부한 스니펫/요약을 갖는 페이로드 유지
            if key not in payload or len(r.get("snippet") or "") > len(payload[key].get("snippet") or ""):
                payload[key] = r

    fused = [dict(payload[k], fused_score=float(v)) for k, v in scores.items()]
    fused.sort(key=lambda x: x["fused_score"], reverse=True)
    return fused[:top_k]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# -----------------------------
# Brave 호출
# -----------------------------
class BraveClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise RuntimeError("BRAVE_API_KEY 미설정")
        self.client = httpx.Client(timeout=20.0, headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        })

    def search(self, query: str, kind: str = "web", count: int = 10,
               country: str = "kr", lang: str = "ko", safesearch: str = "moderate",
               extra_params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        kind: web | news | images | videos
        반환: 통합 스키마 [{title, url, snippet, date, source, rank, thumb?}, ...]
        """
        if kind not in BRAVE_ENDPOINTS:
            raise ValueError(f"Unknown kind: {kind}")
        params = {
            "q": query,
            "count": count,
            "country": country,
            "search_lang": lang,
            "safesearch": safesearch,
        }
        if extra_params:
            params.update({k: v for k, v in extra_params.items() if v is not None})

        r = self.client.get(BRAVE_ENDPOINTS[kind], params=params)
        r.raise_for_status()
        data = r.json()

        out: List[Dict[str, Any]] = []
        # 엔드포인트별 응답 키 분기
        if kind == "web":
            results = (data.get("web") or {}).get("results") or []
            for i, it in enumerate(results, start=1):
                out.append({
                    "title": it.get("title"),
                    "url": it.get("url"),
                    "snippet": it.get("description"),
                    "date": it.get("page_age") or it.get("age"),
                    "source": "brave-web",
                    "rank": i,
                    "favicon": ((it.get("meta_url") or {}).get("favicon")),
                })
        elif kind == "news":
            results = data.get("results") or ((data.get("news") or {}).get("results") or [])
            for i, it in enumerate(results, start=1):
                out.append({
                    "title": it.get("title"),
                    "url": it.get("url"),
                    "snippet": it.get("description"),
                    "date": it.get("age") or it.get("page_age"),
                    "source": "brave-news",
                    "rank": i,
                })
        elif kind == "images":
            results = (data.get("results") or ((data.get("images") or {}).get("results") or []))
            for i, it in enumerate(results, start=1):
                out.append({
                    "title": it.get("title"),
                    "url": it.get("source") or it.get("url"),
                    "snippet": it.get("page_fetched"),
                    "date": it.get("page_fetched"),
                    "thumb": (it.get("thumbnail") or {}).get("src") or it.get("thumbnail"),
                    "image": it.get("properties", {}).get("url") or it.get("url"),
                    "source": "brave-images",
                    "rank": i,
                })
        elif kind == "videos":
            results = (data.get("results") or ((data.get("videos") or {}).get("results") or []))
            for i, it in enumerate(results, start=1):
                out.append({
                    "title": it.get("title"),
                    "url": it.get("url"),
                    "snippet": it.get("description"),
                    "date": it.get("page_age") or it.get("age"),
                    "thumb": (it.get("thumbnail") or {}).get("src"),
                    "source": "brave-videos",
                    "rank": i,
                })
        return out


# -----------------------------
# Exa 호출
# -----------------------------
class ExaClient:
    def __init__(self, api_key: str):
        if not api_key:
            raise RuntimeError("EXA_API_KEY 미설정")
        self.client = httpx.Client(timeout=30.0, headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
        })

    def search(self, query: str, num_results: int = 10, search_type: str = "auto",
               include_domains: Optional[List[str]] = None,
               exclude_domains: Optional[List[str]] = None,
               category: Optional[str] = None,
               start_published: Optional[str] = None,
               end_published: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Exa 의미/키워드 혼합 검색
        """
        body: Dict[str, Any] = {
            "query": query,
            "type": search_type,  # auto | neural | keyword | fast
            "numResults": min(num_results, 100),
        }
        if include_domains: body["includeDomains"] = include_domains
        if exclude_domains: body["excludeDomains"] = exclude_domains
        if category:        body["category"] = category
        if start_published: body["startPublishedDate"] = start_published
        if end_published:   body["endPublishedDate"]   = end_published

        r = self.client.post(EXA_SEARCH, json=body)
        r.raise_for_status()
        data = r.json()
        results = data.get("results") or []
        out: List[Dict[str, Any]] = []
        for i, it in enumerate(results, start=1):
            out.append({
                "title": it.get("title"),
                "url": it.get("url") or it.get("id"),
                "snippet": it.get("summary") or (it.get("highlights") or [None])[0],
                "date": it.get("publishedDate"),
                "source": f"exa-{data.get('resolvedSearchType') or data.get('searchType') or search_type}",
                "rank": i,
            })
        return out

    def contents(self, urls: List[str], want_text: bool = False, want_summary: bool = True, want_highlights: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        상위 결과에 대해 Exa에서 본문/요약/하이라이트 가져오기
        반환: {url: {"text":..., "summary":..., "highlights":[...], ...}}
        """
        if not urls:
            return {}
        body = {
            "urls": urls,
        }
        # Exa docs: text/summary/highlights 플래그 지원
        if want_text:       body["text"] = True
        if want_summary:    body["summary"] = True
        if want_highlights: body["highlights"] = True

        r = self.client.post(EXA_CONTENTS, json=body)
        r.raise_for_status()
        data = r.json()
        out: Dict[str, Dict[str, Any]] = {}
        for it in data.get("results") or []:
            u = it.get("url") or it.get("id")
            if not u: 
                continue
            out[u] = {
                "title": it.get("title"),
                "summary": it.get("summary"),
                "text": it.get("text"),
                "highlights": it.get("highlights"),
                "publishedDate": it.get("publishedDate"),
            }
        return out


# -----------------------------
# Toolset 본체
# -----------------------------
class BraveExaHybridWebToolset(BaseToolset):
    """
    노출 함수:
    - hybrid_web_search: Brave(메인) + Exa(보강) → RRF 결합 → (옵션) Exa Contents로 상위 요약
    - brave_raw: Brave 단일 엔드포인트 생검색
    """
    def __init__(self):
        self.brave = BraveClient(BRAVE_KEY)
        self.exa   = ExaClient(EXA_KEY)

    async def get_tools(self, readonly_context=None) -> List[FunctionTool]:
        return [
            FunctionTool(func=self.hybrid_web_search),
            FunctionTool(func=self.brave_raw),
        ]

    # ----------------- Tools -----------------
    def brave_raw(self, query: str, kind: str = "web", count: int = 10,
                  country: str = "kr", lang: str = "ko") -> Dict[str, Any]:
        """
        Brave 단일 엔드포인트 검색
        kind: web | news | images | videos
        """
        try:
            results = self.brave.search(query, kind=kind, count=count, country=country, lang=lang)
            return {"status": "success", "kind": kind, "query": query, "results": results}
        except Exception as e:
            return {"status": "error", "error": str(e), "kind": kind, "query": query}

    def hybrid_web_search(
        self,
        query: str,
        top_k: int = 10,
        brave_kinds: Optional[List[str]] = None,   # ["web","news"] 등
        brave_each_k: int = 8,
        exa_k: int = 8,
        exa_type: str = "auto",                    # auto|neural|keyword|fast
        fuse_w_brave: float = 1.0,
        fuse_w_exa: float = 1.2,
        enrich_with_exa_contents: bool = True,
        enrich_limit: int = 5,                     # Exa Contents 호출 상한(비용 관리)
        lang: str = "ko",
        country: str = "kr",
        tool_context: Optional[ToolContext] = None
    ) -> Dict[str, Any]:
        """
        Brave(메인) + Exa(보강) 하이브리드 검색
        - Brave: 다양한 vertical(웹/뉴스/이미지/비디오)
        - Exa: 의미 기반 보강 검색
        - RRF 결합으로 최종 top_k 선정
        - (옵션) Exa contents로 상위 N개 요약/텍스트 취합
        """
        brave_kinds = brave_kinds or ["web", "news"]

        debug: Dict[str, Any] = {"brave_counts": {}, "exa_count": 0, "enriched": 0, "ts": _now_iso()}
        groups: List[List[Dict[str, Any]]] = []

        # 1) Brave 다중 호출
        try:
            for k in brave_kinds:
                rs = self.brave.search(query, kind=k, count=brave_each_k, country=country, lang=lang)
                debug["brave_counts"][k] = len(rs)
                groups.append(rs)
        except Exception as e:
            debug["brave_error"] = str(e)

        # 2) Exa 보강 검색
        try:
            exa_rs = self.exa.search(query, num_results=exa_k, search_type=exa_type)
            debug["exa_count"] = len(exa_rs)
            groups.append(exa_rs)
        except Exception as e:
            debug["exa_error"] = str(e)
            exa_rs = []

        # 3) RRF 결합
        weights = []
        for k in brave_kinds:
            weights.append(fuse_w_brave)
        weights.append(fuse_w_exa)
        fused = _rrf(groups, weights=weights, k=60, top_k=top_k)

        # 4) (옵션) 상위 N개 Exa contents로 요약/텍스트 보강
        if enrich_with_exa_contents and fused:
            try:
                urls = []
                for it in fused[:enrich_limit]:
                    if it.get("url"):
                        urls.append(it["url"])
                url2content = self.exa.contents(urls, want_text=False, want_summary=True, want_highlights=True)
                for it in fused:
                    u = it.get("url")
                    if u and u in url2content:
                        c = url2content[u]
                        # summary 우선, 없으면 기존 snippet 유지
                        it["summary"] = c.get("summary")
                        if not it.get("snippet"):
                            it["snippet"] = c.get("summary") or (c.get("highlights") or [None])[0]
                debug["enriched"] = len(url2content)
            except Exception as e:
                debug["enrich_error"] = str(e)

        return {
            "status": "success",
            "query": query,
            "results": fused,
            "debug": debug,
        }