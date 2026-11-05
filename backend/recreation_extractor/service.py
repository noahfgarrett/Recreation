from __future__ import annotations

import hashlib
import json
import queue
import re
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .extraction import Detection, LineSegment, extract_pdf, source_file_for_path
from .exports import export_line_list_xlsx, export_pdf, export_svg, export_xlsx
from .graph import build_graph
from .hierarchy.models import DISCIPLINES, PAGE_ROLES, TemplateSummary, to_plain_dict
from .hierarchy.preflight import PreflightPageSummary, build_preflight_review
from .hierarchy.templates import build_template_payload, score_template_match
from .models import Project, SourceFile, to_dict
from .pid_stitch.evidence import extract_pid_evidence, find_continuation_candidates
from .pid_stitch.export import export_drawing_pdf, export_drawing_svg
from .pid_stitch.layout import generate_layout_options
from .pid_stitch.matching import rank_continuation_matches
from .storage import ProjectStore

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    fitz = None


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class JobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.events: dict[str, "queue.Queue[dict[str, Any]]"] = {}
        self.lock = threading.Lock()

    def start(self, name: str, target: Callable[[str, Callable[[str, dict[str, Any]], None]], Any]) -> str:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        with self.lock:
            self.jobs[job_id] = {"id": job_id, "name": name, "status": "queued", "progress": 0, "result": None, "error": None}
            self.events[job_id] = queue.Queue()
        thread = threading.Thread(target=self._run, args=(job_id, target), daemon=True)
        thread.start()
        return job_id

    def _run(self, job_id: str, target: Callable[[str, Callable[[str, dict[str, Any]], None]], Any]) -> None:
        self._update(job_id, status="running", progress=2)

        def emit(event: str, payload: dict[str, Any]) -> None:
            self._event(job_id, {"event": event, "payload": payload})

        try:
            result = target(job_id, emit)
            self._update(job_id, status="completed", progress=100, result=result)
            emit("completed", {"result": result})
        except Exception as exc:
            self._update(job_id, status="failed", error=str(exc))
            emit("failed", {"error": str(exc)})

    def _update(self, job_id: str, **updates: Any) -> None:
        with self.lock:
            self.jobs[job_id].update(updates)
        self._event(job_id, {"event": "status", "payload": self.get(job_id)})

    def _event(self, job_id: str, event: dict[str, Any]) -> None:
        if job_id in self.events:
            self.events[job_id].put(event)

    def update_progress(self, job_id: str, progress: int) -> None:
        """Public interface for updating job progress."""
        self._update(job_id, progress=progress)

    def get(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            if job_id not in self.jobs:
                raise KeyError(job_id)
            return dict(self.jobs[job_id])

    def stream(self, job_id: str):
        if job_id not in self.events:
            raise KeyError(job_id)
        while True:
            try:
                event = self.events[job_id].get(timeout=15)
                yield f"event: {event['event']}\ndata: {json.dumps(event['payload'])}\n\n"
                if event["event"] in {"completed", "failed"}:
                    break
            except queue.Empty:
                yield "event: heartbeat\ndata: {}\n\n"


class RecreationService:
    def __init__(self, data_dir: str | Path) -> None:
        self.store = ProjectStore(data_dir)
        self.jobs = JobManager()

    def create_project(self, name: str) -> Project:
        now = utc_now()
        project = Project(id=f"project_{uuid.uuid4().hex[:12]}", name=name, createdAt=now, updatedAt=now)
        self.store.upsert_project(project)
        return project

    def import_files(self, project_id: str, paths: list[str | dict[str, Any]]) -> dict[str, Any]:
        imported = []
        for item in paths:
            selection = self._normalize_import_selection(item)
            source_path = selection["path"]
            pages = selection.get("pages")
            display_name: str | None = None
            if pages is not None:
                source_path = str(self._create_page_subset_pdf(project_id, source_path, pages))
                display_name = f"{Path(selection['path']).stem} pages {self._format_page_selection(pages)}.pdf"
            source = source_file_for_path(project_id, source_path)
            if display_name:
                source.name = display_name
            self.store.add_source_file(source)
            imported.append(asdict(source))
        return {"projectId": project_id, "files": imported}

    def _normalize_import_selection(self, item: str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(item, str):
            return {"path": item, "pages": None}
        path = item.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("Import selection is missing a PDF path")
        raw_pages = item.get("pages")
        if raw_pages is None:
            return {"path": path, "pages": None}
        pages: list[int] = []
        for page in raw_pages:
            if not self._is_positive_int(page):
                raise ValueError(f"Invalid page selection for {path}: {page}")
            pages.append(page)
        return {"path": path, "pages": sorted(set(pages))}

    def _create_page_subset_pdf(self, project_id: str, path: str, pages: list[int]) -> Path:
        if fitz is None:
            raise ValueError("PyMuPDF is required to import selected PDF pages")
        if not pages:
            raise ValueError(f"No pages selected for {path}")

        source_path = Path(path)
        doc = fitz.open(source_path)
        try:
            page_count = len(doc)
            bad_pages = [page for page in pages if page < 1 or page > page_count]
            if bad_pages:
                raise ValueError(f"Selected pages for {source_path.name} must be between 1 and {page_count}")
            subset = fitz.open()
            try:
                for page in pages:
                    subset.insert_pdf(doc, from_page=page - 1, to_page=page - 1)
                output_dir = self.store.data_dir / "imports" / project_id
                output_dir.mkdir(parents=True, exist_ok=True)
                page_slug = "-".join(str(page) for page in pages)
                stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", source_path.stem).strip("_") or "source"
                digest = hashlib.sha256(f"{source_path.resolve()}\0{page_slug}".encode("utf-8")).hexdigest()[:10]
                output_path = output_dir / f"{stem}_pages_{page_slug}_{digest}.pdf"
                subset.save(output_path)
            finally:
                subset.close()
        finally:
            doc.close()
        return output_path

    def _format_page_selection(self, pages: list[int]) -> str:
        return ",".join(str(page) for page in pages)

    def run_preflight(self, project_id: str) -> dict[str, Any]:
        sources = self.store.list_source_files(project_id)
        if not sources:
            raise ValueError("No source files imported for this project")
        summaries: list[PreflightPageSummary] = []
        for source_row in sources:
            source_summaries = self._preflight_page_summaries(source_row["id"], source_row["path"])
            summaries.extend(source_summaries)
            self._persist_preflight_page_count(project_id, source_row, len(source_summaries))
        draft_review = to_plain_dict(build_preflight_review(project_id, summaries, []))
        templates = self._rank_hierarchy_templates(draft_review)
        review = to_plain_dict(build_preflight_review(project_id, summaries, templates))
        return self.store.upsert_preflight_review(project_id, review)

    def get_preflight(self, project_id: str) -> dict[str, Any]:
        existing = self.store.get_preflight_review(project_id)
        if existing is not None:
            self._ensure_preflight_sources_available(project_id)
            return existing
        return self.run_preflight(project_id)

    def confirm_preflight(self, project_id: str, payload: Any) -> dict[str, Any]:
        self._validate_preflight_confirmation(project_id, payload)
        payload = {**payload, "projectId": project_id, "status": "confirmed"}
        return self.store.upsert_preflight_review(project_id, payload)

    def list_hierarchy_templates(self) -> list[dict[str, Any]]:
        return self.store.list_hierarchy_templates()

    def save_hierarchy_template(self, name: str, review: dict[str, Any]) -> dict[str, Any]:
        template_id = f"template_{uuid.uuid4().hex[:12]}"
        template = build_template_payload(template_id, name.strip(), review)
        return self.store.upsert_hierarchy_template(template_id, template["name"], template)

    def _rank_hierarchy_templates(self, review: dict[str, Any]) -> list[TemplateSummary]:
        ranked_templates: list[tuple[float, dict[str, Any]]] = []
        for template in self.store.list_hierarchy_templates():
            score = score_template_match(template, review)
            if score <= 0.25:
                continue
            ranked_templates.append((score, template))
        ranked_templates.sort(key=lambda item: (-item[0], str(item[1].get("name", ""))))
        return [
            TemplateSummary(
                id=str(template.get("id", "")),
                name=str(template.get("name", "")),
                disciplines=list(template.get("disciplines", [])),
                description=str(template.get("description", "")),
                confidence=score,
            )
            for score, template in ranked_templates
        ]

    def _preflight_page_summaries(self, source_file_id: str, path: str) -> list[PreflightPageSummary]:
        doc = self._open_imported_pdf(path)
        try:
            summaries: list[PreflightPageSummary] = []
            for index, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                summaries.append(PreflightPageSummary(source_file_id, index, text[:8000]))
            return summaries
        finally:
            doc.close()

    def _persist_preflight_page_count(self, project_id: str, source_row: dict[str, Any], page_count: int) -> None:
        if page_count <= 0:
            return
        self.store.add_source_file(
            SourceFile(
                id=source_row["id"],
                projectId=project_id,
                path=source_row["path"],
                name=source_row["name"],
                sha256=source_row["sha256"],
                pageCount=page_count,
            )
        )

    def _validate_preflight_confirmation(self, project_id: str, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Preflight confirmation payload must be a dictionary")

        known_disciplines = set(DISCIPLINES)
        disciplines = payload.get("disciplines")
        if not isinstance(disciplines, list) or not disciplines:
            raise ValueError("Preflight disciplines must be a non-empty list")
        for discipline in disciplines:
            if discipline not in known_disciplines:
                raise ValueError(f"Unknown preflight discipline: {discipline}")

        legend_pages = payload.get("legendPages")
        if not isinstance(legend_pages, list):
            raise ValueError("Preflight legendPages must be a list")
        for page in legend_pages:
            if not self._is_positive_int(page):
                raise ValueError("Preflight legendPages must contain positive integers")

        page_roles = payload.get("pageRoles")
        if not isinstance(page_roles, list):
            raise ValueError("Preflight pageRoles must be a list")
        known_roles = set(PAGE_ROLES)
        sources = self.store.list_source_files(project_id)
        sources_by_id = {source["id"]: source for source in sources}
        source_page_counts = [self._source_page_count(source) for source in sources]
        max_page_count = max(source_page_counts, default=0)
        for page in legend_pages:
            if max_page_count > 0 and page > max_page_count:
                raise ValueError(f"Preflight legend page {page} exceeds available source page count {max_page_count}")
        for assignment in page_roles:
            if not isinstance(assignment, dict):
                raise ValueError("Preflight pageRoles must contain dictionaries")
            source_file_id = assignment.get("sourceFileId")
            source = sources_by_id.get(source_file_id)
            if sources and source is None:
                raise ValueError(f"Unknown preflight sourceFileId: {source_file_id}")
            page = assignment.get("page")
            if not self._is_positive_int(page):
                raise ValueError("Preflight pageRoles must contain positive integer pages")
            page_count = self._source_page_count(source)
            if page_count > 0 and page > page_count:
                raise ValueError(f"Preflight page {page} exceeds source page count {page_count}")
            role = assignment.get("role")
            if role not in known_roles:
                raise ValueError(f"Unknown preflight page role: {role}")

        self._ensure_preflight_sources_available(project_id, sources)

    def _is_positive_int(self, value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value > 0

    def _ensure_preflight_sources_available(self, project_id: str, sources: list[dict[str, Any]] | None = None) -> None:
        for source in sources if sources is not None else self.store.list_source_files(project_id):
            self._ensure_source_file_available(source)

    def _ensure_source_file_available(self, source: dict[str, Any]) -> None:
        path = str(source.get("path", ""))
        if not Path(path).is_file():
            raise ValueError(f"Imported PDF file is missing: {path}")

    def _source_page_count(self, source: dict[str, Any] | None) -> int:
        if not source:
            return 0
        return self._pdf_page_count(source)

    def _pdf_page_count(self, source: dict[str, Any]) -> int:
        path = str(source.get("path", ""))
        doc = self._open_imported_pdf(path, purpose="validate preflight page counts")
        try:
            return len(doc)
        finally:
            doc.close()

    def _open_imported_pdf(self, path: str, purpose: str = "read imported PDF") -> Any:
        if fitz is None:
            raise ValueError(f"PyMuPDF is required to {purpose}")
        if not Path(path).is_file():
            raise ValueError(f"Imported PDF file is missing: {path}")
        try:
            return fitz.open(path)
        except Exception as exc:
            raise ValueError(f"Unable to read imported PDF: {path}") from exc

    def start_extract_job(self, project_id: str) -> str:
        def run(_job_id: str, emit: Callable[[str, dict[str, Any]], None]) -> dict[str, Any]:
            sources = self.store.list_source_files(project_id)
            if not sources:
                raise ValueError("No source files imported for this project")
            all_pages: list[dict[str, Any]] = []
            all_detections: list[Detection] = []
            all_segments: list[LineSegment] = []
            total = len(sources)
            for index, source_row in enumerate(sources, start=1):
                emit("extracting", {"file": source_row["name"], "index": index, "total": total})
                source = source_file_for_path(project_id, source_row["path"])
                source, pages, detections = extract_pdf(source)
                self.store.add_source_file(source)
                all_pages.extend([to_dict(page) for page in pages])
                all_detections.extend(detections)
                for page in pages:
                    all_segments.extend(page.paths)
                self.jobs.update_progress(_job_id, int((index / total) * 70))
            self.store.replace_pages(project_id, all_pages)
            emit("graph", {"detections": len(all_detections)})
            self.jobs.update_progress(_job_id, 75)
            graph = build_graph(project_id, all_detections, tuple(all_segments))
            self.jobs.update_progress(_job_id, 90)
            self.store.replace_graph(graph)
            self.jobs.update_progress(_job_id, 95)
            return {"projectId": project_id, "nodes": len(graph.nodes), "edges": len(graph.edges), "reviewItems": len(graph.reviewItems)}

        return self.jobs.start("extract", run)

    def start_stitch_job(self, project_id: str) -> str:
        def run(_job_id: str, emit: Callable[[str, dict[str, Any]], None]) -> dict[str, Any]:
            sources = self.store.list_source_files(project_id)
            if not sources:
                raise ValueError("No source files imported for this project")

            all_pages = []
            all_candidates = []
            source_paths: dict[str, str] = {}
            total = len(sources)
            for index, source_row in enumerate(sources, start=1):
                emit("stitch_extracting", {"file": source_row["name"], "index": index, "total": total})
                source_paths[source_row["id"]] = source_row["path"]
                pages = extract_pid_evidence(project_id, source_row["id"], source_row["path"])
                candidates = find_continuation_candidates(pages)
                all_pages.extend(pages)
                all_candidates.extend(candidates)
                self.jobs.update_progress(_job_id, int((index / total) * 65))

            emit("stitch_matching", {"candidates": len(all_candidates)})
            self.jobs.update_progress(_job_id, 75)
            matches = rank_continuation_matches(all_candidates, source_paths=source_paths)

            emit("stitch_layout", {"pages": len(all_pages), "candidates": len(all_candidates), "matches": len(matches)})
            self.jobs.update_progress(_job_id, 90)
            options = generate_layout_options(
                project_id,
                all_pages,
                all_candidates,
                matches,
                source_paths=source_paths,
                preflight_review=self.store.get_preflight_review(project_id),
            )
            self.store.replace_drawing_options(project_id, options)
            self.jobs.update_progress(_job_id, 95)
            layout_option_ids = [option.id for option, _document in options]
            drawing_ids = [document.id for _option, document in options]

            return {
                "projectId": project_id,
                "candidates": len(all_candidates),
                "matches": len(matches),
                "layoutOptions": len(options),
                "layoutOptionIds": layout_option_ids,
                "drawingIds": drawing_ids,
            }

        return self.jobs.start("stitch", run)

    def export(self, project_id: str, export_type: str) -> dict[str, Any]:
        graph = self.store.get_graph(project_id)
        export_dir = self.store.data_dir / "exports" / project_id
        if export_type == "svg":
            path = export_svg(graph, export_dir / "combined.svg")
        elif export_type == "pdf":
            path = export_pdf(graph, export_dir / "combined.pdf")
        elif export_type == "xlsx":
            path = export_xlsx(graph, export_dir / "tags-and-legend.xlsx")
        elif export_type == "line_list":
            path = export_line_list_xlsx(graph, export_dir / "line-list.xlsx")
        else:
            raise ValueError(f"Unsupported export type: {export_type}")
        self.store.record_export(project_id, export_type, str(path))
        return {"projectId": project_id, "type": export_type, "path": str(path)}

    def export_drawing(self, project_id: str, drawing_id: str, export_type: str) -> dict[str, Any]:
        document = self.store.get_drawing_document(project_id, drawing_id)
        export_dir = self.store.data_dir / "exports" / project_id / "drawings"
        if export_type == "svg":
            path = export_drawing_svg(document, export_dir / f"{drawing_id}.svg")
        elif export_type == "pdf":
            path = export_drawing_pdf(document, export_dir / f"{drawing_id}.pdf")
        else:
            raise ValueError(f"Unsupported drawing export type: {export_type}")
        self.store.record_export(project_id, f"drawing_{export_type}", str(path))
        return {"projectId": project_id, "drawingId": drawing_id, "type": export_type, "path": str(path)}
