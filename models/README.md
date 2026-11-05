# models

Nothing here is needed to run the app. `src-tauri/tauri.conf.json` bundles this folder, and it is where a GGUF model would go (`models/llm/*.gguf`) for the llama.cpp helper in `backend/recreation_extractor/llm.py`. That helper is not called by the pipeline yet.
