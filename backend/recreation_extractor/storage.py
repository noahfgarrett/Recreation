from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .models import DrawingGraph, GraphEdge, GraphNode, Project, ReviewItem, SourceFile, to_dict
from .pid_stitch.models import LayoutOption


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_files (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  name TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  page_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pages (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_file_id TEXT NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  width REAL NOT NULL,
  height REAL NOT NULL,
  text TEXT NOT NULL,
  vector_count INTEGER NOT NULL DEFAULT 0,
  rasterized INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS detections (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  source_file_id TEXT NOT NULL REFERENCES source_files(id) ON DELETE CASCADE,
  page_number INTEGER NOT NULL,
  kind TEXT NOT NULL,
  label TEXT NOT NULL,
  confidence REAL NOT NULL,
  bounds_json TEXT NOT NULL,
  evidence_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_nodes (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS graph_edges (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS review_items (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS drawing_documents (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS layout_options (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  drawing_id TEXT NOT NULL REFERENCES drawing_documents(id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preflight_reviews (
  project_id TEXT PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS hierarchy_templates (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS correction_memory (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  memory_type TEXT NOT NULL,
  key TEXT NOT NULL,
  value_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, memory_type, key)
);

CREATE TABLE IF NOT EXISTS export_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  export_type TEXT NOT NULL,
  path TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class ProjectStore:
    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "projects.sqlite"
        self._init_schema()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
            source_file_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(source_files)")
            }
            if "page_count" not in source_file_columns:
                conn.execute("ALTER TABLE source_files ADD COLUMN page_count INTEGER NOT NULL DEFAULT 0")

    def upsert_project(self, project: Project) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET name = excluded.name, updated_at = excluded.updated_at
                """,
                (project.id, project.name, project.createdAt, project.updatedAt),
            )

    def list_projects(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM projects ORDER BY updated_at DESC")]

    def project_exists(self, project_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone()
        return row is not None

    def add_source_file(self, source: SourceFile) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                DELETE FROM source_files
                WHERE project_id = ? AND path = ? AND id != ?
                """,
                (source.projectId, source.path, source.id),
            )
            conn.execute(
                """
                INSERT OR REPLACE INTO source_files (id, project_id, path, name, sha256, page_count)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (source.id, source.projectId, source.path, source.name, source.sha256, source.pageCount),
            )

    def list_source_files(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    "SELECT * FROM source_files WHERE project_id = ? ORDER BY name",
                    (project_id,),
                )
            ]

    def get_source_file(self, project_id: str, source_file_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM source_files WHERE id = ? AND project_id = ?",
                (source_file_id, project_id),
            ).fetchone()
            return dict(row) if row else None

    def upsert_preflight_review(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO preflight_reviews (project_id, payload_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(project_id) DO UPDATE SET
                  payload_json = excluded.payload_json,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (project_id, json.dumps(payload)),
            )
        return payload

    def get_preflight_review(self, project_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM preflight_reviews WHERE project_id = ?",
                (project_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def list_hierarchy_templates(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id, name, payload_json FROM hierarchy_templates ORDER BY name").fetchall()
        templates: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            payload["id"] = row["id"]
            payload["name"] = row["name"]
            templates.append(payload)
        return templates

    def upsert_hierarchy_template(self, template_id: str, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO hierarchy_templates (id, name, payload_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                  name = excluded.name,
                  payload_json = excluded.payload_json,
                  updated_at = CURRENT_TIMESTAMP
                """,
                (template_id, name, json.dumps(payload)),
            )
        return payload

    def replace_pages(self, project_id: str, pages: list[dict[str, Any]]) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM pages WHERE project_id = ?", (project_id,))
            for page in pages:
                conn.execute(
                    """
                    INSERT INTO pages (
                      id, project_id, source_file_id, page_number, width, height, text, vector_count, rasterized
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        page["id"],
                        project_id,
                        page["sourceFileId"],
                        page["page"],
                        page["width"],
                        page["height"],
                        page["text"],
                        page["vectorCount"],
                        int(page["rasterized"]),
                    ),
                )

    def replace_graph(self, graph: DrawingGraph) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM graph_nodes WHERE project_id = ?", (graph.projectId,))
            conn.execute("DELETE FROM graph_edges WHERE project_id = ?", (graph.projectId,))
            conn.execute("DELETE FROM review_items WHERE project_id = ?", (graph.projectId,))
            for node in graph.nodes:
                conn.execute(
                    "INSERT INTO graph_nodes (id, project_id, payload_json) VALUES (?, ?, ?)",
                    (node.id, graph.projectId, json.dumps(to_dict(node))),
                )
            for edge in graph.edges:
                conn.execute(
                    "INSERT INTO graph_edges (id, project_id, payload_json) VALUES (?, ?, ?)",
                    (edge.id, graph.projectId, json.dumps(to_dict(edge))),
                )
            for item in graph.reviewItems:
                conn.execute(
                    "INSERT INTO review_items (id, project_id, payload_json) VALUES (?, ?, ?)",
                    (item.id, graph.projectId, json.dumps(to_dict(item))),
                )

    def get_graph(self, project_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            nodes = [
                json.loads(row["payload_json"])
                for row in conn.execute("SELECT payload_json FROM graph_nodes WHERE project_id = ?", (project_id,))
            ]
            edges = [
                json.loads(row["payload_json"])
                for row in conn.execute("SELECT payload_json FROM graph_edges WHERE project_id = ?", (project_id,))
            ]
            review = [
                json.loads(row["payload_json"])
                for row in conn.execute("SELECT payload_json FROM review_items WHERE project_id = ?", (project_id,))
            ]
        return {"projectId": project_id, "nodes": nodes, "edges": edges, "reviewItems": review}

    def replace_drawing_options(self, project_id: str, options: list[LayoutOption]) -> None:
        payloads = [self._drawing_option_payloads(project_id, raw_option) for raw_option in options]
        with self.connect() as conn:
            conn.execute("DELETE FROM layout_options WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM drawing_documents WHERE project_id = ?", (project_id,))
            for option_payload, document_payload in payloads:
                conn.execute(
                    """
                    INSERT INTO drawing_documents (id, project_id, payload_json)
                    VALUES (?, ?, ?)
                    """,
                    (document_payload["id"], project_id, json.dumps(document_payload)),
                )
                conn.execute(
                    """
                    INSERT INTO layout_options (id, project_id, drawing_id, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        option_payload["id"],
                        project_id,
                        option_payload["drawingId"],
                        json.dumps(option_payload),
                    ),
                )

    def list_layout_options(self, project_id: str) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                  layout_options.payload_json AS option_json,
                  drawing_documents.payload_json AS document_json
                FROM layout_options
                JOIN drawing_documents ON drawing_documents.id = layout_options.drawing_id
                WHERE layout_options.project_id = ?
                ORDER BY
                  CASE
                    WHEN json_extract(layout_options.payload_json, '$.metrics.primaryOutput') = 1 THEN 0
                    ELSE 1
                  END,
                  layout_options.id
                """,
                (project_id,),
            ).fetchall()
        options: list[dict[str, Any]] = []
        for row in rows:
            option = json.loads(row["option_json"])
            option.pop("drawingDocument", None)
            option["drawingDocument"] = json.loads(row["document_json"])
            options.append(option)
        return options

    def get_drawing_document(self, project_id: str, drawing_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT payload_json
                FROM drawing_documents
                WHERE id = ? AND project_id = ?
                """,
                (drawing_id, project_id),
            ).fetchone()
        if not row:
            raise KeyError(drawing_id)
        return json.loads(row["payload_json"])

    def update_drawing_document(self, project_id: str, drawing_id: str, document: dict[str, Any]) -> dict[str, Any]:
        persisted = to_dict(document)
        if not isinstance(persisted, dict):
            raise ValueError("Drawing document payload must be a dictionary")
        persisted = dict(persisted)
        persisted.pop("project_id", None)
        persisted["id"] = drawing_id
        persisted["projectId"] = project_id

        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM drawing_documents WHERE id = ? AND project_id = ?",
                (drawing_id, project_id),
            ).fetchone()
            if not row:
                raise KeyError(drawing_id)
            conn.execute(
                """
                UPDATE drawing_documents
                SET payload_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND project_id = ?
                """,
                (json.dumps(persisted), drawing_id, project_id),
            )
        return persisted

    def update_layout(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        graph = self.get_graph(project_id)
        node_updates = {node["id"]: node for node in payload.get("nodes", [])}
        edge_updates = {edge["id"]: edge for edge in payload.get("edges", [])}

        for node in graph["nodes"]:
            update = node_updates.get(node["id"])
            if update:
                node["layout"] = {**node.get("layout", {}), **update.get("layout", {})}
                if "locked" in update:
                    node["locked"] = bool(update["locked"])

        for edge in graph["edges"]:
            update = edge_updates.get(edge["id"])
            if update:
                edge["waypoints"] = update.get("waypoints", edge.get("waypoints", []))

        with self.connect() as conn:
            for node in graph["nodes"]:
                conn.execute(
                    "UPDATE graph_nodes SET payload_json = ? WHERE id = ? AND project_id = ?",
                    (json.dumps(node), node["id"], project_id),
                )
            for edge in graph["edges"]:
                conn.execute(
                    "UPDATE graph_edges SET payload_json = ? WHERE id = ? AND project_id = ?",
                    (json.dumps(edge), edge["id"], project_id),
                )
        return graph

    def resolve_review_item(self, project_id: str, item_id: str, resolution: dict[str, Any]) -> dict[str, Any]:
        graph = self.get_graph(project_id)
        resolved: dict[str, Any] | None = None
        for item in graph["reviewItems"]:
            if item["id"] == item_id:
                item["status"] = "resolved"
                item["resolution"] = resolution
                item["resolvedBy"] = resolution.get("resolvedBy", "user")
                resolved = item
                break
        if not resolved:
            raise KeyError(item_id)
        with self.connect() as conn:
            conn.execute(
                "UPDATE review_items SET payload_json = ? WHERE id = ? AND project_id = ?",
                (json.dumps(resolved), item_id, project_id),
            )
            conn.execute(
                """
                INSERT INTO correction_memory (project_id, memory_type, key, value_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_id, memory_type, key) DO UPDATE SET value_json = excluded.value_json
                """,
                (project_id, resolved["type"], item_id, json.dumps(resolution)),
            )
        return resolved

    def update_node(self, project_id: str, node_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM graph_nodes WHERE id = ? AND project_id = ?",
                (node_id, project_id),
            ).fetchone()
            if not row:
                raise KeyError(node_id)
            node = json.loads(row["payload_json"])
            node.update(updates)
            conn.execute(
                "UPDATE graph_nodes SET payload_json = ? WHERE id = ? AND project_id = ?",
                (json.dumps(node), node_id, project_id),
            )
        return node

    def update_edge(self, project_id: str, edge_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT payload_json FROM graph_edges WHERE id = ? AND project_id = ?",
                (edge_id, project_id),
            ).fetchone()
            if not row:
                raise KeyError(edge_id)
            edge = json.loads(row["payload_json"])
            edge.update(updates)
            conn.execute(
                "UPDATE graph_edges SET payload_json = ? WHERE id = ? AND project_id = ?",
                (json.dumps(edge), edge_id, project_id),
            )
        return edge

    def delete_node(self, project_id: str, node_id: str) -> None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM graph_nodes WHERE id = ? AND project_id = ?",
                (node_id, project_id),
            ).fetchone()
            if not row:
                raise KeyError(node_id)
            conn.execute("DELETE FROM graph_nodes WHERE id = ? AND project_id = ?", (node_id, project_id))
            conn.execute(
                "DELETE FROM graph_edges WHERE project_id = ? AND (payload_json LIKE ? OR payload_json LIKE ?)",
                (project_id, f'%"{node_id}:%', f'%{node_id}"%'),
            )

    def record_export(self, project_id: str, export_type: str, path: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO export_history (project_id, export_type, path) VALUES (?, ?, ?)",
                (project_id, export_type, path),
            )

    def _drawing_option_payloads(self, project_id: str, raw_option: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        option: Any = raw_option
        document: Any = None
        if isinstance(raw_option, tuple) and len(raw_option) == 2:
            option, document = raw_option
        else:
            document = getattr(raw_option, "drawingDocument", None)
            if document is None:
                document = getattr(raw_option, "drawing_document", None)

        option_payload = to_dict(option)
        if not isinstance(option_payload, dict):
            raise ValueError("Layout option payload must be a dictionary")
        option_payload = dict(option_payload)

        for key in ("drawingDocument", "drawing_document"):
            nested_document = option_payload.pop(key, None)
            if document is None:
                document = nested_document

        if document is None:
            raise ValueError(f"Layout option {option_payload.get('id', '<unknown>')} is missing a drawing document")

        document_payload = to_dict(document)
        if not isinstance(document_payload, dict):
            raise ValueError("Drawing document payload must be a dictionary")
        document_payload = dict(document_payload)

        drawing_id = option_payload.pop("drawing_id", None) or option_payload.get("drawingId")
        if drawing_id is None:
            drawing_id = document_payload.get("id")
        if not drawing_id:
            raise ValueError(f"Layout option {option_payload.get('id', '<unknown>')} is missing drawingId")
        if document_payload.get("id") != drawing_id:
            raise ValueError(f"Layout option {option_payload.get('id', '<unknown>')} drawingId does not match document id")

        self._validate_payload_project_id("Layout option", project_id, option_payload)
        self._validate_payload_project_id("Drawing document", project_id, document_payload)
        option_payload.pop("project_id", None)
        document_payload.pop("project_id", None)
        option_payload["drawingId"] = drawing_id
        option_payload["projectId"] = project_id
        document_payload["projectId"] = project_id
        return option_payload, document_payload

    def _validate_payload_project_id(self, payload_name: str, project_id: str, payload: dict[str, Any]) -> None:
        for key in ("projectId", "project_id"):
            incoming_project_id = payload.get(key)
            if incoming_project_id is not None and incoming_project_id != project_id:
                raise ValueError(f"{payload_name} {key} does not match project_id")
