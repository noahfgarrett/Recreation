use serde::Serialize;
use std::{
    net::TcpListener,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
};
use tauri::{AppHandle, Manager, State};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_shell::{process::CommandChild, ShellExt};

#[derive(Default)]
struct ServiceState {
    child: Mutex<Option<ManagedChild>>,
    info: Mutex<Option<ServiceInfo>>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct ServiceInfo {
    base_url: String,
    port: u16,
    data_dir: String,
    mode: String,
}

enum ManagedChild {
    Std(Child),
    Sidecar(CommandChild),
}

impl ManagedChild {
    fn kill(self) {
        match self {
            ManagedChild::Std(mut child) => {
                let _ = child.kill();
                let _ = child.wait();
            }
            ManagedChild::Sidecar(child) => {
                let _ = child.kill();
            }
        }
    }
}

#[tauri::command]
async fn select_import_files(app: AppHandle) -> Result<Vec<String>, String> {
    let files = app
        .dialog()
        .file()
        .add_filter("PDF drawings", &["pdf"])
        .set_title("Select P&ID or cable PDF package")
        .blocking_pick_files();

    Ok(files
        .unwrap_or_default()
        .into_iter()
        .map(|path| path.to_string())
        .collect())
}

#[tauri::command]
async fn select_export_path(app: AppHandle) -> Result<Option<String>, String> {
    Ok(app
        .dialog()
        .file()
        .set_title("Select export destination")
        .blocking_save_file()
        .map(|path| path.to_string()))
}

#[tauri::command]
async fn start_project_service(app: AppHandle, state: State<'_, ServiceState>) -> Result<ServiceInfo, String> {
    if let Some(info) = state.info.lock().map_err(|_| "Service state poisoned")?.clone() {
        return Ok(info);
    }

    let port = find_free_port()?;
    let data_dir = app
        .path()
        .app_local_data_dir()
        .map_err(|err| format!("Could not resolve app data directory: {err}"))?
        .join("projects");
    std::fs::create_dir_all(&data_dir).map_err(|err| format!("Could not create data directory: {err}"))?;

    let child = spawn_extractor(&app, port, data_dir.clone())?;
    let info = ServiceInfo {
        base_url: format!("http://127.0.0.1:{port}"),
        port,
        data_dir: data_dir.to_string_lossy().to_string(),
        mode: "tauri".to_string(),
    };

    *state.child.lock().map_err(|_| "Service state poisoned")? = Some(child);
    *state.info.lock().map_err(|_| "Service state poisoned")? = Some(info.clone());
    Ok(info)
}

#[tauri::command]
async fn stop_project_service(state: State<'_, ServiceState>) -> Result<(), String> {
    if let Some(child) = state.child.lock().map_err(|_| "Service state poisoned")?.take() {
        child.kill();
    }
    *state.info.lock().map_err(|_| "Service state poisoned")? = None;
    Ok(())
}

#[tauri::command]
async fn open_source_evidence(project_id: String, evidence_id: String) -> Result<(), String> {
    println!("Open evidence requested: project={project_id} evidence={evidence_id}");
    Ok(())
}

fn find_free_port() -> Result<u16, String> {
    TcpListener::bind(("127.0.0.1", 0))
        .map_err(|err| format!("Could not bind local port: {err}"))?
        .local_addr()
        .map(|addr| addr.port())
        .map_err(|err| format!("Could not read local port: {err}"))
}

fn spawn_extractor(app: &AppHandle, port: u16, data_dir: PathBuf) -> Result<ManagedChild, String> {
    if let Ok(command) = std::env::var("RECREATION_EXTRACTOR_CMD") {
        return spawn_shell_command(&command, port, data_dir);
    }

    if let Some(backend_dir) = dev_backend_dir()? {
        let mut command = Command::new(python_binary());
        command
            .arg("-m")
            .arg("recreation_extractor.cli")
            .arg("serve")
            .arg("--host")
            .arg("127.0.0.1")
            .arg("--port")
            .arg(port.to_string())
            .arg("--data-dir")
            .arg(data_dir)
            .env("PYTHONPATH", backend_dir);
        return spawn_configured(command);
    }

    if let Ok(child) = spawn_sidecar(app, port, data_dir.clone()) {
        return Ok(child);
    }

    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|err| format!("Could not resolve resource directory: {err}"))?;
    let bundled = resource_dir.join("backend").join("recreation_extractor").join("cli.py");
    if bundled.exists() {
        let mut command = Command::new(python_binary());
        command
            .arg("-m")
            .arg("recreation_extractor.cli")
            .arg("serve")
            .arg("--host")
            .arg("127.0.0.1")
            .arg("--port")
            .arg(port.to_string())
            .arg("--data-dir")
            .arg(data_dir)
            .env("PYTHONPATH", resource_dir.join("backend"));
        return spawn_configured(command);
    }

    Err("Could not find recreation-extractor sidecar or development Python backend".to_string())
}

fn dev_backend_dir() -> Result<Option<PathBuf>, String> {
    let current_dir = std::env::current_dir().map_err(|err| format!("Could not resolve current directory: {err}"))?;
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let candidates = [
        current_dir.join("backend"),
        current_dir.join("..").join("backend"),
        manifest_dir.join("backend"),
        manifest_dir.join("..").join("backend"),
    ];

    Ok(candidates
        .into_iter()
        .find(|path| path.join("recreation_extractor").join("cli.py").exists()))
}

fn spawn_sidecar(app: &AppHandle, port: u16, data_dir: PathBuf) -> Result<ManagedChild, String> {
    let sidecar_args = vec![
        "serve".to_string(),
        "--host".to_string(),
        "127.0.0.1".to_string(),
        "--port".to_string(),
        port.to_string(),
        "--data-dir".to_string(),
        data_dir.to_string_lossy().to_string(),
    ];
    let (_rx, child) = app
        .shell()
        .sidecar("binaries/recreation-extractor")
        .map_err(|err| format!("Could not resolve extractor sidecar: {err}"))?
        .args(sidecar_args)
        .spawn()
        .map_err(|err| format!("Could not start extractor sidecar: {err}"))?;
    Ok(ManagedChild::Sidecar(child))
}

fn spawn_shell_command(command_line: &str, port: u16, data_dir: PathBuf) -> Result<ManagedChild, String> {
    let mut parts = command_line.split_whitespace();
    let program = parts.next().ok_or("RECREATION_EXTRACTOR_CMD is empty")?;
    let mut command = Command::new(program);
    command.args(parts);
    command
        .arg("serve")
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .arg("--data-dir")
        .arg(data_dir);
    spawn_configured(command)
}

fn spawn_configured(mut command: Command) -> Result<ManagedChild, String> {
    command.stdout(Stdio::piped()).stderr(Stdio::piped());
    command
        .spawn()
        .map(ManagedChild::Std)
        .map_err(|err| format!("Could not start extractor service: {err}"))
}

fn python_binary() -> &'static str {
    if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    }
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .manage(ServiceState::default())
        .invoke_handler(tauri::generate_handler![
            select_import_files,
            select_export_path,
            start_project_service,
            stop_project_service,
            open_source_evidence
        ])
        .run(tauri::generate_context!())
        .expect("error while running Recreation");
}

fn main() {
    run();
}
