// Tauri commands for Bifang Desktop

use tauri::command;
use std::process::Command;
use std::fs;
use std::path::Path;

#[command]
async fn get_file_tree(path: String) -> Result<String, String> {
    let path = Path::new(&path);
    if !path.exists() {
        return Err("Path does not exist".to_string());
    }

    let mut entries = Vec::new();
    read_dir_recursive(path, path, &mut entries, 0)?;

    serde_json::to_string(&entries).map_err(|e| e.to_string())
}

fn read_dir_recursive(
    root: &Path,
    current: &Path,
    entries: &mut Vec<FileEntry>,
    depth: usize,
) -> Result<(), String> {
    if depth > 10 {
        return Ok(());
    }

    let dir_entries = fs::read_dir(current).map_err(|e| e.to_string())?;

    for entry in dir_entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();

        // Skip hidden files and common ignore patterns
        if name.starts_with('.') && name != ".github" && name != ".gitignore" {
            continue;
        }
        if matches!(name.as_str(), "node_modules" | "target" | "dist" | "build" | "__pycache__" | ".venv" | "venv") {
            continue;
        }

        let is_dir = path.is_dir();
        let relative = path.strip_prefix(root).map_err(|e| e.to_string())?.to_string_lossy().to_string();

        let mut file_entry = FileEntry {
            name,
            path: relative,
            type_: if is_dir { "directory".to_string() } else { "file".to_string() },
            children: None,
            expanded: false,
            has_changes: false,
        };

        if is_dir {
            let mut children = Vec::new();
            read_dir_recursive(root, &path, &mut children, depth + 1)?;
            file_entry.children = Some(children);
        }

        entries.push(file_entry);
    }

    Ok(())
}

#[derive(serde::Serialize)]
struct FileEntry {
    name: String,
    path: String,
    type_: String,
    children: Option<Vec<FileEntry>>,
    expanded: bool,
    has_changes: bool,
}

#[command]
async fn run_bifang_command(args: Vec<String>) -> Result<String, String> {
    let output = Command::new("bifang")
        .args(args)
        .output()
        .map_err(|e| format!("Failed to execute bifang: {}", e))?;

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);

    if output.status.success() {
        Ok(stdout.to_string())
    } else {
        Err(format!("Command failed: {}", stderr))
    }
}

