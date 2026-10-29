//! Bifang TUI - API Client
//!
//! Communicates with the bifang-server sidecar via HTTP.

use anyhow::Result;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use std::time::Duration;
use urlencoding;

use crate::types::{FileEntry, RoutingReceipt, TokenUsage};

/// API client for bifang-server
pub struct ApiClient {
    client: Client,
}

impl ApiClient {
    pub fn new() -> Result<Self> {
        let client = Client::builder()
            .timeout(Duration::from_secs(30))
            .build()?;
        Ok(Self { client })
    }

    pub async fn health_check(&self, base_url: &str) -> Result<()> {
        let url = format!("{}/health", base_url);
        let resp = self.client.get(&url).send().await?;
        if resp.status().is_success() {
            Ok(())
        } else {
            anyhow::bail!("Health check failed: {}", resp.status());
        }
    }

    pub async fn send_chat(&self, base_url: &str, prompt: &str) -> Result<ChatResponse> {
        let url = format!("{}/chat", base_url);
        let req = ChatRequest {
            prompt: prompt.to_string(),
            model: None,
            max_steps: 12,
        };
        let resp = self.client.post(&url).json(&req).send().await?;
        let chat_resp = resp.json::<ChatResponse>().await?;
        Ok(chat_resp)
    }

    pub async fn list_files(&self, base_url: &str, path: &str) -> Result<Vec<FileEntry>> {
        let url = format!("{}/files?path={}", base_url, urlencoding::encode(path));
        let resp = self.client.get(&url).send().await?;
        let files = resp.json::<FilesResponse>().await?;
        Ok(files.files)
    }

    pub async fn get_diff(&self, base_url: &str, session_id: &str) -> Result<DiffResponse> {
        let url = format!("{}/sessions/{}/diff", base_url, session_id);
        let resp = self.client.get(&url).send().await?;
        let diff = resp.json::<DiffResponse>().await?;
        Ok(diff)
    }

    pub async fn apply_diff(&self, base_url: &str, session_id: &str, patch_sha256: &str) -> Result<ApplyResponse> {
        let url = format!("{}/sessions/{}/apply", base_url, session_id);
        let req = ApplyRequest { patch_sha256: patch_sha256.to_string() };
        let resp = self.client.post(&url).json(&req).send().await?;
        let apply = resp.json::<ApplyResponse>().await?;
        Ok(apply)
    }

    pub async fn create_session(&self, base_url: &str, workspace: &str) -> Result<SessionResponse> {
        let url = format!("{}/sessions", base_url);
        let req = CreateSessionRequest {
            workspace: workspace.to_string(),
            max_steps: 12,
        };
        let resp = self.client.post(&url).json(&req).send().await?;
        let session = resp.json::<SessionResponse>().await?;
        Ok(session)
    }
}

/// Chat request
#[derive(Serialize)]
struct ChatRequest {
    prompt: String,
    model: Option<String>,
    max_steps: u32,
}

/// Chat response
#[derive(Deserialize, Debug)]
pub struct ChatResponse {
    pub response: String,
    pub session_id: String,
    pub routing: Vec<RoutingReceipt>,
    pub diff: Option<String>,
}

/// Files response
#[derive(Deserialize)]
struct FilesResponse {
    files: Vec<FileEntry>,
}

/// Diff response
#[derive(Deserialize, Debug)]
pub struct DiffResponse {
    pub diff: String,
    pub patch_sha256: String,
}

/// Apply request
#[derive(Serialize)]
struct ApplyRequest {
    patch_sha256: String,
}

/// Apply response
#[derive(Deserialize, Debug)]
pub struct ApplyResponse {
    pub success: bool,
    pub message: String,
}

/// Create session request
#[derive(Serialize)]
struct CreateSessionRequest {
    workspace: String,
    max_steps: u32,
}

/// Session response
#[derive(Deserialize, Debug)]
pub struct SessionResponse {
    pub session_id: String,
    pub workspace: String,
}