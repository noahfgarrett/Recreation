# Tauri Sidecar Binaries

Tauri expects platform-specific sidecars here using this naming pattern:

```text
recreation-extractor-<target-triple>
llama-server-<target-triple>
```

Examples:

```text
recreation-extractor-aarch64-apple-darwin
recreation-extractor-x86_64-apple-darwin
recreation-extractor-x86_64-pc-windows-msvc.exe
```

The repository includes macOS arm64 placeholders: `recreation-extractor-*` runs the Python service from `./backend`, and `llama-server-*` just exits. For packaging:

1. Run `scripts/build-extractor-sidecar.sh` on each target platform.
2. Replace `llama-server-*` with a `llama.cpp` server binary if you want to try `llm.py` (not used by the pipeline yet).
