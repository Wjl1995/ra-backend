"""轻量级结构导航 · 接入层接口。

挂在 ``/api/v1/documents/{document_id}/structure`` 下，提供 5 个核心接口：
- ``GET  /tree``                  完整结构树（讲/卡片/要点）
- ``GET  /concepts/{name}``       概念出现位置 + 1–2 跳邻居
- ``GET  /graph``                 全量概念图谱（``?section=`` 取 1 跳子图）
- ``GET  /sections/{section_id}`` 单章节内容/锚点
- ``POST /search``                语义检索（复用向量引擎，补标题路径元数据）

鉴权：复用 ``get_current_user`` + 文档归属校验；结构未构建时按需惰性重建。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from apps.backend.dependencies import get_current_user, get_db
from apps.backend.models import Document, User
from apps.backend.services import structure_service

router = APIRouter(prefix="/documents", tags=["structure"])


class StructureSearchPayload(BaseModel):
    query: str
    top_k: int = 5


def _get_owned_document(db: Session, document_id: int, user: User) -> Document:
    document = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == user.id)
        .first()
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def _ensure_structure(db: Session, document: Document) -> dict:
    data = structure_service.load_structure(document)
    if not data or not data.get("tree"):
        if document.chunks:
            data = structure_service.rebuild_and_persist(db, document)
        else:
            data = {"tree": [], "graph": {"nodes": [], "edges": []}, "chunk_sections": {}}
    return data


@router.get("/{document_id}/structure/tree")
def structure_tree(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_owned_document(db, document_id, current_user)
    data = _ensure_structure(db, document)
    return {"document_id": document_id, "tree": data.get("tree", [])}


@router.get("/{document_id}/structure/graph")
def structure_graph(
    document_id: int,
    section: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_owned_document(db, document_id, current_user)
    data = _ensure_structure(db, document)
    graph = data.get("graph", {"nodes": [], "edges": []})
    if section:
        graph = structure_service.subgraph(graph, section)
    return {"document_id": document_id, **graph}


@router.get("/{document_id}/structure/sections/{section_id}")
def structure_section(
    document_id: int,
    section_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_owned_document(db, document_id, current_user)
    data = _ensure_structure(db, document)
    node = structure_service.find_node(data.get("tree", []), section_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Section not found")

    chunk_map = {c.id: c for c in document.chunks}
    seen: set[int] = set()
    content = []
    for cid in structure_service.collect_chunk_ids(node):
        if cid in seen:
            continue
        seen.add(cid)
        chunk = chunk_map.get(cid)
        if chunk:
            content.append({"chunk_id": cid, "text": chunk.content or ""})
    return {"document_id": document_id, "section": {**node, "content": content}}


@router.get("/{document_id}/structure/concepts/{name}")
def structure_concept(
    document_id: int,
    name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_owned_document(db, document_id, current_user)
    data = _ensure_structure(db, document)
    tree = data.get("tree", [])

    node = structure_service.find_node(tree, name)
    if node is None:
        node = structure_service.find_node_by_title(tree, name)
    if node is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Concept not found")

    chunk_map = {c.id: c for c in document.chunks}
    locations = structure_service.node_locations(node, chunk_map)
    neighbors = structure_service.compute_neighbors(data.get("graph", {"nodes": [], "edges": []}), node["id"])

    return {
        "document_id": document_id,
        "concept": node["title"],
        "section_id": node["id"],
        "title_path": node.get("path", node["title"]),
        "locations": locations,
        "neighbors": neighbors,
    }


@router.post("/{document_id}/structure/search")
def structure_search(
    document_id: int,
    payload: StructureSearchPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = _get_owned_document(db, document_id, current_user)
    data = _ensure_structure(db, document)

    # 延迟导入：语义检索依赖向量引擎（onnxruntime 等），仅在搜索时加载
    from apps.backend.services import search_service

    matches = search_service.retrieve_relevant_chunks(
        db,
        user=current_user,
        query=payload.query,
        document_id=document_id,
        top_k=payload.top_k or 5,
        published_only=False,
    )
    chunk_sections = data.get("chunk_sections", {})
    results = [
        {
            "chunk_id": match.chunk_id,
            "document_id": match.document_id,
            "document_title": match.document_title,
            "section_id": chunk_sections.get(str(match.chunk_id)),
            "title_path": match.chunk_title,
            "snippet": match.snippet,
            "score": round(match.score, 4),
        }
        for match in matches
    ]
    return {"document_id": document_id, "query": payload.query, "results": results}
