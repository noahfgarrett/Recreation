from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .service import RecreationService

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    fitz = None

try:
    from fastapi import Body, FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import Response, StreamingResponse
    from pydantic import BaseModel, StrictInt
except Exception as exc:  # pragma: no cover
    raise RuntimeError("FastAPI dependencies are required to run the service") from exc

try:
    from PIL import Image
except Exception:  # pragma: no cover - optional at runtime
    Image = None


class CreateProjectRequest(BaseModel):
    name: str = "Untitled Recreation Project"


class ImportFileSelection(BaseModel):
    path: str
    pages: list[StrictInt] | None = None


class ImportFilesRequest(BaseModel):
    paths: list[str] = []
    files: list[ImportFileSelection] | None = None


class ConfirmPreflightRequest(BaseModel):
    payload: dict[str, Any]


class SaveHierarchyTemplateRequest(BaseModel):
    name: str
    review: dict[str, Any]


class UpdateNodeRequest(BaseModel):
    tag: str | None = None
    kind: str | None = None
    locked: bool | None = None


class UpdateEdgeRequest(BaseModel):
    label: str | None = None
    lineOrCableId: str | None = None


class LayoutUpdateRequest(BaseModel):
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []


class ReviewResolutionRequest(BaseModel):
    resolvedBy: str = "user"
    resolution: dict[str, Any] = {}


_SNAKE_TO_CAMEL: dict[str, str] = {
    "id": "id",
    "name": "name",
    "created_at": "createdAt",
    "updated_at": "updatedAt",
    "project_id": "projectId",
    "source_file_id": "sourceFileId",
    "page_count": "pageCount",
    "page_number": "pageNumber",
    "vector_count": "vectorCount",
}


def _to_camel_dict(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a dict with snake_case keys to camelCase."""
    return {_SNAKE_TO_CAMEL.get(key, key): value for key, value in row.items()}


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    service = RecreationService(data_dir or os.environ.get("RECREATION_DATA_DIR", ".recreation-data"))
    app = FastAPI(title="Recreation Extractor", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:1420",
            "http://localhost:1420",
            "http://127.0.0.1:5190",
            "http://localhost:5190",
            "tauri://localhost",
        ],
        allow_origin_regex=r"^(tauri://localhost|https?://(localhost|127\.0\.0\.1|tauri\.localhost)(:\d+)?)$",
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Page-Width", "X-Page-Height"],
    )

    def require_project(project_id: str) -> None:
        if not service.store.project_exists(project_id):
            raise HTTPException(status_code=404, detail="Project not found")

    def require_pdf_path(path: str) -> None:
        if not path.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail=f"Only PDF files are supported: {path}",
            )
        if not os.path.isfile(path):
            raise HTTPException(
                status_code=400,
                detail=f"File does not exist: {path}",
            )

    def webp_page_response(path: str, page_num: int, dpi: int) -> Response:
        if fitz is None:
            raise HTTPException(status_code=501, detail="PyMuPDF is not available")
        if Image is None:
            raise HTTPException(status_code=501, detail="Pillow is not available")
        require_pdf_path(path)

        doc = fitz.open(path)
        try:
            if page_num < 1 or page_num > len(doc):
                raise HTTPException(status_code=404, detail=f"Page {page_num} not found (document has {len(doc)} pages)")
            page = doc[page_num - 1]
            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=70, method=4)
            return Response(
                content=output.getvalue(),
                media_type="image/webp",
                headers={
                    "Cache-Control": "public, max-age=3600",
                    "X-Page-Width": str(page_width),
                    "X-Page-Height": str(page_height),
                    "Access-Control-Expose-Headers": "X-Page-Width, X-Page-Height",
                },
            )
        finally:
            doc.close()

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "service": "recreation-extractor"}

    @app.get("/pdf-preview")
    def preview_pdf(
        path: str = Query(...),
        dpi: int = Query(default=54, ge=36, le=150),
    ) -> dict[str, Any]:
        if fitz is None:
            raise HTTPException(status_code=501, detail="PyMuPDF is not available")
        require_pdf_path(path)

        doc = fitz.open(path)
        try:
            pages = []
            for index, page in enumerate(doc, start=1):
                pages.append(
                    {
                        "page": index,
                        "width": float(page.rect.width),
                        "height": float(page.rect.height),
                        "thumbnailUrl": f"/pdf-preview/page-image?path={quote(path)}&page={index}&dpi={dpi}",
                    }
                )
            return {"path": path, "name": Path(path).name, "pageCount": len(doc), "pages": pages}
        finally:
            doc.close()

    @app.get("/pdf-preview/page-image")
    def preview_pdf_page_image(
        path: str = Query(...),
        page: int = Query(..., ge=1),
        dpi: int = Query(default=54, ge=36, le=150),
    ) -> Response:
        return webp_page_response(path, page, dpi)

    @app.get("/projects")
    def list_projects() -> list[dict[str, Any]]:
        return [_to_camel_dict(row) for row in service.store.list_projects()]

    @app.post("/projects")
    def create_project(payload: CreateProjectRequest) -> dict[str, Any]:
        return service.create_project(payload.name).__dict__

    @app.post("/projects/{project_id}/imports")
    def import_files(project_id: str, payload: ImportFilesRequest) -> dict[str, Any]:
        require_project(project_id)
        files = payload.files if payload.files is not None else [ImportFileSelection(path=path) for path in payload.paths]
        if not files:
            raise HTTPException(status_code=400, detail="No PDF files selected")
        for selection in files:
            require_pdf_path(selection.path)
        try:
            return service.import_files(
                project_id,
                [{"path": selection.path, "pages": selection.pages} for selection in files],
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/projects/{project_id}/preflight")
    def run_preflight(project_id: str) -> dict[str, Any]:
        require_project(project_id)
        try:
            return service.run_preflight(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/projects/{project_id}/preflight")
    def get_preflight(project_id: str) -> dict[str, Any]:
        require_project(project_id)
        try:
            return service.get_preflight(project_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/projects/{project_id}/preflight")
    def confirm_preflight(project_id: str, payload: ConfirmPreflightRequest) -> dict[str, Any]:
        require_project(project_id)
        try:
            return service.confirm_preflight(project_id, payload.payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/hierarchy-templates")
    def list_hierarchy_templates() -> list[dict[str, Any]]:
        return service.list_hierarchy_templates()

    @app.post("/hierarchy-templates")
    def save_hierarchy_template(payload: SaveHierarchyTemplateRequest) -> dict[str, Any]:
        if not payload.name.strip():
            raise HTTPException(status_code=400, detail="Template name is required")
        return service.save_hierarchy_template(payload.name, payload.review)

    @app.post("/projects/{project_id}/jobs/extract")
    def extract(project_id: str) -> dict[str, str]:
        require_project(project_id)
        return {"jobId": service.start_extract_job(project_id)}

    @app.post("/projects/{project_id}/jobs/stitch")
    def stitch(project_id: str) -> dict[str, str]:
        require_project(project_id)
        if not service.store.list_source_files(project_id):
            raise HTTPException(status_code=400, detail="No source files imported for this project")
        return {"jobId": service.start_stitch_job(project_id)}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            return service.jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc

    @app.get("/jobs/{job_id}/events")
    def job_events(job_id: str) -> StreamingResponse:
        try:
            stream = service.jobs.stream(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Job not found") from exc
        return StreamingResponse(stream, media_type="text/event-stream")

    @app.get("/projects/{project_id}/graph")
    def get_graph(project_id: str) -> dict[str, Any]:
        require_project(project_id)
        return service.store.get_graph(project_id)

    @app.get("/projects/{project_id}/layout-options")
    def list_layout_options(project_id: str) -> list[dict[str, Any]]:
        require_project(project_id)
        return service.store.list_layout_options(project_id)

    @app.get("/projects/{project_id}/drawings/{drawing_id}")
    def get_drawing(project_id: str, drawing_id: str) -> dict[str, Any]:
        require_project(project_id)
        try:
            return service.store.get_drawing_document(project_id, drawing_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Drawing not found") from exc

    @app.put("/projects/{project_id}/drawings/{drawing_id}")
    def update_drawing(project_id: str, drawing_id: str, payload: Any = Body(...)) -> dict[str, Any]:
        require_project(project_id)
        try:
            return service.store.update_drawing_document(project_id, drawing_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Drawing not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/projects/{project_id}/drawings/{drawing_id}/exports/{export_type}")
    def export_drawing(project_id: str, drawing_id: str, export_type: str) -> dict[str, Any]:
        require_project(project_id)
        try:
            return service.export_drawing(project_id, drawing_id, export_type)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Drawing not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/projects/{project_id}/layout")
    def put_layout(project_id: str, payload: LayoutUpdateRequest) -> dict[str, Any]:
        require_project(project_id)
        return service.store.update_layout(project_id, payload.model_dump())

    @app.post("/projects/{project_id}/review/{item_id}/resolve")
    def resolve_review(project_id: str, item_id: str, payload: ReviewResolutionRequest) -> dict[str, Any]:
        require_project(project_id)
        try:
            resolution = {"resolvedBy": payload.resolvedBy, **payload.resolution}
            return service.store.resolve_review_item(project_id, item_id, resolution)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Review item not found") from exc

    @app.patch("/projects/{project_id}/nodes/{node_id}")
    def update_node(project_id: str, node_id: str, payload: UpdateNodeRequest) -> dict[str, Any]:
        require_project(project_id)
        try:
            return service.store.update_node(project_id, node_id, payload.model_dump(exclude_none=True))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Node not found") from exc

    @app.delete("/projects/{project_id}/nodes/{node_id}")
    def delete_node(project_id: str, node_id: str) -> dict[str, Any]:
        require_project(project_id)
        try:
            service.store.delete_node(project_id, node_id)
            return {"deleted": node_id}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Node not found") from exc

    @app.patch("/projects/{project_id}/edges/{edge_id}")
    def update_edge(project_id: str, edge_id: str, payload: UpdateEdgeRequest) -> dict[str, Any]:
        require_project(project_id)
        updates = payload.model_dump(exclude_none=True)
        if "lineOrCableId" in updates:
            from .graph import parse_line_id

            updates["parsedLineId"] = parse_line_id(updates["lineOrCableId"])
        try:
            return service.store.update_edge(project_id, edge_id, updates)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Edge not found") from exc

    @app.post("/projects/{project_id}/exports/{export_type}")
    def export(project_id: str, export_type: str) -> dict[str, Any]:
        require_project(project_id)
        try:
            return service.export(project_id, export_type)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/projects/{project_id}/sources")
    def list_sources(project_id: str) -> list[dict[str, Any]]:
        require_project(project_id)
        return [_to_camel_dict(row) for row in service.store.list_source_files(project_id)]

    @app.get("/projects/{project_id}/sources/{source_file_id}/pages/{page_num}/image")
    def page_image(
        project_id: str,
        source_file_id: str,
        page_num: int,
        dpi: int = Query(default=150, ge=72, le=300),
    ) -> Response:
        require_project(project_id)
        if fitz is None:
            raise HTTPException(status_code=501, detail="PyMuPDF is not available")

        source = service.store.get_source_file(project_id, source_file_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source file not found")

        file_path = source["path"]
        if not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="PDF file not found on disk")

        doc = fitz.open(file_path)
        if page_num < 1 or page_num > len(doc):
            doc.close()
            raise HTTPException(status_code=404, detail=f"Page {page_num} not found (document has {len(doc)} pages)")

        page = doc[page_num - 1]
        page_width = float(page.rect.width)
        page_height = float(page.rect.height)
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        doc.close()

        return Response(
            content=png_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Page-Width": str(page_width),
                "X-Page-Height": str(page_height),
                "Access-Control-Expose-Headers": "X-Page-Width, X-Page-Height",
            },
        )

    return app
