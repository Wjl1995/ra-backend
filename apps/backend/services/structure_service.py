"""轻量级结构导航 · 结构与概念计算服务。

设计目标（见《轻量级结构导航集成设计》）：
- 从知识库文档已解析的 chunk 聚合出层级结构树（按 ``title_path`` 面包屑）。
- 由结构树自动生成概念图谱（节点 = 章节标题，边 = 父子层级 + 可选静态语义边）。
- 提供概念邻居计算（1–2 跳、带衰减打分），用于前端概念关联。

零 NLP 依赖：概念直接来自文档各级标题，静态语义边（contrast / prerequisite /
instance 等）由可选术语表注入。
"""
from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from apps.backend.models import Document


# ════════════════════════════════════════════════════════════
#  结构构建
# ════════════════════════════════════════════════════════════


def build_structure(document: Document, chunks: Iterable[Any], glossary: list[dict] | None = None) -> dict:
    """从文档 chunk 列表聚合结构树、概念图谱与 chunk→章节映射。

    chunk 约定：``chunk.title`` 承载 ``title_path``（" > " 连接的层级面包屑），
    ``chunk.content`` 为正文，``chunk.id`` 为数据库主键。
    """
    chunk_map = {c.id: c for c in chunks}
    root_children: list[dict] = []
    node_index: dict[str, dict] = {}
    path_to_id: dict[str, str] = {}
    chunk_section: dict[int, str] = {}
    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"s{counter}"

    for chunk in chunks:
        raw = (chunk.title or "").strip()
        if ">" in raw:
            parts = [p.strip() for p in raw.split(">")]
        else:
            parts = [raw]
        parts = [p for p in parts if p]
        if not parts:
            parts = [document.title or "未命名文档"]

        accumulated: list[str] = []
        parent_list = root_children
        current: dict | None = None
        for depth, part in enumerate(parts, start=1):
            accumulated.append(part)
            full = " > ".join(accumulated)
            nid = path_to_id.get(full)
            if nid is None:
                node = {
                    "id": next_id(),
                    "title": part,
                    "level": depth,
                    "path": full,
                    "children": [],
                    "preview": "",
                    "chunk_ids": [],
                }
                node_index[node["id"]] = node
                path_to_id[full] = node["id"]
                parent_list.append(node)
            else:
                node = node_index[nid]
            parent_list = node["children"]
            current = node
        if current is None:
            continue
        current["chunk_ids"].append(chunk.id)
        chunk_section[chunk.id] = current["id"]
        snippet = (chunk.content or "").strip()[:240]
        if not current["preview"]:
            current["preview"] = snippet

    _fill_previews(root_children)

    # ── 概念图谱 ──
    nodes = [
        {"id": sid, "name": node["title"], "type": "section", "level": node["level"]}
        for sid, node in node_index.items()
    ]
    edges: list[dict] = []
    for sid, node in node_index.items():
        for child in node["children"]:
            edges.append({"source": sid, "target": child["id"], "type": "sub", "weight": 2})

    if glossary:
        name_to_id = {node["title"]: sid for sid, node in node_index.items()}
        for edge in glossary:
            source = name_to_id.get(edge.get("source"))
            target = name_to_id.get(edge.get("target"))
            if source and target and source != target:
                edges.append(
                    {
                        "source": source,
                        "target": target,
                        "type": edge.get("type", "related"),
                        "weight": edge.get("weight", 1),
                    }
                )

    return {
        "tree": root_children,
        "graph": {"nodes": nodes, "edges": edges},
        "chunk_sections": {str(k): v for k, v in chunk_section.items()},
    }


def _fill_previews(nodes: list[dict]) -> None:
    """后序填充：分支节点沿用首个有内容的子节点 preview。"""
    for node in nodes:
        if node["children"]:
            _fill_previews(node["children"])
            if not node["preview"]:
                for child in node["children"]:
                    if child.get("preview"):
                        node["preview"] = child["preview"]
                        break


def rebuild_and_persist(db: Session, document: Document) -> dict:
    """（重新）构建结构并写回 ``document.structure_json``。"""
    data = build_structure(document, document.chunks)
    document.structure_json = json.dumps(data, ensure_ascii=False)
    document.structure_status = "ready"
    db.add(document)
    db.commit()
    db.refresh(document)
    return data


def load_structure(document: Document) -> dict:
    try:
        data = json.loads(document.structure_json or "{}")
    except Exception:  # noqa: BLE001
        data = {}
    return data or {}


# ════════════════════════════════════════════════════════════
#  查询与计算
# ════════════════════════════════════════════════════════════


def find_node(tree: list[dict], section_id: str) -> dict | None:
    for node in tree:
        if node.get("id") == section_id:
            return node
        found = find_node(node.get("children", []), section_id)
        if found:
            return found
    return None


def find_node_by_title(tree: list[dict], title: str) -> dict | None:
    for node in tree:
        if node.get("title") == title:
            return node
        found = find_node_by_title(node.get("children", []), title)
        if found:
            return found
    return None


def collect_chunk_ids(node: dict) -> list[int]:
    ids = list(node.get("chunk_ids", []))
    for child in node.get("children", []):
        ids.extend(collect_chunk_ids(child))
    return ids


def node_locations(node: dict, chunk_map: dict, max_snippet: int = 240) -> list[dict]:
    out = []
    seen = set()
    for cid in collect_chunk_ids(node):
        if cid in seen:
            continue
        seen.add(cid)
        chunk = chunk_map.get(cid)
        if not chunk:
            continue
        out.append(
            {
                "section_id": node["id"],
                "title_path": node.get("path", node["title"]),
                "chunk_id": cid,
                "snippet": (chunk.content or "").strip()[:max_snippet],
            }
        )
    return out


def compute_neighbors(graph: dict, start_id: str, top_k: int = 8) -> list[dict]:
    """BFS 1–2 跳邻居，按 ``weight * decay(hop)`` 降序返回。

    decay(1)=1.0, decay(2)=0.5（每多一跳再乘 0.5）。
    """
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    if start_id not in nodes:
        return []
    adj: dict[str, list[tuple[str, str, int | float]]] = defaultdict(list)
    for edge in graph.get("edges", []):
        weight = edge.get("weight", 1)
        adj[edge["source"]].append((edge["target"], edge.get("type", "related"), weight))
        adj[edge["target"]].append((edge["source"], edge.get("type", "related"), weight))

    best: dict[str, tuple[float, str]] = {}
    queue: deque[tuple[str, float, str]] = deque([(start_id, 0.0, "sub")])
    while queue:
        current, score, rel = queue.popleft()
        for neighbor, rtype, weight in adj.get(current, []):
            if neighbor == start_id:
                continue
            cand = weight * 1.0 if current == start_id else score * 0.5
            if neighbor not in best or cand > best[neighbor][0]:
                best[neighbor] = (cand, rtype)
                queue.append((neighbor, cand, rtype))

    ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)[:top_k]
    return [
        {
            "id": nid,
            "name": nodes[nid]["name"],
            "weight": round(score, 2),
            "relation": rel,
        }
        for nid, (score, rel) in ranked
    ]


def subgraph(graph: dict, section_id: str) -> dict:
    """返回围绕 ``section_id`` 的 1 跳子图（含自身与直接邻居）。"""
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    if section_id not in nodes_by_id:
        return {"nodes": [], "edges": []}
    keep = {section_id}
    for edge in graph.get("edges", []):
        if edge["source"] == section_id:
            keep.add(edge["target"])
        if edge["target"] == section_id:
            keep.add(edge["source"])
    nodes = [n for n in graph.get("nodes", []) if n["id"] in keep]
    edges = [e for e in graph.get("edges", []) if e["source"] in keep and e["target"] in keep]
    return {"nodes": nodes, "edges": edges}
