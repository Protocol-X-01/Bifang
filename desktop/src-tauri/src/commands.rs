// Tauri commands for Bifang Desktop

use std::fs;
use std::path::Path;
use tauri::command;

#[command]
pub(crate) fn create_workspace(
    window: tauri::WebviewWindow,
    parent: String,
    name: String,
) -> Result<String, String> {
    crate::terminal::local_window(&window)?;
    create_workspace_directory(&parent, &name)
}

fn create_workspace_directory(parent: &str, name: &str) -> Result<String, String> {
    let stem = name.split('.').next().unwrap_or("").to_ascii_uppercase();
    if name.is_empty()
        || name.len() > 120
        || name.trim() != name
        || name.starts_with('.')
        || name.ends_with('.')
        || name
            .chars()
            .any(|character| character.is_control() || "/\\:<>\"|?*".contains(character))
        || matches!(stem.as_str(), "CON" | "PRN" | "AUX" | "NUL")
        || (1..=9).any(|number| stem == format!("COM{number}") || stem == format!("LPT{number}"))
    {
        return Err(
            "Choose a folder name without path separators, reserved names or trailing spaces"
                .into(),
        );
    }
    let parent = resolve_workspace_path(parent.to_string())?;
    let directory = Path::new(&parent).join(name);
    fs::create_dir(&directory).map_err(|error| match error.kind() {
        std::io::ErrorKind::AlreadyExists => "A file or folder already uses that name".to_string(),
        _ => "Could not create the workspace in this parent directory".to_string(),
    })?;
    Ok(directory.to_string_lossy().into_owned())
}

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
    use super::{create_workspace_directory, resolve_workspace_path, FileEntry};
    use std::path::Path;

    #[test]
    fn new_workspace_rejects_paths_and_reserved_names() {
        let parent = std::env::temp_dir().to_string_lossy().into_owned();
        for name in [
            "",
            ".",
            "..",
            "../escape",
            "a/b",
            "a\\b",
            ".git",
            "CON",
            "nul.txt",
            "COM1",
            "LPT9.log",
            "name.",
            " name",
            "name ",
            "bad:name",
            "line\nname",
        ] {
            assert!(
                create_workspace_directory(&parent, name).is_err(),
                "{name:?}"
            );
        }
        assert!(create_workspace_directory(".", "project").is_err());
    }

    #[test]
    fn new_workspace_creates_only_empty_directory_and_refuses_collisions() {
        let identity = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let parent = std::env::temp_dir().join(format!(
            "bifang-workspace-{}-{identity}",
            std::process::id()
        ));
        std::fs::create_dir(&parent).unwrap();
        let result = create_workspace_directory(&parent.to_string_lossy(), "My project").unwrap();
        assert_eq!(
            Path::new(&result),
            parent.canonicalize().unwrap().join("My project")
        );
        assert_eq!(std::fs::read_dir(&result).unwrap().count(), 0);
        std::fs::write(Path::new(&result).join("keep.txt"), "preserve").unwrap();
        assert!(create_workspace_directory(&parent.to_string_lossy(), "My project").is_err());
        std::fs::write(parent.join("file"), "preserve").unwrap();
        assert!(create_workspace_directory(&parent.to_string_lossy(), "file").is_err());
        assert!(
            create_workspace_directory(&parent.join("missing").to_string_lossy(), "project")
                .is_err()
        );
        assert!(
            create_workspace_directory(&parent.join("file").to_string_lossy(), "project").is_err()
        );
        assert_eq!(
            std::fs::read_to_string(Path::new(&result).join("keep.txt")).unwrap(),
            "preserve"
        );
        std::fs::remove_dir_all(parent).unwrap();
    }

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
