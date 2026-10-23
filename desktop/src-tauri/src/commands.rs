// Tauri commands for Bifang Desktop

use std::fs;
use std::path::Path;
use tauri::command;

#[command]
pub(crate) fn resolve_workspace_path(path: String) -> Result<String, String> {
    let directory = Path::new(&path);
    if !directory.is_absolute() {
        return Err("Enter an absolute directory path".to_string());
    }
    let directory = fs::canonicalize(directory)
        .map_err(|_| "Directory does not exist or is not accessible".to_string())?;
    if !directory.is_dir() {
        return Err("Choose a directory, not a file".to_string());
    }
    Ok(directory.to_string_lossy().into_owned())
}

#[command]
pub(crate) async fn get_file_tree(path: String) -> Result<String, String> {
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
        if matches!(
            name.as_str(),
            "node_modules" | "target" | "dist" | "build" | "__pycache__" | ".venv" | "venv"
        ) {
            continue;
        }

        let is_dir = path.is_dir();
        let relative = path
            .strip_prefix(root)
            .map_err(|e| e.to_string())?
            .to_string_lossy()
            .to_string();

        let mut file_entry = FileEntry {
            name,
            path: relative,
            type_: if is_dir {
                "directory".to_string()
            } else {
                "file".to_string()
            },
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
    #[serde(rename = "type")]
    type_: String,
    children: Option<Vec<FileEntry>>,
    expanded: bool,
    has_changes: bool,
}

#[cfg(test)]
mod tests {
    use super::{resolve_workspace_path, FileEntry};
    use std::path::Path;

    #[test]
    fn workspace_path_rejects_relative_paths() {
        assert!(resolve_workspace_path(".".to_string()).is_err());
    }

    #[test]
    fn workspace_path_rejects_files() {
        let executable = std::env::current_exe().unwrap();
        assert!(resolve_workspace_path(executable.to_string_lossy().into_owned()).is_err());
    }

    #[test]
    fn workspace_path_resolves_existing_directories() {
        let directory = std::env::temp_dir();
        let resolved = resolve_workspace_path(directory.to_string_lossy().into_owned()).unwrap();
        assert_eq!(
            Path::new(&resolved),
            std::fs::canonicalize(directory).unwrap()
        );
    }

    #[test]
    fn file_tree_serializes_frontend_type_field() {
        let entry = FileEntry {
            name: "src".to_string(),
            path: "src".to_string(),
            type_: "directory".to_string(),
            children: None,
            expanded: false,
            has_changes: false,
        };

        let value = serde_json::to_value(entry).unwrap();
        assert_eq!(value["type"], "directory");
        assert!(value.get("type_").is_none());
    }
}
