//! Bifang TUI - API Client
//!
//! Communicates with the bifang-server HTTP API.
//! Endpoint shape matches src/bifang/server.py (session flow v0.3.x):
//!   POST /sessions                     -> {session_id, workspace}
//!   POST /sessions/{id}/chat           -> {session_id, response, message_count, routing}
//!   GET  /sessions/{id}/diff           -> {diff, patch_sha256}
//!   POST /sessions/{id}/apply          -> {applied}
//!   GET  /sessions/{id}/approval       -> {approval_id, action} | {pending: false}
//!   POST /sessions/{id}/approval      -> {resolved: true}
//!   GET  /health                       -> {status: "ok"}

use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use urlencoding;
use serde_json::Value;

use crate::types::{FileEntry, ChatResponsePayload, SessionInfo, DiffResponsePayload, ApprovalRequest};

/// Wait for a single agent turn. Tool approvals can hold a turn for a long
/// time, so chat requests use their own generous timeout.
const CHAT_TIMEOUT_SECS: u64 = 900;

/// API client for bifang-server
pub struct ApiClient {
    client: Client,
}

impl ApiClient {
    pub fn new() -> Result<Self> {
        let client = Client::builder()
            .build()?;
        Ok(Self { client })
    }

    pub async fn health_check(&self, base_url: &str) -> Result<()> {
        let url = format!("{}/health", base_url);
        let resp = self.client.get(&url).timeout(Duration::from_secs(5)).send().await?;
        if resp.status().is_success() {
            Ok(())
        } else {
            anyhow::bail!("Health check failed: {}", resp.status());
        }
    }

    pub async fn create_session(&self, base_url: &str, workspace: &str) -> Result<SessionInfo> {
        let url = format!("{}/sessions", base_url);
        let req = CreateSessionRequest {
            workspace: workspace.to_string(),
        };
        let resp = self.client.post(&url).json(&req)
            .timeout(Duration::from_secs(30)).send().await?;
        let status = resp.status();
        if !status.is_success() {
            let detail = resp.text().await.unwrap_or_default();
            anyhow::bail!("Create session failed: {} ({})", status, truncate(&detail, 300));
        }
        let session = resp.json::<SessionInfo>().await?;
        Ok(session)
    }

    /// Send one agent turn. Runs until the model responds, which may include
    /// waiting on pending tool approvals resolved from a concurrent call.
    pub async fn send_chat(&self, base_url: &str, session_id: &str, prompt: &str) -> Result<ChatResponsePayload> {
        let url = format!("{}/sessions/{}/chat", base_url, urlencoding::encode(session_id));
        let req = ChatRequest { prompt: prompt.to_string() };
        let resp = self.client.post(&url).json(&req)
            .timeout(Duration::from_secs(CHAT_TIMEOUT_SECS)).send().await?;
        let status = resp.status();
        if !status.is_success() {
            let detail = resp.text().await.unwrap_or_default();
            anyhow::bail!("Chat failed: {} ({})", status, truncate(&detail, 300));
        }
        let chat_resp = resp.json::<ChatResponsePayload>().await?;
        Ok(chat_resp)
    }

    pub async fn get_diff(&self, base_url: &str, session_id: &str) -> Result<DiffResponsePayload> {
        let url = format!("{}/sessions/{}/diff", base_url, urlencoding::encode(session_id));
        let resp = self.client.get(&url).timeout(Duration::from_secs(30)).send().await?;
        let status = resp.status();
        if !status.is_success() {
            let detail = resp.text().await.unwrap_or_default();
            anyhow::bail!("Diff fetch failed: {} ({})", status, truncate(&detail, 300));
        }
        let diff = resp.json::<DiffResponsePayload>().await?;
        Ok(diff)
    }

    pub async fn apply_diff(&self, base_url: &str, session_id: &str, patch_sha256: &str) -> Result<bool> {
        let url = format!("{}/sessions/{}/apply", base_url, urlencoding::encode(session_id));
        let req = ApplyRequest { patch_sha256: patch_sha256.to_string() };
        let resp = self.client.post(&url).json(&req)
            .timeout(Duration::from_secs(60)).send().await?;
        let status = resp.status();
        if !status.is_success() {
            let detail = resp.text().await.unwrap_or_default();
            anyhow::bail!("Apply failed: {} ({})", status, truncate(&detail, 300));
        }
        let payload: ApplyResponse = resp.json().await?;
        Ok(payload.applied)
    }

    /// Poll for a pending tool approval. Returns None when nothing is pending
    /// or the server is unreachable.
    pub async fn poll_approval(&self, base_url: &str, session_id: &str) -> Option<ApprovalRequest> {
        let url = format!("{}/sessions/{}/approval", base_url, urlencoding::encode(session_id));
        let resp = self.client.get(&url).timeout(Duration::from_secs(5)).send().await.ok()?;
        if !resp.status().is_success() {
            return None;
        }
        let payload: ApprovalPollResponse = resp.json().await.ok()?;
        let decision = match payload {
            ApprovalPollResponse::Pending { approval_id, action } =>
                Some(ApprovalRequest { approval_id, action }),
            ApprovalPollResponse::None { .. } => None,
        };
        decision
    }

    pub async fn resolve_approval(&self, base_url: &str, session_id: &str, approval_id: &str, approved: bool) -> Result<bool> {
        let url = format!("{}/sessions/{}/approval", base_url, urlencoding::encode(session_id));
        let req = ResolveApprovalRequest { approval_id: approval_id.to_string(), approved };
        let resp = self.client.post(&url).json(&req)
            .timeout(Duration::from_secs(30)).send().await?;
        let status = resp.status();
        if !status.is_success() {
            let detail = resp.text().await.unwrap_or_default();
            anyhow::bail!("Approval resolve failed: {} ({})", status, truncate(&detail, 300));
        }
        let payload: ResolvedApprovalResponse = resp.json().await?;
        Ok(payload.resolved)
    }

    /// Workspace file listing. Returns Ok(None) when the server has no
    /// /files endpoint so the UI can fall back to local listing.
    pub async fn list_files(&self, base_url: &str, path: &str) -> Result<Option<Vec<FileEntry>>> {
        let url = format!("{}/files?path={}", base_url, urlencoding::encode(path));
        let resp = self.client.get(&url).timeout(Duration::from_secs(15)).send().await?;
        if resp.status() == reqwest::StatusCode::NOT_FOUND {
            return Ok(None);
        }
        let status = resp.status();
        if !status.is_success() {
            anyhow::bail!("Files list failed: {}", status);
        }
        let files = resp.json::<FilesResponse>().await?;
        Ok(Some(files.files))
    }
}

/// Chat request body (server forbids unknown fields)
#[derive(Serialize)]
struct ChatRequest {
    prompt: String,
}

/// Diff request bodies
#[derive(Serialize)]
struct ApplyRequest {
    patch_sha256: String,
}

#[derive(Serialize)]
struct ResolveApprovalRequest {
    approval_id: String,
    approved: bool,
}

#[derive(Serialize)]
struct CreateSessionRequest {
    workspace: String,
}

/// Approval GET payload (deserialized union)
#[derive(Deserialize)]
#[serde(untagged)]
enum ApprovalPollResponse {
    Pending { approval_id: String, action: String },
    None { pending: bool },
}

#[derive(Deserialize)]
struct ResolvedApprovalResponse {
    resolved: bool,
}

/// Files response
#[derive(Deserialize)]
struct FilesResponse {
    files: Vec<FileEntry>,
}

#[derive(Deserialize)]
struct ApplyResponse {
    applied: bool,
}

/// Keep error context readable inside the TUI status line
fn truncate(detail: &str, max: usize) -> String {
    let cleaned = detail.trim();
    if cleaned.chars().count() <= max {
        cleaned.to_string()
    } else {
        cleaned.chars().take(max).collect::<String>() + "..."
    }
}

/// Unused-typo guard helper mirrors serde Value re-use
pub type RoutingValue = Value;
