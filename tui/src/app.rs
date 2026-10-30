//! Bifang TUI - Application State
//!
//! Central state management for the TUI application.

use std::collections::VecDeque;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{mpsc, RwLock};
use anyhow::Result;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use chrono::{DateTime, Utc};
use uuid::Uuid;
use crossterm::event::{KeyEvent, KeyCode, KeyModifiers, MouseEvent};
use ratatui::Frame;

use crate::design::colors;
use crate::design::styles;
use crate::types::{AppMode, ServerStatus, ChatMessage, MessageRole, ModelInfo, TokenUsage, FileEntry, DiffHunk, DiffLine, DiffKind, TerminalSession, ApprovalRequest, SessionInfo, ChatResponsePayload};

/// How often the pending-approval endpoint is polled while a turn runs
const APPROVAL_POLL_INTERVAL: Duration = Duration::from_millis(1500);
/// How often the server health banner is refreshed
const SERVER_CHECK_INTERVAL: Duration = Duration::from_secs(30);

/// Main application state
pub struct App {
    pub mode: AppMode,
    pub server_status: ServerStatus,
    pub server_url: String,
    pub workspace_path: Option<String>,
    pub workspace_files: Vec<FileEntry>,
    pub selected_file: Option<usize>,
    pub chat_messages: Vec<ChatMessage>,
    pub chat_input: String,
    pub chat_scroll: usize,
    pub diff_hunks: Vec<DiffHunk>,
    pub diff_scroll: usize,
    pub terminal_sessions: Vec<TerminalSession>,
    pub active_terminal: Option<usize>,
    pub terminal_input: String,
    pub tabs: Vec<Tab>,
    pub active_tab: usize,
    pub approval_pending: Option<ApprovalRequest>,
    pub status_message: Option<String>,
    pub command_palette_open: bool,
    pub command_palette_query: String,
    pub command_palette_results: Vec<CommandAction>,
    pub should_quit: bool,
    // Live server session for the current conversation
    pub session_id: Option<String>,
    pub patch_sha256: Option<String>,
    pub chat_inflight: bool,
    pub last_approval_poll: Instant,
    pub last_server_check: Instant,
    pub last_diff_refresh: Instant,
    // Async handles
    event_tx: mpsc::UnboundedSender<AppEvent>,
    event_rx: mpsc::UnboundedReceiver<AppEvent>,
    api_client: Arc<crate::ApiClient>,
}

/// Application events for async handling
#[derive(Debug)]
pub enum AppEvent {
    ServerStatusChanged(ServerStatus),
    ChatMessageReceived(ChatMessage),
    DiffUpdated(Vec<DiffHunk>, String),
    FilesUpdated(Vec<FileEntry>),
    TerminalOutput(TerminalOutput),
    ApprovalRequested(ApprovalRequest),
    SessionCreated(String),
    SessionLost(String),
    ChatTurnDone,
    Error(String),
    StatusMessage(String),
}

/// Terminal output event
#[derive(Debug)]
pub struct TerminalOutput {
    pub session_id: Uuid,
    pub data: String,
}

/// Tab in the workspace
#[derive(Debug, Clone)]
pub enum Tab {
    Chat,
    Diff,
    Terminal,
    Files,
    Settings,
}

impl Tab {
    pub fn title(&self) -> &str {
        match self {
            Tab::Chat => "Chat",
            Tab::Diff => "Diff",
            Tab::Terminal => "Terminal",
            Tab::Files => "Files",
            Tab::Settings => "Settings",
        }
    }
}

/// Command palette action
#[derive(Debug, Clone)]
pub struct CommandAction {
    pub id: String,
    pub title: String,
    pub description: String,
    pub shortcut: Option<String>,
    pub action: CommandActionKind,
}

/// Command action kind
#[derive(Debug, Clone)]
pub enum CommandActionKind {
    NewChat,
    OpenWorkspace,
    NewWorkspace,
    ToggleTerminal,
    ToggleFiles,
    OpenSettings,
    ShowHelp,
    Quit,
    ApplyDiff,
    PauseApprovals,
    ResumeApprovals,
}

impl App {
    pub async fn new() -> Result<Self> {
        let (event_tx, event_rx) = mpsc::unbounded_channel();
        let api_client = Arc::new(crate::ApiClient::new()?);

        let server_url = std::env::var("BIFANG_TUI_SERVER").ok()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| "http://127.0.0.1:8000".to_string());
        let now = Instant::now();

        let mut app = Self {
            mode: AppMode::Workspace,
            server_status: ServerStatus::Stopped,
            server_url,
            workspace_path: None,
            workspace_files: Vec::new(),
            selected_file: None,
            chat_messages: Vec::new(),
            chat_input: String::new(),
            chat_scroll: 0,
            diff_hunks: Vec::new(),
            diff_scroll: 0,
            terminal_sessions: Vec::new(),
            active_terminal: None,
            terminal_input: String::new(),
            tabs: vec![Tab::Chat, Tab::Diff, Tab::Terminal, Tab::Files],
            active_tab: 0,
            approval_pending: None,
            status_message: None,
            command_palette_open: false,
            command_palette_query: String::new(),
            command_palette_results: Self::default_commands(),
            should_quit: false,
            session_id: None,
            patch_sha256: None,
            chat_inflight: false,
            last_approval_poll: now - APPROVAL_POLL_INTERVAL,
            last_server_check: now,
            last_diff_refresh: now,
            event_tx,
            event_rx,
            api_client,
        };

        // Try to connect to server
        app.check_server().await;

        Ok(app)
    }

    fn default_commands() -> Vec<CommandAction> {
        vec![
            CommandAction {
                id: "new-chat".into(),
                title: "New Chat".into(),
                description: "Start a fresh conversation".into(),
                shortcut: Some("Ctrl+N".into()),
                action: CommandActionKind::NewChat,
            },
            CommandAction {
                id: "open-workspace".into(),
                title: "Open Workspace".into(),
                description: "Open an existing project directory".into(),
                shortcut: Some("Ctrl+O".into()),
                action: CommandActionKind::OpenWorkspace,
            },
            CommandAction {
                id: "new-workspace".into(),
                title: "New Workspace".into(),
                description: "Create a new project".into(),
                shortcut: Some("Ctrl+Shift+N".into()),
                action: CommandActionKind::NewWorkspace,
            },
            CommandAction {
                id: "toggle-terminal".into(),
                title: "Toggle Terminal".into(),
                description: "Show/hide terminal panel".into(),
                shortcut: Some("Ctrl+`".into()),
                action: CommandActionKind::ToggleTerminal,
            },
            CommandAction {
                id: "toggle-files".into(),
                title: "Toggle File Explorer".into(),
                description: "Show/hide file explorer".into(),
                shortcut: Some("Ctrl+B".into()),
                action: CommandActionKind::ToggleFiles,
            },
            CommandAction {
                id: "apply-diff".into(),
                title: "Apply Changes".into(),
                description: "Apply reviewed diff to project".into(),
                shortcut: Some("Ctrl+K".into()),
                action: CommandActionKind::ApplyDiff,
            },
            CommandAction {
                id: "quit".into(),
                title: "Quit".into(),
                description: "Exit Bifang".into(),
                shortcut: Some("Ctrl+Q".into()),
                action: CommandActionKind::Quit,
            },
        ]
    }

    /// Handle key events
    pub async fn handle_key(&mut self, key: KeyEvent) -> Result<bool> {
        if self.command_palette_open {
            return self.handle_command_palette_key(key).await;
        }

        if let Some(approval) = &self.approval_pending {
            return self.handle_approval_key(key, approval.clone()).await;
        }

        match key.code {
            KeyCode::Char('q') | KeyCode::Char('Q') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.should_quit = true;
                return Ok(true);
            }
            KeyCode::Char('p') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.command_palette_open = true;
                self.command_palette_query.clear();
                self.update_command_results();
            }
            KeyCode::Char('n') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.new_chat().await?;
            }
            KeyCode::Char('o') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.open_workspace().await?;
            }
            KeyCode::Char('`') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.toggle_terminal().await?;
            }
            KeyCode::Char('b') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.toggle_files();
            }
            KeyCode::Char('\n') | KeyCode::Enter if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.apply_diff().await?;
            }
            // Ctrl+Enter reaches many terminals as a bare Enter/LF, so offer
            // Ctrl+K as a reliable apply alias (the command palette covers
            // any other binding gap).
            KeyCode::Char('k') | KeyCode::Char('K') if key.modifiers.contains(KeyModifiers::CONTROL) => {
                self.apply_diff().await?;
            }
            KeyCode::Tab => {
                self.next_tab();
            }
            KeyCode::BackTab => {
                self.prev_tab();
            }
            KeyCode::Esc => {
                self.esc_pressed().await?;
            }
            _ => {
                self.handle_mode_key(key).await?;
            }
        }
        Ok(false)
    }

    async fn handle_command_palette_key(&mut self, key: KeyEvent) -> Result<bool> {
        match key.code {
            KeyCode::Esc => {
                self.command_palette_open = false;
            }
            KeyCode::Char(c) => {
                self.command_palette_query.push(c);
                self.update_command_results();
            }
            KeyCode::Backspace => {
                self.command_palette_query.pop();
                self.update_command_results();
            }
            KeyCode::Down => {
                // Navigate results
            }
            KeyCode::Up => {
                // Navigate results
            }
            KeyCode::Enter => {
                if let Some(action) = self.command_palette_results.first() {
                    self.execute_command(action.clone()).await?;
                    self.command_palette_open = false;
                }
            }
            _ => {}
        }
        Ok(false)
    }

    async fn handle_approval_key(&mut self, key: KeyEvent, _approval: ApprovalRequest) -> Result<bool> {
        match key.code {
            KeyCode::Char('y') | KeyCode::Char('Y') => {
                self.approve_action(true).await?;
            }
            KeyCode::Char('n') | KeyCode::Char('N') => {
                self.approve_action(false).await?;
            }
            KeyCode::Esc => {
                self.approve_action(false).await?;
            }
            _ => {}
        }
        Ok(false)
    }

async fn handle_mode_key(&mut self, key: KeyEvent) -> Result<bool> {
        let result = match self.mode {
            AppMode::Workspace => self.handle_workspace_key(key).await?,
            AppMode::Terminal => self.handle_terminal_key(key).await?,
            AppMode::Files => self.handle_files_key(key).await?,
            AppMode::Settings => false,
            AppMode::CommandPalette => false,
        };

        Ok(result)
    }

    async fn handle_workspace_key(&mut self, key: KeyEvent) -> Result<bool> {
        match key.code {
            KeyCode::Char(c) => {
                self.chat_input.push(c);
            }
            KeyCode::Backspace => {
                self.chat_input.pop();
            }
            KeyCode::Enter if !key.modifiers.contains(KeyModifiers::SHIFT) => {
                if !self.chat_input.trim().is_empty() {
                    self.send_chat_message().await?;
                }
            }
            KeyCode::Up => {
                if self.chat_scroll > 0 {
                    self.chat_scroll -= 1;
                }
            }
            KeyCode::Down => {
                self.chat_scroll = self.chat_scroll.saturating_add(1);
            }
            KeyCode::PageUp => {
                self.chat_scroll = self.chat_scroll.saturating_sub(10);
            }
            KeyCode::PageDown => {
                self.chat_scroll = self.chat_scroll.saturating_add(10);
            }
            _ => {}
        }
        Ok(false)
    }

    async fn handle_terminal_key(&mut self, key: KeyEvent) -> Result<bool> {
        if let Some(idx) = self.active_terminal {
            if idx < self.terminal_sessions.len() {
                let _session = &mut self.terminal_sessions[idx];
                match key.code {
                    KeyCode::Char(c) => {
                        self.terminal_input.push(c);
                    }
                    KeyCode::Backspace => {
                        self.terminal_input.pop();
                    }
                    KeyCode::Enter => {
                        self.send_terminal_command().await?;
                    }
                    KeyCode::Up => {}
                    KeyCode::Down => {}
                    _ => {}
                }
            }
        }
        Ok(false)
    }

    async fn handle_files_key(&mut self, key: KeyEvent) -> Result<bool> {
        match key.code {
            KeyCode::Up => {
                if let Some(sel) = self.selected_file {
                    if sel > 0 {
                        self.selected_file = Some(sel - 1);
                    }
                } else if !self.workspace_files.is_empty() {
                    self.selected_file = Some(0);
                }
            }
            KeyCode::Down => {
                if let Some(sel) = self.selected_file {
                    if sel + 1 < self.workspace_files.len() {
                        self.selected_file = Some(sel + 1);
                    }
                } else if !self.workspace_files.is_empty() {
                    self.selected_file = Some(0);
                }
            }
            KeyCode::Enter => {
                if let Some(sel) = self.selected_file {
                    if sel < self.workspace_files.len() {
                        let _file = &self.workspace_files[sel];
                    }
                }
            }
            _ => {}
        }
        Ok(false)
    }

    fn update_command_results(&mut self) {
        let query = self.command_palette_query.to_lowercase();
        self.command_palette_results = Self::default_commands()
            .into_iter()
            .filter(|cmd| {
                cmd.title.to_lowercase().contains(&query)
                    || cmd.description.to_lowercase().contains(&query)
            })
            .collect();
    }

    async fn execute_command(&mut self, action: CommandAction) -> Result<()> {
        match action.action {
            CommandActionKind::NewChat => self.new_chat().await?,
            CommandActionKind::OpenWorkspace => self.open_workspace().await?,
            CommandActionKind::NewWorkspace => self.new_workspace().await?,
            CommandActionKind::ToggleTerminal => self.toggle_terminal().await?,
            CommandActionKind::ToggleFiles => self.toggle_files(),
            CommandActionKind::OpenSettings => self.open_settings(),
            CommandActionKind::ShowHelp => {}
            CommandActionKind::Quit => self.should_quit = true,
            CommandActionKind::ApplyDiff => self.apply_diff().await?,
            CommandActionKind::PauseApprovals => self.pause_approvals().await?,
            CommandActionKind::ResumeApprovals => self.resume_approvals().await?,
        }
        Ok(())
    }

    async fn new_chat(&mut self) -> Result<()> {
        self.chat_messages.clear();
        self.chat_input.clear();
        self.chat_scroll = 0;
        self.diff_hunks.clear();
        self.session_id = None;
        self.patch_sha256 = None;
        self.set_status("New chat started");
        Ok(())
    }

    async fn open_workspace(&mut self) -> Result<()> {
        let path = std::env::current_dir()?.to_string_lossy().to_string();
        self.workspace_path = Some(path.clone());
        self.load_workspace_files(&path).await?;
        self.set_status(&format!("Opened workspace: {}", path));
        Ok(())
    }

    async fn new_workspace(&mut self) -> Result<()> {
        self.set_status("New workspace created");
        Ok(())
    }

    async fn toggle_terminal(&mut self) -> Result<()> {
        if self.active_terminal.is_some() {
            self.active_terminal = None;
            self.mode = AppMode::Workspace;
        } else {
            self.create_terminal().await?;
        }
        Ok(())
    }

    async fn create_terminal(&mut self) -> Result<()> {
        let session = TerminalSession {
            id: Uuid::new_v4(),
            cwd: self.workspace_path.clone().unwrap_or_else(|| std::env::current_dir().unwrap().to_string_lossy().to_string()),
            cols: 80,
            rows: 24,
            buffer: VecDeque::new(),
            cursor_x: 0,
            cursor_y: 0,
        };
        self.terminal_sessions.push(session);
        self.active_terminal = Some(self.terminal_sessions.len() - 1);
        self.mode = AppMode::Terminal;
        self.set_status("Terminal opened");
        Ok(())
    }

    fn toggle_files(&mut self) {
        if self.mode == AppMode::Files {
            self.mode = AppMode::Workspace;
        } else {
            self.mode = AppMode::Files;
        }
    }

    fn open_settings(&mut self) {
        self.mode = AppMode::Settings;
    }

    async fn apply_diff(&mut self) -> Result<()> {
        if self.chat_inflight {
            self.set_status("Wait for the current agent turn to finish");
            return Ok(());
        }
        if self.diff_hunks.is_empty() {
            self.set_status("No changes to apply");
            return Ok(());
        }
        let Some(session) = self.session_id.clone() else {
            self.set_status("No changes to apply");
            return Ok(());
        };
        let Some(sha) = self.patch_sha256.clone() else {
            self.set_status("No changes to apply");
            return Ok(());
        };
        self.set_status("Applying changes...");
        match self.api_client.apply_diff(&self.server_url, &session, &sha).await {
            Ok(true) => {
                self.set_status("Changes applied to the workspace");
                self.patch_sha256 = None;
                self.refresh_diff(&session).await;
            }
            Ok(false) => self.set_status("Changes were already applied"),
            Err(e) => self.set_status(&format!("Error: {}", e)),
        }
        Ok(())
    }

    async fn pause_approvals(&mut self) -> Result<()> {
        self.set_status("Auto-approvals paused");
        Ok(())
    }

    async fn resume_approvals(&mut self) -> Result<()> {
        self.set_status("Auto-approvals resumed");
        Ok(())
    }

    async fn esc_pressed(&mut self) -> Result<()> {
        if self.mode == AppMode::Terminal {
            self.active_terminal = None;
            self.mode = AppMode::Workspace;
        } else if self.mode == AppMode::Files {
            self.mode = AppMode::Workspace;
        } else if self.mode == AppMode::Settings {
            self.mode = AppMode::Workspace;
        }
        Ok(())
    }

    fn next_tab(&mut self) {
        self.active_tab = (self.active_tab + 1) % self.tabs.len();
    }

    fn prev_tab(&mut self) {
        if self.active_tab == 0 {
            self.active_tab = self.tabs.len() - 1;
        } else {
            self.active_tab -= 1;
        }
    }

    async fn send_chat_message(&mut self) -> Result<()> {
        let content = self.chat_input.trim().to_string();
        if content.is_empty() {
            return Ok(());
        }
        if self.chat_inflight {
            self.set_status("Agent is working - wait for the current turn");
            return Ok(());
        }
        if content.chars().count() > 20000 {
            self.set_status("Prompt too long for the server (20,000 characters)");
            return Ok(());
        }

        let msg = ChatMessage {
            id: Uuid::new_v4(),
            role: MessageRole::User,
            content: content.clone(),
            timestamp: Utc::now(),
            model_info: None,
        };
        self.chat_messages.push(msg);
        self.chat_input.clear();
        self.chat_inflight = true;
        self.set_status("Agent working... press Esc later to keep using the UI");

        let api = Arc::clone(&self.api_client);
        let server_url = self.server_url.clone();
        let sender = self.event_tx.clone();
        let workspace = self.workspace_path.clone().unwrap_or_else(|| {
            std::env::current_dir().map(|p| p.to_string_lossy().to_string()).unwrap_or_else(|_| ".".to_string())
        });
        let known_session = self.session_id.clone();

        tokio::spawn(async move {
            // Reuse the shared session or create a fresh one on the server
            let session: SessionInfo = match known_session {
                Some(shared) => SessionInfo { session_id: shared, workspace: workspace.clone() },
                None => match api.create_session(&server_url, &workspace).await {
                    Ok(info) => {
                        let _ = sender.send(AppEvent::SessionCreated(info.session_id.clone()));
                        info
                    }
                    Err(e) => {
                        let _ = sender.send(AppEvent::Error(e.to_string()));
                        let _ = sender.send(AppEvent::ChatTurnDone);
                        return;
                    }
                },
            };
            let session_id = session.session_id.clone();

            let result = api.send_chat(&server_url, &session_id, &content).await;
            let turn_id = Uuid::new_v4();
            match result {
                Ok(payload) => {
                    let model_info = payload.routing.first().and_then(|entry| {
                        let provider = entry.get("provider")?.as_str()?;
                        let model = entry.get("model")?.as_str()?;
                        let task_type = entry.get("task_type").and_then(Value::as_str).unwrap_or("pinned");
                        let usage = entry.get("usage").map(|u| TokenUsage {
                            prompt: u.get("prompt").and_then(Value::as_u64).unwrap_or(0),
                            completion: u.get("completion").and_then(Value::as_u64).unwrap_or(0),
                        });
                        Some(ModelInfo { provider: provider.to_string(), model: model.to_string(), task_type: task_type.to_string(), tokens: usage })
                    });
                    let _ = sender.send(AppEvent::ChatMessageReceived(ChatMessage {
                        id: turn_id,
                        role: MessageRole::Assistant,
                        content: payload.response.clone(),
                        timestamp: Utc::now(),
                        model_info,
                    }));
                    let _ = sender.send(AppEvent::StatusMessage(format!("Agent responded · session {}", session_id)));
                    if let Ok(diff_payload) = api.get_diff(&server_url, &session_id).await {
                        let hunks = parse_unified_diff(&diff_payload.diff);
                        let _ = sender.send(AppEvent::DiffUpdated(hunks, diff_payload.patch_sha256));
                    }
                }
                Err(e) => {
                    let text = e.to_string();
                    if text.contains("404") && text.contains("Chat failed") {
                        // Session expired server-side; let the next message recreate it
                        let _ = sender.send(AppEvent::SessionLost(session_id));
                    }
                    let _ = sender.send(AppEvent::Error(text));
                }
            }
            let _ = sender.send(AppEvent::StatusMessage("Agent finished".to_string()));
            let _ = sender.send(AppEvent::ChatTurnDone);
        });

        Ok(())
    }

    async fn send_terminal_command(&mut self) -> Result<()> {
        self.terminal_input.clear();
        Ok(())
    }

    async fn approve_action(&mut self, approved: bool) -> Result<bool> {
        let Some(approval) = self.approval_pending.take() else {
            return Ok(false);
        };
        let Some(session) = self.session_id.clone() else {
            self.set_status("Approval expired - session missing");
            return Ok(false);
        };
        match self.api_client.resolve_approval(&self.server_url, &session, &approval.approval_id, approved).await {
            Ok(true) => self.set_status(if approved { "Approved - agent continues" } else { "Denied - agent continues without it" }),
            Ok(false) => self.set_status("Approval was no longer valid"),
            Err(e) => self.set_status(&format!("Error: {}", e)),
        }
        Ok(false)
    }

    async fn load_workspace_files(&mut self, path: &str) -> Result<()> {
        match self.api_client.list_files(&self.server_url, path).await {
            Ok(Some(files)) => self.workspace_files = files,
            Ok(None) => {
                // Server has no /files endpoint: list the local folder instead
                let mut entries = Vec::new();
                if let Ok(children) = std::fs::read_dir(path) {
                    for child in children.flatten() {
                        let child_path = child.path();
                        let Ok(meta) = child.metadata() else { continue };
                        entries.push(FileEntry {
                            path: child_path.to_string_lossy().to_string(),
                            name: child_path.file_name().unwrap_or_default().to_string_lossy().to_string(),
                            is_dir: meta.is_dir(),
                            size: if meta.is_file() { Some(meta.len()) } else { None },
                            modified: meta.modified().ok().map(DateTime::<Utc>::from),
                        });
                    }
                }
                entries.sort_by(|a, b| b.is_dir.cmp(&a.is_dir).then_with(|| a.name.cmp(&b.name)));
                self.workspace_files = entries;
                self.set_status("Server file listing unavailable - showing the local folder");
            }
            Err(e) => self.set_status(&format!("Error: {}", e)),
        }
        Ok(())
    }

    async fn check_server(&mut self) {
        self.last_server_check = Instant::now();
        match self.api_client.health_check(&self.server_url).await {
            Ok(_) => {
                self.server_status = ServerStatus::Running;
                self.set_status("Server connected");
            }
            Err(_) => {
                self.server_status = ServerStatus::Error;
                self.set_status("Server not running (Bifang TUI expects it on 127.0.0.1:8000)");
            }
        }
    }

    pub async fn tick(&mut self) -> Result<()> {
        while let Ok(event) = self.event_rx.try_recv() {
            match event {
                AppEvent::ServerStatusChanged(status) => self.server_status = status,
                AppEvent::ChatMessageReceived(msg) => self.chat_messages.push(msg),
                AppEvent::DiffUpdated(hunks, sha256) => {
                    self.diff_hunks = hunks;
                    self.patch_sha256 = Some(sha256);
                }
                AppEvent::FilesUpdated(files) => self.workspace_files = files,
                AppEvent::SessionCreated(id) => self.session_id = Some(id),
                AppEvent::SessionLost(_) => self.session_id = None,
                AppEvent::ChatTurnDone => self.chat_inflight = false,
                AppEvent::TerminalOutput(output) => {
                    if let Some(idx) = self.active_terminal {
                        if idx < self.terminal_sessions.len() {
                            self.terminal_sessions[idx].buffer.push_back(output.data);
                        }
                    }
                }
                AppEvent::ApprovalRequested(req) => self.approval_pending = Some(req),
                AppEvent::Error(msg) => self.set_status(&format!("Error: {}", msg)),
                AppEvent::StatusMessage(msg) => self.set_status(&msg),
            }
        }

        self.poll_server().await?;

        Ok(())
    }

    async fn poll_server(&mut self) -> Result<()> {
        // Refresh the connection banner on a slow cadence
        if self.last_server_check.elapsed() >= SERVER_CHECK_INTERVAL {
            self.check_server().await;
        }

        // While an agent turn runs, watch for pending tool approvals
        if self.chat_inflight
            && self.approval_pending.is_none()
            && self.last_approval_poll.elapsed() >= APPROVAL_POLL_INTERVAL
        {
            self.last_approval_poll = Instant::now();
            if let Some(session) = self.session_id.clone() {
                if let Some(approval) = self.api_client.poll_approval(&self.server_url, &session).await {
                    self.approval_pending = Some(approval.clone());
                    self.set_status("Permission requested - Y to allow, N/Esc to deny");
                }
            }
        }

        Ok(())
    }

    fn set_status(&mut self, msg: &str) {
        self.status_message = Some(msg.to_string());
    }

    /// Refresh the workspace diff for a live session and remember its hash
    async fn refresh_diff(&mut self, session: &str) {
        match self.api_client.get_diff(&self.server_url, session).await {
            Ok(payload) => {
                self.diff_hunks = parse_unified_diff(&payload.diff);
                self.patch_sha256 = Some(payload.patch_sha256);
            }
            Err(_) => {
                self.diff_hunks.clear();
                self.patch_sha256 = None;
            }
        }
    }

    pub async fn handle_mouse(&mut self, _mouse: MouseEvent) -> Result<()> {
        Ok(())
    }

    pub fn draw(&self, f: &mut Frame) {
        crate::components::draw_app(f, self);
    }
}

/// Parse a unified diff into hunk/line structures for the diff tab
pub fn parse_unified_diff(diff: &str) -> Vec<DiffHunk> {
    let mut hunks = Vec::new();
    let mut current: Option<DiffHunk> = None;
    let mut old_line = 0u32;
    let mut new_line = 0u32;

    for raw_line in diff.lines() {
        if raw_line.is_empty() || (raw_line.starts_with("\\ No newline")) {
            continue;
        }

        let kind: DiffKind;
        let content: String;

        if let Some(rest) = raw_line.strip_prefix("@@") {
            // Example header: @@ -12,3 +12,4 @@ context
            let mut old_start = 0u32;
            let mut new_start = 0u32;
            if let Some((old_spec, new_spec)) = extract_range_specs(rest) {
                old_start = old_spec.0;
                new_start = new_spec.0;
            }
            old_line = old_start;
            new_line = new_start;
            if let Some(hunk) = current.take() {
                hunks.push(hunk);
            }
            current = Some(DiffHunk {
                old_start,
                old_lines: 0,
                new_start,
                new_lines: 0,
                lines: Vec::new(),
            });
            continue;
        } else if let Some(rest) = raw_line.strip_prefix('+') {
            kind = DiffKind::Added;
            content = rest.to_string();
            new_line += 1;
        } else if let Some(rest) = raw_line.strip_prefix('-') {
            kind = DiffKind::Removed;
            content = rest.to_string();
            old_line += 1;
        } else {
            kind = DiffKind::Context;
            content = raw_line.strip_prefix(' ').unwrap_or(raw_line).to_string();
        }

        if let Some(hunk) = current.as_mut() {
            let (old_num, new_num) = match kind {
                DiffKind::Added => (None, Some(new_line)),
                DiffKind::Removed => (Some(old_line), None),
                DiffKind::Context => (Some(old_line), Some(new_line)),
            };
            hunk.lines.push(DiffLine { kind, content, old_line_num: old_num, new_line_num: new_num });
        }
    }
    if let Some(hunk) = current.take() {
        hunks.push(hunk);
    }
    hunks
}

/// Extract "(-start,-count, +start,+count)" specs from a hunk header
fn extract_range_specs(header: &str) -> Option<((u32, u32), (u32, u32))> {
    let mut specs = Vec::new();
    let mut parts = header.split_whitespace();
    while let Some(part) = parts.next() {
        let spec = part.trim_start_matches(['-', '+']);
        let (start_str, count_str) = spec.split_once(',').unwrap_or((spec, "1"));
        let start = start_str.parse::<u32>().ok()?;
        let count = count_str.parse::<u32>().unwrap_or(1);
        specs.push((start, count));
        if specs.len() == 2 {
            break;
        }
    }
    if specs.len() == 2 {
        Some((specs[0], specs[1]))
    } else {
        None
    }
}