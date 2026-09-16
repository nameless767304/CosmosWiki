# 파일명: backend/app/database.py
import json
import logging
import os
import sqlite3
import uuid
from contextlib import contextmanager

from app.config import (
    LOCAL_DB_PATH,
    SIMILARITY_THRESHOLD,
    TOP_K_RELATIONS
)

# Initialize logger
logger = logging.getLogger("cosmos_wiki")

SCHEMA_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS knowledge_nodes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata TEXT,
    embedding TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_links (
    id TEXT PRIMARY KEY,
    source_node_id TEXT,
    target_node_id TEXT,
    similarity REAL NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_source_target UNIQUE (source_node_id, target_node_id),
    FOREIGN KEY (source_node_id) REFERENCES knowledge_nodes (id) ON DELETE CASCADE,
    FOREIGN KEY (target_node_id) REFERENCES knowledge_nodes (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_knowledge_links_source ON knowledge_links (source_node_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_links_target ON knowledge_links (target_node_id);

CREATE TABLE IF NOT EXISTS project_global_summaries (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'user',
    architecture_summary TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_blueprints (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_blueprints_path ON project_blueprints (path);

CREATE TABLE IF NOT EXISTS blueprint_functions (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    function_name TEXT NOT NULL,
    signature TEXT NOT NULL,
    summary TEXT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES project_blueprints (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_functions_file_id ON blueprint_functions (file_id);

CREATE TABLE IF NOT EXISTS blueprint_relationships (
    id TEXT PRIMARY KEY,
    relation_type TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_relationships_source_lookup ON blueprint_relationships (source_node_id, source_type);
CREATE INDEX IF NOT EXISTS idx_relationships_target_lookup ON blueprint_relationships (target_node_id, target_type);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    message TEXT NOT NULL,
    active_mode TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_lookup ON chat_sessions (session_id, created_at);

CREATE TABLE IF NOT EXISTS project_source_codes (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL UNIQUE,
    raw_code TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (file_id) REFERENCES project_blueprints (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_source_codes_file_id ON project_source_codes (file_id);
"""


class QueryResult:
    """Lightweight response wrapper mirroring the .data access pattern callers rely on."""

    __slots__ = ("data",)

    def __init__(self, data):
        self.data = data


def get_connection() -> sqlite3.Connection:
    """Open a new SQLite connection with FK enforcement enabled."""
    conn = sqlite3.connect(LOCAL_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


@contextmanager
def db_cursor(commit: bool = False):
    """Context manager yielding a cursor on a fresh connection; closes on exit."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    finally:
        conn.close()


def initialize_database():
    """Create the schema (8 tables + indices) if it does not already exist."""
    os.makedirs(os.path.dirname(LOCAL_DB_PATH), exist_ok=True)
    conn = get_connection()
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.executescript(SCHEMA_DDL)
        conn.commit()
        logger.info(f"SQLite schema initialized at: {LOCAL_DB_PATH}")
    finally:
        conn.close()


initialize_database()

# ----------------------------------------------------------------
# Knowledge graph management
# ----------------------------------------------------------------

def insert_wiki_node(title: str, content: str, embedding: list, created_by: str):
    """Insert wiki node."""
    node_id = str(uuid.uuid4())
    metadata = {
        "architecture": "modular_graph_v1",
        "created_by": created_by
    }
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO knowledge_nodes (id, title, content, metadata, embedding)
            VALUES (?, ?, ?, ?, ?)
            """,
            (node_id, title, content, json.dumps(metadata), json.dumps(embedding))
        )
    return QueryResult([{
        "id": node_id,
        "title": title,
        "content": content,
        "metadata": metadata,
        "embedding": embedding
    }])

def fetch_all_wiki_nodes():
    """Fetch all wiki nodes."""
    with db_cursor() as cur:
        rows = cur.execute(
            "SELECT id, title, content, embedding FROM knowledge_nodes"
        ).fetchall()
    return [dict(r) for r in rows]

def insert_knowledge_link(source_id: str, target_id: str, similarity: float):
    """Insert knowledge link."""
    link_id = str(uuid.uuid4())
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                """
                INSERT INTO knowledge_links (id, source_node_id, target_node_id, similarity)
                VALUES (?, ?, ?, ?)
                """,
                (link_id, source_id, target_id, similarity)
            )
        return QueryResult([{
            "id": link_id,
            "source_node_id": source_id,
            "target_node_id": target_id,
            "similarity": similarity
        }])
    except Exception as e:
        logger.warning(f"Failed to insert knowledge link: {e}")
        return None

def delete_knowledge_links_by_node(node_id: str):
    """Delete knowledge links by node ID."""
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM knowledge_links WHERE source_node_id = ?", (node_id,))
        cur.execute("DELETE FROM knowledge_links WHERE target_node_id = ?", (node_id,))

def update_wiki_node(node_id: str, title: str, content: str, embedding: list):
    """Update wiki node."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            UPDATE knowledge_nodes
            SET title = ?, content = ?, embedding = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (title, content, json.dumps(embedding), node_id)
        )
    return QueryResult([{
        "id": node_id,
        "title": title,
        "content": content,
        "embedding": embedding
    }])

def delete_wiki_node(node_id: str):
    """Delete wiki node and its links."""
    delete_knowledge_links_by_node(node_id)
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM knowledge_nodes WHERE id = ?", (node_id,))
    return QueryResult([{"id": node_id}])

def fetch_associated_graph_links(node_id: str):
    """Fetch associated links for a node."""
    try:
        logger.debug(f"Fetching links for node_id: {node_id}")
        with db_cursor() as cur:
            rows = cur.execute(
                """
                SELECT kl.target_node_id AS target_node_id,
                       kl.similarity AS similarity,
                       kn.title AS title
                FROM knowledge_links kl
                JOIN knowledge_nodes kn ON kn.id = kl.target_node_id
                WHERE kl.source_node_id = ?
                ORDER BY kl.similarity DESC
                LIMIT 3
                """,
                (node_id,)
            ).fetchall()

        refined_links = []
        for row in rows:
            raw_similarity = (row["similarity"] or 0) * 100
            formatted_similarity = f"{raw_similarity:.1f}"

            refined_links.append({
                "id": row["target_node_id"],
                "title": row["title"] or "Unknown Node",
                "similarity": formatted_similarity
            })
        logger.debug(f"Fetched {len(refined_links)} links")
        return refined_links
    except Exception as e:
        logger.error(f"Error fetching links for node_id {node_id}: {e}", exc_info=True)
        raise e

def fetch_gemini_wiki_nodes():
    """Fetch wiki nodes created by Gemini agent."""
    with db_cursor() as cur:
        rows = cur.execute(
            """
            SELECT id, title, content, created_at, metadata
            FROM knowledge_nodes
            WHERE json_extract(metadata, '$.created_by') IN ('gemini_agent', 'chat_hover_button')
            ORDER BY created_at DESC
            """
        ).fetchall()
    return QueryResult([dict(r) for r in rows])

def fetch_all_wiki_nodes_listing():
    """Fetch wiki node listing (id, title, content, created_at), newest first."""
    with db_cursor() as cur:
        rows = cur.execute(
            "SELECT id, title, content, created_at FROM knowledge_nodes ORDER BY created_at DESC"
        ).fetchall()
    return QueryResult([dict(r) for r in rows])

def insert_chat_message(session_id: str, role: str, message: str, active_mode: str):
    """Insert chat message."""
    message_id = str(uuid.uuid4())
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO chat_sessions (id, session_id, role, message, active_mode)
            VALUES (?, ?, ?, ?, ?)
            """,
            (message_id, session_id, role, message, active_mode)
        )
    return QueryResult([{
        "id": message_id,
        "session_id": session_id,
        "role": role,
        "message": message,
        "active_mode": active_mode
    }])

def fetch_chat_history(session_id: str, window_size: int = 20):
    """Fetch chat history for a session."""
    with db_cursor() as cur:
        rows = cur.execute(
            """
            SELECT role, message
            FROM chat_sessions
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (session_id, window_size * 2)
        ).fetchall()
    return list(reversed([dict(r) for r in rows]))

def fetch_project_global_summary(user_id: str = "user"):
    """Fetch project global summary."""
    with db_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM project_global_summaries WHERE user_id = ? LIMIT 1",
            (user_id,)
        ).fetchone()
    return dict(row) if row else None

def fetch_granular_blueprint_metadata():
    """Fetch blueprint metadata."""
    with db_cursor() as cur:
        blueprints = [dict(r) for r in cur.execute("SELECT * FROM project_blueprints").fetchall()]
        functions = [dict(r) for r in cur.execute("SELECT * FROM blueprint_functions").fetchall()]
        relationships = [dict(r) for r in cur.execute("SELECT * FROM blueprint_relationships").fetchall()]

    return {
        "blueprints": blueprints,
        "functions": functions,
        "relationships": relationships
    }

def fetch_direct_dependencies_metadata(file_id: str) -> dict:
    """Fetch direct dependencies for a file."""
    try:
        with db_cursor() as cur:
            relations = [dict(r) for r in cur.execute(
                """
                SELECT target_node_id, relation_type
                FROM blueprint_relationships
                WHERE source_node_id = ? AND relation_type IN ('imports', 'api_call', 'dependency')
                """,
                (file_id,)
            ).fetchall()]

            if not relations:
                return {"blueprints": [], "functions": []}

            target_ids = [r["target_node_id"] for r in relations]
            placeholders = ",".join("?" * len(target_ids))

            blueprints = [dict(r) for r in cur.execute(
                f"""
                SELECT id, path, summary, type, updated_at AS created_at
                FROM project_blueprints
                WHERE id IN ({placeholders})
                """,
                target_ids
            ).fetchall()]

            functions = [dict(r) for r in cur.execute(
                f"""
                SELECT file_id, function_name, signature, summary
                FROM blueprint_functions
                WHERE file_id IN ({placeholders})
                """,
                target_ids
            ).fetchall()]

        return {
            "blueprints": blueprints,
            "functions": functions,
            "relations": relations
        }
    except Exception as e:
        logger.error(f"Failed to fetch dependencies for file_id {file_id}: {e}")
        return {"blueprints": [], "functions": [], "relations": []}

def update_blueprint_metadata_text(node_id: str, type: str, new_summary: str):
    """Update blueprint summary."""
    table_name = "project_blueprints" if type == "file" else "blueprint_functions"
    with db_cursor(commit=True) as cur:
        cur.execute(
            f"UPDATE {table_name} SET summary = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (new_summary, node_id)
        )
    return QueryResult([{"id": node_id, "summary": new_summary}])

def upsert_project_source_code(file_id: str, raw_code: str):
    """Upsert project source code."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO project_source_codes (id, file_id, raw_code)
            VALUES (?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                raw_code = excluded.raw_code,
                updated_at = CURRENT_TIMESTAMP
            """,
            (str(uuid.uuid4()), file_id, raw_code)
        )
    return QueryResult([{"file_id": file_id, "raw_code": raw_code}])

def fetch_project_source_code(file_id: str):
    """Fetch project source code."""
    with db_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM project_source_codes WHERE file_id = ? LIMIT 1",
            (file_id,)
        ).fetchone()
    return dict(row) if row else None

def fetch_blueprint_by_id(file_id: str):
    """Fetch blueprint by ID."""
    with db_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM project_blueprints WHERE id = ? LIMIT 1",
            (file_id,)
        ).fetchone()
    return dict(row) if row else None

def delete_blueprint_functions_by_file(file_id: str):
    """Delete blueprint functions by file ID."""
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM blueprint_functions WHERE file_id = ?", (file_id,))

def delete_blueprint_relationships_by_source(source_id: str):
    """Delete blueprint relationships by source ID."""
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM blueprint_relationships WHERE source_node_id = ?", (source_id,))

def fetch_all_blueprints_basic():
    """Fetch all blueprints basic info."""
    with db_cursor() as cur:
        rows = cur.execute("SELECT id, path FROM project_blueprints").fetchall()
    return [dict(r) for r in rows]

def insert_blueprint_relationship(relation_type: str, source_id: str, source_type: str, target_id: str, target_type: str):
    """Insert blueprint relationship."""
    relationship_id = str(uuid.uuid4())
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO blueprint_relationships
                (id, relation_type, source_node_id, source_type, target_node_id, target_type)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (relationship_id, relation_type, source_id, source_type, target_id, target_type)
        )
    return QueryResult([{
        "id": relationship_id,
        "relation_type": relation_type,
        "source_node_id": source_id,
        "source_type": source_type,
        "target_node_id": target_id,
        "target_type": target_type
    }])

def insert_blueprint_function(file_id: str, function_name: str, signature: str, summary: str):
    """Insert a blueprint function entry."""
    function_id = str(uuid.uuid4())
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO blueprint_functions (id, file_id, function_name, signature, summary)
            VALUES (?, ?, ?, ?, ?)
            """,
            (function_id, file_id, function_name, signature, summary)
        )
    return QueryResult([{
        "id": function_id,
        "file_id": file_id,
        "function_name": function_name,
        "signature": signature,
        "summary": summary
    }])

def fetch_blueprint_id_by_path(path: str):
    """Fetch a blueprint's ID by its file path."""
    with db_cursor() as cur:
        row = cur.execute(
            "SELECT id FROM project_blueprints WHERE path = ? LIMIT 1",
            (path,)
        ).fetchone()
    return row["id"] if row else None

def upsert_project_blueprint(blueprint_id: str, type: str, path: str, summary: str):
    """Upsert project blueprint, matching by ID."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO project_blueprints (id, type, path, summary)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type = excluded.type,
                path = excluded.path,
                summary = excluded.summary,
                updated_at = CURRENT_TIMESTAMP
            """,
            (blueprint_id, type, path, summary)
        )
    return QueryResult([{"id": blueprint_id, "type": type, "path": path, "summary": summary}])

def delete_blueprint_cascade(blueprint_id: str):
    """Delete a blueprint and its relationships, functions, and source code."""
    with db_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM blueprint_relationships WHERE source_node_id = ? OR target_node_id = ?",
            (blueprint_id, blueprint_id)
        )
        # FK cascades remove blueprint_functions and project_source_codes rows.
        cur.execute("DELETE FROM project_blueprints WHERE id = ?", (blueprint_id,))

def fetch_raw_links_by_source(node_id: str) -> list:
    """Fetch raw links by source node ID."""
    try:
        with db_cursor() as cur:
            rows = cur.execute(
                "SELECT target_node_id, similarity FROM knowledge_links WHERE source_node_id = ?",
                (node_id,)
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Failed to fetch raw links for node_id {node_id}: {e}")
        return []

def delete_specific_edge_bidirectional(node_a: str, node_b: str):
    """Delete bidirectional edge between two nodes."""
    try:
        with db_cursor(commit=True) as cur:
            cur.execute(
                "DELETE FROM knowledge_links WHERE source_node_id = ? AND target_node_id = ?",
                (node_a, node_b)
            )
            cur.execute(
                "DELETE FROM knowledge_links WHERE source_node_id = ? AND target_node_id = ?",
                (node_b, node_a)
            )
    except Exception as e:
        logger.error(f"Failed to delete bidirectional edge between {node_a} and {node_b}: {e}")

def prune_node_edges_if_needed(node_id: str):
    """Prune low similarity edges if limit exceeded."""
    current_links = fetch_raw_links_by_source(node_id)
    if len(current_links) > TOP_K_RELATIONS:
        current_links.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        prune_targets = current_links[TOP_K_RELATIONS:]
        for edge in prune_targets:
            target_id = edge["target_node_id"]
            logger.info(f"Edge count exceeded limit. Pruning edges for node_id: {node_id}")
            delete_specific_edge_bidirectional(node_id, target_id)

def sync_node_graph_relations(node_id: str, current_vector: list) -> int:
    """Sync node graph relations."""
    # Import internally to avoid circular dependency
    from app.gemini import compute_cosine_similarity

    # Clear existing links
    delete_knowledge_links_by_node(node_id)

    # Compute similarity for all nodes
    all_nodes = fetch_all_wiki_nodes()
    if not all_nodes or len(all_nodes) <= 1:
        return 0

    link_candidates = []
    for node in all_nodes:
        target_id = node.get("id")
        if target_id == node_id:
            continue

        target_vector = node.get("embedding")
        if isinstance(target_vector, str):
            try: target_vector = json.loads(target_vector)
            except Exception:
                continue

        if target_vector and len(target_vector) == 3072:
            current_sim = compute_cosine_similarity(current_vector, target_vector)
            if current_sim >= SIMILARITY_THRESHOLD:
                link_candidates.append({"target_id": target_id, "similarity": current_sim})

    # Extract top-K links
    link_candidates.sort(key=lambda x: x["similarity"], reverse=True)
    top_k_links = link_candidates[:TOP_K_RELATIONS]

    links_created = 0
    for c in top_k_links:
        links_created += 1
        insert_knowledge_link(node_id, c["target_id"], c["similarity"])
        insert_knowledge_link(c["target_id"], node_id, c["similarity"])

        # Prune edges if needed
        prune_node_edges_if_needed(c["target_id"])

    return links_created
