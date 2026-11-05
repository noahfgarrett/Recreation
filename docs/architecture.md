# Architecture

Recreation treats drawings as evidence for a structured graph.

1. PDF pages are parsed into positioned text spans and vector segments with PyMuPDF. Pages with lots of vector content but little usable text go through a Tesseract OCR fallback.
2. Text near the page edges is turned into off-page continuation candidates, which are scored and paired across sheets. Tags, lines, and equipment become graph nodes and edges, and anything uncertain becomes a review item.
3. The editor keeps drawing layout separate from the connectivity graph, so moving things around doesn't change what is connected to what.
4. A confirmed preflight setup (page roles, disciplines, legend pages) can be saved as a template and suggested for later packages.
5. Exports are generated from the stored graph and drawing data, not from screenshots.

Naming rules that depend on a particular drawing package (project code, building codes) live in `backend/recreation_extractor/conventions.py`.

`backend/recreation_extractor/llm.py` is an adapter for a local llama.cpp server that would reconcile ambiguous tag text. It is not wired into the pipeline.
