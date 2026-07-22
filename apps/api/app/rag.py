from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from typing import Any

from . import db


CHUNKER = {
    "name": "markdown-paragraph-v1",
    "max_chars": 700,
    "overlap_chars": 80,
}
KEYWORD_ENGINE = "sqlite-fts5-bm25"
EMBEDDING_MODEL = "local-tfidf-lsa-v1"
FUSION = {"name": "weighted-rrf", "rrf_k": 60, "keyword_weight": 0.5, "vector_weight": 0.5}
TOKEN_RE = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9][a-zA-Z0-9_.-]*")


def tokenize(text: str) -> list[str]:
    """Tokenize without hidden models: CJK bigrams plus lower-cased word tokens."""
    tokens: list[str] = []
    for match in TOKEN_RE.finditer(text.lower()):
        value = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", value):
            if len(value) == 1:
                tokens.append(value)
            else:
                tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
        else:
            tokens.append(value)
    return tokens


def _split_long_block(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = [item.strip() for item in re.split(r"(?<=[。！？；.!?;])\s*", text) if item.strip()]
    if len(sentences) <= 1:
        return [text[index : index + max_chars] for index in range(0, len(text), max_chars)]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            pieces.append(current)
            current = ""
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                sentence[index : index + max_chars]
                for index in range(0, len(sentence), max_chars)
            )
        else:
            current += sentence
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(content: str) -> list[dict[str, Any]]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    heading = "正文"
    blocks: list[tuple[str, str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        if paragraph:
            blocks.append((heading, "\n".join(paragraph).strip()))
            paragraph.clear()

    for line in normalized.split("\n"):
        stripped = line.strip()
        match = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if match:
            flush()
            heading = match.group(1).strip()[:160]
        elif not stripped:
            flush()
        else:
            paragraph.append(stripped)
    flush()

    expanded: list[tuple[str, str]] = []
    for block_heading, block in blocks:
        for piece in _split_long_block(block, CHUNKER["max_chars"] - len(block_heading) - 8):
            expanded.append((block_heading, piece))

    chunks: list[dict[str, Any]] = []
    current_heading = ""
    current_parts: list[str] = []
    for block_heading, block in expanded:
        candidate_parts = current_parts + [block]
        candidate = f"# {block_heading}\n" + "\n\n".join(candidate_parts)
        if current_parts and (block_heading != current_heading or len(candidate) > CHUNKER["max_chars"]):
            rendered = f"# {current_heading}\n" + "\n\n".join(current_parts)
            chunks.append({"heading": current_heading, "content": rendered})
            overlap = rendered[-CHUNKER["overlap_chars"] :].strip()
            current_parts = ([f"上文续接：{overlap}"] if overlap else []) + [block]
            current_heading = block_heading
        else:
            current_heading = block_heading
            current_parts = candidate_parts
    if current_parts:
        rendered = f"# {current_heading}\n" + "\n\n".join(current_parts)
        chunks.append({"heading": current_heading, "content": rendered})
    for index, chunk in enumerate(chunks):
        chunk["ordinal"] = index
        chunk["char_count"] = len(chunk["content"])
        chunk["search_text"] = " ".join(tokenize(chunk["content"]))
        chunk["content_hash"] = hashlib.sha256(chunk["content"].encode("utf-8")).hexdigest()
    return chunks


def preview_document(content: str) -> dict[str, Any]:
    chunks = chunk_markdown(content)
    return {
        "chunks": chunks,
        "chunk_count": len(chunks),
        "original_char_count": len(content),
        "chunker": CHUNKER,
        "keyword_engine": KEYWORD_ENGINE,
        "embedding_model": EMBEDDING_MODEL,
        "fusion": FUSION,
    }


def _tfidf_documents(token_lists: list[list[str]]) -> tuple[list[dict[str, float]], dict[str, float]]:
    count = len(token_lists)
    document_frequency: Counter[str] = Counter()
    for tokens in token_lists:
        document_frequency.update(set(tokens))
    idf = {
        term: math.log((1.0 + count) / (1.0 + frequency)) + 1.0
        for term, frequency in document_frequency.items()
    }
    vectors: list[dict[str, float]] = []
    for tokens in token_lists:
        frequencies = Counter(tokens)
        vector = {
            term: (1.0 + math.log(frequency)) * idf[term]
            for term, frequency in frequencies.items()
        }
        norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
        vectors.append({term: value / norm for term, value in vector.items()})
    return vectors, idf


def _dot(left: dict[str, float], right: dict[str, float]) -> float:
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(term, 0.0) for term, value in left.items())


def _top_eigenpairs(matrix: list[list[float]], dimensions: int) -> list[tuple[float, list[float]]]:
    size = len(matrix)
    if size == 0:
        return []
    pairs: list[tuple[float, list[float]]] = []
    for component in range(min(dimensions, size)):
        vector = [
            math.sin((index + 1) * (component + 1) * 0.73)
            + math.cos((index + 1) * (component + 2) * 0.31)
            for index in range(size)
        ]
        for prior_value, prior in pairs:
            if prior_value <= 1e-10:
                continue
            projection = sum(vector[index] * prior[index] for index in range(size))
            vector = [vector[index] - projection * prior[index] for index in range(size)]
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        vector = [value / norm for value in vector]
        for _ in range(120):
            next_vector = [sum(matrix[row][col] * vector[col] for col in range(size)) for row in range(size)]
            for prior_value, prior in pairs:
                if prior_value <= 1e-10:
                    continue
                projection = sum(next_vector[index] * prior[index] for index in range(size))
                next_vector = [next_vector[index] - projection * prior[index] for index in range(size)]
            norm = math.sqrt(sum(value * value for value in next_vector))
            if norm <= 1e-12:
                break
            next_vector = [value / norm for value in next_vector]
            delta = math.sqrt(sum((next_vector[index] - vector[index]) ** 2 for index in range(size)))
            vector = next_vector
            if delta < 1e-10:
                break
        multiplied = [sum(matrix[row][col] * vector[col] for col in range(size)) for row in range(size)]
        eigenvalue = max(0.0, sum(vector[index] * multiplied[index] for index in range(size)))
        if eigenvalue <= 1e-10:
            break
        pairs.append((eigenvalue, vector))
    return pairs


def fit_lsa(chunks: list[dict[str, Any]], dimensions: int = 8) -> dict[str, Any]:
    token_lists = [tokenize(chunk["content"]) for chunk in chunks]
    documents, idf = _tfidf_documents(token_lists)
    gram = [[_dot(left, right) for right in documents] for left in documents]
    pairs = _top_eigenpairs(gram, dimensions)
    eigenvectors = [vector for _value, vector in pairs]
    singular_values = [math.sqrt(value) for value, _vector in pairs]
    coordinates = [
        [singular_values[axis] * eigenvectors[axis][doc_index] for axis in range(len(pairs))]
        for doc_index in range(len(documents))
    ]
    return {
        "model": EMBEDDING_MODEL,
        "dimensions": len(pairs),
        "idf": idf,
        "eigenvectors": eigenvectors,
        "singular_values": singular_values,
        "document_coordinates": coordinates,
        "training_chunk_count": len(chunks),
    }


def _query_coordinates(query: str, chunks: list[dict[str, Any]], model: dict[str, Any]) -> list[float]:
    idf = {str(key): float(value) for key, value in model["idf"].items()}
    frequencies = Counter(token for token in tokenize(query) if token in idf)
    if not frequencies:
        return []
    query_vector = {
        term: (1.0 + math.log(frequency)) * idf[term]
        for term, frequency in frequencies.items()
    }
    norm = math.sqrt(sum(value * value for value in query_vector.values())) or 1.0
    query_vector = {term: value / norm for term, value in query_vector.items()}
    documents, _unused = _tfidf_documents([tokenize(chunk["content"]) for chunk in chunks])
    coordinates: list[float] = []
    for axis, singular in enumerate(model["singular_values"]):
        eigenvector = model["eigenvectors"][axis]
        numerator = sum(_dot(query_vector, documents[index]) * eigenvector[index] for index in range(len(documents)))
        coordinates.append(numerator / float(singular) if float(singular) > 1e-12 else 0.0)
    return coordinates


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    denominator = math.sqrt(sum(value * value for value in left)) * math.sqrt(sum(value * value for value in right))
    if denominator <= 1e-12:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / denominator


def _validation_errors(payload: dict[str, Any], preview: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    name = str(payload.get("name", "")).strip()
    content = str(payload.get("content", "")).strip()
    version_note = str(payload.get("version_note", "")).strip()
    tags = payload.get("tags")
    if not name or len(name) > 100:
        errors.append("name 必须为 1-100 个字符")
    if len(content) < 500 or len(content) > 100_000:
        errors.append("content 必须为 500-100000 个字符的纯文本或 Markdown")
    if not version_note or len(version_note) > 300:
        errors.append("version_note 必须为 1-300 个字符")
    if not isinstance(tags, list) or not tags or len(tags) > 12:
        errors.append("tags 必须包含 1-12 个标签")
    elif any(not isinstance(item, str) or not item.strip() or len(item) > 30 for item in tags):
        errors.append("每个标签必须为 1-30 个字符")
    if not preview["chunks"]:
        errors.append("切片结果不能为空")
    return errors


def save_document(payload: dict[str, Any], document_id: str | None = None) -> dict[str, Any]:
    content = str(payload.get("content", "")).replace("\x00", "").strip()
    values = {
        "name": str(payload.get("name", "")).strip(),
        "content": content,
        "tags": list(dict.fromkeys(str(item).strip() for item in payload.get("tags", []) if str(item).strip())),
        "version_note": str(payload.get("version_note", "")).strip(),
    }
    preview = preview_document(content)
    errors = _validation_errors(values, preview)
    model = fit_lsa(preview["chunks"])
    timestamp = db.now_iso()
    with db.connection() as conn:
        if document_id is None:
            document_id = db.new_id("ragdoc")
            version_number = 1
            created_at = timestamp
            legacy_agent_ids: list[str] = []
        else:
            current = conn.execute("SELECT * FROM rag_documents WHERE id=?", (document_id,)).fetchone()
            if current is None:
                raise KeyError(document_id)
            version_number = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 AS n FROM rag_versions WHERE document_id=?",
                (document_id,),
            ).fetchone()["n"]
            created_at = current["created_at"]
            legacy_agent_ids = json.loads(current["agent_ids_json"])
        version_id = db.new_id("ragv")
        original_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if version_number == 1:
            conn.execute(
                """
                INSERT INTO rag_documents(
                    id, name, tags_json, status, current_version_id, agent_ids_json,
                    validation_errors_json, created_at, updated_at
                ) VALUES(?, ?, ?, 'DRAFT', ?, ?, ?, ?, ?)
                """,
                (
                    document_id, values["name"], json.dumps(values["tags"], ensure_ascii=False),
                    version_id, json.dumps(legacy_agent_ids, ensure_ascii=False),
                    json.dumps(errors, ensure_ascii=False), created_at, timestamp,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE rag_documents SET name=?, tags_json=?, status='DRAFT', current_version_id=?,
                    agent_ids_json=?, validation_errors_json=?, updated_at=? WHERE id=?
                """,
                (
                    values["name"], json.dumps(values["tags"], ensure_ascii=False), version_id,
                    json.dumps(legacy_agent_ids, ensure_ascii=False),
                    json.dumps(errors, ensure_ascii=False), timestamp, document_id,
                ),
            )
        conn.execute(
            """
            INSERT INTO rag_versions(
                id, document_id, version_number, original_content, original_content_hash,
                version_note, chunker_json, keyword_engine, embedding_model, fusion_json,
                model_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version_id, document_id, version_number, content, original_hash,
                values["version_note"], json.dumps(CHUNKER, ensure_ascii=False), KEYWORD_ENGINE,
                EMBEDDING_MODEL, json.dumps(FUSION, ensure_ascii=False),
                json.dumps(model, ensure_ascii=False), timestamp,
            ),
        )
        for index, chunk in enumerate(preview["chunks"]):
            chunk_id = db.new_id("ragchunk")
            vector = model["document_coordinates"][index] if index < len(model["document_coordinates"]) else []
            conn.execute(
                """
                INSERT INTO rag_chunks(
                    id, rag_version_id, ordinal, heading, content, search_text,
                    vector_json, char_count, content_hash
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id, version_id, chunk["ordinal"], chunk["heading"], chunk["content"],
                    chunk["search_text"], json.dumps(vector), chunk["char_count"], chunk["content_hash"],
                ),
            )
            conn.execute(
                "INSERT INTO rag_chunks_fts(chunk_id, content) VALUES(?, ?)",
                (chunk_id, chunk["search_text"]),
            )
    return get_document(document_id)


def _version_dict(conn, version_id: str) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM rag_versions WHERE id=?", (version_id,)).fetchone()
    if row is None:
        raise KeyError(version_id)
    result = dict(row)
    for source, target in (("chunker_json", "chunker"), ("fusion_json", "fusion"), ("model_json", "model")):
        result[target] = json.loads(result.pop(source))
    result["chunks"] = []
    for chunk in conn.execute("SELECT * FROM rag_chunks WHERE rag_version_id=? ORDER BY ordinal", (version_id,)).fetchall():
        item = dict(chunk)
        item["vector"] = json.loads(item.pop("vector_json"))
        item.pop("search_text", None)
        result["chunks"].append(item)
    return result


def get_document(document_id: str) -> dict[str, Any]:
    with db.connection() as conn:
        row = conn.execute("SELECT * FROM rag_documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise KeyError(document_id)
        result = dict(row)
        result["tags"] = json.loads(result.pop("tags_json"))
        result["legacy_agent_ids"] = json.loads(result.pop("agent_ids_json"))
        result["bound_agent_ids"] = db.bound_agent_ids(conn, "RAG", document_id)
        result["agent_ids"] = list(result["bound_agent_ids"])
        result["validation_errors"] = json.loads(result.pop("validation_errors_json"))
        result["current_version"] = _version_dict(conn, result["current_version_id"])
        result["versions"] = [
            dict(item)
            for item in conn.execute(
                "SELECT id, version_number, original_content_hash, version_note, created_at FROM rag_versions WHERE document_id=? ORDER BY version_number DESC",
                (document_id,),
            ).fetchall()
        ]
        return result


def list_documents() -> list[dict[str, Any]]:
    with db.connection() as conn:
        ids = [row["id"] for row in conn.execute("SELECT id FROM rag_documents ORDER BY created_at DESC").fetchall()]
    return [get_document(document_id) for document_id in ids]


def validate_document(document_id: str) -> dict[str, Any]:
    document = get_document(document_id)
    version = document["current_version"]
    payload = {
        "name": document["name"], "content": version["original_content"],
        "tags": document["tags"], "version_note": version["version_note"],
    }
    errors = _validation_errors(payload, preview_document(version["original_content"]))
    with db.connection() as conn:
        conn.execute(
            "UPDATE rag_documents SET status=?, validation_errors_json=?, updated_at=? WHERE id=?",
            ("VALIDATED" if not errors else "DRAFT", json.dumps(errors, ensure_ascii=False), db.now_iso(), document_id),
        )
    return get_document(document_id)


def disable_document(document_id: str) -> dict[str, Any]:
    with db.connection() as conn:
        if conn.execute("SELECT 1 FROM rag_documents WHERE id=?", (document_id,)).fetchone() is None:
            raise KeyError(document_id)
        conn.execute("UPDATE rag_documents SET status='DISABLED', updated_at=? WHERE id=?", (db.now_iso(), document_id))
    return get_document(document_id)


def retrieve(version_id: str, query: str, limit: int = 5) -> dict[str, Any]:
    with db.connection() as conn:
        version = _version_dict(conn, version_id)
        rows = conn.execute(
            "SELECT id, ordinal, heading, content, search_text, vector_json, char_count, content_hash FROM rag_chunks WHERE rag_version_id=? ORDER BY ordinal",
            (version_id,),
        ).fetchall()
        chunks = [dict(row) for row in rows]
        tokens = list(dict.fromkeys(tokenize(query)))
        keyword_raw: dict[str, float] = {}
        if tokens:
            expression = " OR ".join(f'"{token}"' for token in tokens[:80])
            matches = conn.execute(
                "SELECT chunk_id, bm25(rag_chunks_fts) AS score FROM rag_chunks_fts WHERE rag_chunks_fts MATCH ? ORDER BY score LIMIT 200",
                (expression,),
            ).fetchall()
            allowed = {chunk["id"] for chunk in chunks}
            keyword_raw = {row["chunk_id"]: -float(row["score"]) for row in matches if row["chunk_id"] in allowed}

    model = version["model"]
    query_coordinates = _query_coordinates(query, chunks, model)
    vector_scores = {
        chunk["id"]: max(-1.0, min(1.0, _cosine(query_coordinates, json.loads(chunk["vector_json"]))))
        for chunk in chunks
    } if query_coordinates else {}
    keyword_ranked = sorted(keyword_raw, key=lambda item: keyword_raw[item], reverse=True)
    vector_ranked = sorted(
        (item for item, score in vector_scores.items() if score > 0.02),
        key=lambda item: vector_scores[item],
        reverse=True,
    )
    rank_keyword = {chunk_id: index + 1 for index, chunk_id in enumerate(keyword_ranked)}
    rank_vector = {chunk_id: index + 1 for index, chunk_id in enumerate(vector_ranked)}
    hybrid_scores: dict[str, float] = {}
    for chunk_id in set(rank_keyword) | set(rank_vector):
        score = 0.0
        if chunk_id in rank_keyword:
            score += FUSION["keyword_weight"] / (FUSION["rrf_k"] + rank_keyword[chunk_id])
        if chunk_id in rank_vector:
            score += FUSION["vector_weight"] / (FUSION["rrf_k"] + rank_vector[chunk_id])
        hybrid_scores[chunk_id] = score
    by_id = {chunk["id"]: chunk for chunk in chunks}

    def render(chunk_id: str) -> dict[str, Any]:
        chunk = by_id[chunk_id]
        return {
            "chunk_id": chunk_id,
            "ordinal": chunk["ordinal"],
            "heading": chunk["heading"],
            "content": chunk["content"],
            "char_count": chunk["char_count"],
            "content_hash": chunk["content_hash"],
            "keyword_score": keyword_raw.get(chunk_id),
            "keyword_rank": rank_keyword.get(chunk_id),
            "vector_score": vector_scores.get(chunk_id),
            "vector_rank": rank_vector.get(chunk_id),
            "hybrid_score": hybrid_scores.get(chunk_id),
            "citation": f"[RAG:{version['document_id']}#{chunk_id}]",
        }

    hybrid_ranked = sorted(hybrid_scores, key=lambda item: hybrid_scores[item], reverse=True)
    return {
        "query": query,
        "rag_version_id": version_id,
        "document_id": version["document_id"],
        "technology": {"keyword_engine": KEYWORD_ENGINE, "embedding_model": EMBEDDING_MODEL, "fusion": FUSION},
        "keyword_results": [render(item) for item in keyword_ranked[:limit]],
        "vector_results": [render(item) for item in vector_ranked[:limit]],
        "hybrid_results": [render(item) for item in hybrid_ranked[:limit]],
    }


def retrieve_release(config: dict[str, Any], agent_id: str, query: str, limit: int = 4) -> dict[str, Any]:
    released = [item for item in config.get("rag", []) if agent_id in item.get("agent_ids", [])]
    candidates: list[dict[str, Any]] = []
    tests: list[dict[str, Any]] = []
    for binding in released:
        result = retrieve(binding["rag_version_id"], query, limit=limit)
        tests.append({
            "document_id": binding["document_id"],
            "rag_version_id": binding["rag_version_id"],
            "hybrid_result_count": len(result["hybrid_results"]),
        })
        for item in result["hybrid_results"]:
            enriched = dict(item)
            enriched["document_id"] = binding["document_id"]
            enriched["document_name"] = binding["name"]
            enriched["rag_version_id"] = binding["rag_version_id"]
            enriched["citation"] = f"[RAG:{binding['name']}#{item['chunk_id']}]"
            candidates.append(enriched)
    candidates.sort(key=lambda item: float(item.get("hybrid_score") or 0.0), reverse=True)
    evidence = candidates[:limit]
    return {
        "published_binding_count": len(released),
        "tests": tests,
        "evidence": evidence,
        "citations": [item["citation"] for item in evidence],
        "injected_char_count": sum(len(item["content"]) for item in evidence),
        "technology": {"keyword_engine": KEYWORD_ENGINE, "embedding_model": EMBEDDING_MODEL, "fusion": FUSION},
    }


def prompt_context(result: dict[str, Any]) -> str:
    evidence = result.get("evidence", [])
    if not evidence:
        return "\n\n本次没有检索到可用的已发布 RAG 证据。禁止生成任何 RAG 引用。"
    blocks = [f"{item['citation']}\n{item['content']}" for item in evidence]
    return (
        "\n\n以下内容来自本 Release 已发布的 RAG 切片。只可使用每段前给出的完整引用标识，"
        "不得创造、改写或猜测引用；证据不足时要明确说明。\n\n" + "\n\n".join(blocks)
    )


def sanitize_citations(answer: str, allowed: list[str]) -> tuple[str, list[str], list[str]]:
    allowed_set = set(allowed)
    normalized = re.sub(
        r"[\[\(（](RAG:[^\]\)）]+)[\]\)）]",
        lambda match: f"[{match.group(1)}]",
        answer,
    )
    found = re.findall(r"\[RAG:[^\]]+\]", normalized)
    removed = [item for item in found if item not in allowed_set]
    sanitized = re.sub(
        r"\[RAG:[^\]]+\]",
        lambda match: match.group(0) if match.group(0) in allowed_set else "",
        normalized,
    )
    used = list(dict.fromkeys(item for item in found if item in allowed_set))
    return sanitized, used, list(dict.fromkeys(removed))
