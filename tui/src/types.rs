//! Bifang TUI - Shared Types
//!
//! Common types shared between modules to avoid circular dependencies.

use std::collections::VecDeque;
use serde::{Deserialize, Serialize};
use chrono::{DateTime, Utc};
use uuid::Uuid;

/// Application modes
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AppMode {
    /// Main coding workspace
    Workspace,
    /// Terminal panel
    Terminal,
    /// File explorer
    Files,
    /// Settings
    Settings,
    /// Command palette
    CommandPalette,
}

/// Server connection status
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ServerStatus {
    Stopped,
    Starting,
    Running,
    Error,
}

/// Message in the chat/conversation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ChatMessage {
    pub id: Uuid,
    pub role: MessageRole,
    pub content: String,
    pub timestamp: DateTime<Utc>,
    pub model_info: Option<ModelInfo>,
}

/// Message role
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum MessageRole {
    User,
    Assistant,
    System,
    Tool,
}

/// Model information for routing receipts
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelInfo {
    pub provider: String,
    pub model: String,
    pub task_type: String,
    pub tokens: Option<TokenUsage>,
}

/// Token usage
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenUsage {
    pub prompt: u64,
    pub completion: u64,
}

/// Workspace file entry
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileEntry {
    pub path: String,
    pub name: String,
    pub is_dir: bool,
    pub size: Option<u64>,
    pub modified: Option<DateTime<Utc>>,
}

/// Diff hunk for unified diff view
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiffHunk {
    pub old_start: u32,
    pub old_lines: u32,
    pub new_start: u32,
    pub new_lines: u32,
    pub lines: Vec<DiffLine>,
}

/// Single diff line
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiffLine {
    pub kind: DiffKind,
    pub content: String,
    pub old_line_num: Option<u32>,
    pub new_line_num: Option<u32>,
}

/// Diff line kind
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum DiffKind {
    Added,
    Removed,
    Context,
}

/// Terminal session
#[derive(Debug, Clone)]
pub struct TerminalSession {
    pub id: Uuid,
    pub cwd: String,
    pub cols: u16,
    pub rows: u16,
    pub buffer: VecDeque<String>,
    pub cursor_x: u16,
    pub cursor_y: u16,
}

/// Approval request from server
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApprovalRequest {
    pub approval_id: String,
    pub action: String,
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

/// Routing receipt
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RoutingReceipt {
    pub provider: String,
    pub model: String,
    pub task_type: String,
    pub usage: Option<TokenUsage>,
}

/// Server chat response payload (src/bifang/server.py ChatResponse)
#[derive(Debug, Clone, Deserialize)]
pub struct ChatResponsePayload {
    pub session_id: String,
    pub response: String,
    pub message_count: u64,
    #[serde(default)]
    pub routing: Vec<serde_json::Value>,
}

/// Server session payload (SessionResponse)
#[derive(Debug, Clone, Deserialize)]
pub struct SessionInfo {
    pub session_id: String,
    #[serde(default)]
    pub workspace: String,
}

/// Server diff payload
#[derive(Debug, Clone, Deserialize)]
pub struct DiffResponsePayload {
    pub diff: String,
    pub patch_sha256: String,
}