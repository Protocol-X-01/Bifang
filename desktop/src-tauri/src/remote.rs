use reqwest::{header, Client, Method, Url};
use serde::Deserialize;
use serde_json::Value;
use std::time::Duration;
use tauri::State;
use tokio::sync::Mutex;

pub struct RemoteState(Mutex<Option<Session>>);

impl Default for RemoteState {
    fn default() -> Self {
        Self(Mutex::new(None))
    }
}

struct Session {
    client: Client,
    origin: Url,
}

fn origin(value: &str) -> Result<Url, String> {
    let url = Url::parse(value).map_err(|_| "Enter an HTTPS service origin".to_string())?;
    if value.len() > 2048
        || url.scheme() != "https"
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
        || url.path() != "/"
    {
        return Err("Use only an HTTPS origin, without credentials, path or query".into());
    }
    Ok(url)
}

fn identity(value: &str) -> Result<&str, String> {
    if value.len() == 32
        && value
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        Ok(value)
    } else {
        Err("Invalid resource identity".into())
    }
}

#[derive(Deserialize)]
#[serde(tag = "operation", rename_all = "snake_case", deny_unknown_fields)]
pub enum Operation {
    List,
    Get { id: String },
    Patch { id: String },
    Submit { key: String, payload: Value },
    Decide { id: String, payload: Decision },
    Cancel { id: String },
    Forget { id: String },
    Project { id: String },
    ForgetProject { id: String },
}

#[derive(Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
pub struct Decision {
    action: Action,
    candidate_sha256: String,
    approved: bool,
}

#[derive(Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
enum Action {
    Writes,
    Check,
    Review,
    Stage,
    Apply,
}

async fn request(
    session: &Session,
    method: Method,
    path: &str,
    body: Option<Value>,
    key: Option<String>,
) -> Result<Value, String> {
    let url = session
        .origin
        .join(path)
        .map_err(|_| "Invalid service route".to_string())?;
    let mut builder = session.client.request(method, url);
    if let Some(payload) = body {
        if serde_json::to_vec(&payload)
            .map_err(|_| "Invalid JSON".to_string())?
            .len()
            > 400000
        {
            return Err("Selected source exceeds the request limit".into());
        }
        builder = builder.json(&payload);
    }
    if let Some(value) = key {
        builder = builder.header("Idempotency-Key", value);
    }
    let mut response = builder
        .send()
        .await
        .map_err(|_| "HTTPS request failed; refresh before retrying an action".to_string())?;
    if !response.status().is_success() {
        return Err(format!(
            "Remote service returned HTTP {}; refresh before retrying",
            response.status().as_u16()
        ));
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| "Incomplete response; refresh before retrying".to_string())?
    {
        if bytes.len() + chunk.len() > 2000000 {
            return Err("Remote response exceeds the client limit".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice(&bytes).map_err(|_| "Remote service returned invalid JSON".into())
}

#[tauri::command]
pub async fn remote_connect(
    endpoint: String,
    token: String,
    state: State<'_, RemoteState>,
) -> Result<Value, String> {
    let mut guard = state.0.lock().await;
    *guard = None;
    let endpoint = origin(&endpoint)?;
    if !(16..=512).contains(&token.len()) || !token.bytes().all(|byte| byte.is_ascii_graphic()) {
        return Err("Enter a valid client access token, not a provider key".into());
    }
    let mut authorization = header::HeaderValue::from_str(&format!("Bearer {token}"))
        .map_err(|_| "Invalid access token".to_string())?;
    authorization.set_sensitive(true);
    let mut headers = header::HeaderMap::new();
    headers.insert(header::AUTHORIZATION, authorization);
    let session = Session {
        origin: endpoint,
        client: Client::builder()
            .https_only(true)
            .redirect(reqwest::redirect::Policy::none())
            .no_proxy()
            .referer(false)
            .timeout(Duration::from_secs(20))
            .connect_timeout(Duration::from_secs(8))
            .default_headers(headers)
            .build()
            .map_err(|_| "Could not initialize HTTPS".to_string())?,
    };
    let schema = request(&session, Method::GET, "/v1/coding/schema", None, None).await?;
    if !schema.get("submission").is_some_and(Value::is_object)
        || !schema.get("decision").is_some_and(Value::is_object)
    {
        return Err("Service does not expose the coding contract".into());
    }
    *guard = Some(session);
    Ok(schema)
}

#[tauri::command]
pub async fn remote_disconnect(state: State<'_, RemoteState>) -> Result<(), String> {
    *state.0.lock().await = None;
    Ok(())
}

#[tauri::command]
pub async fn remote_operation(
    operation: Operation,
    state: State<'_, RemoteState>,
) -> Result<Value, String> {
    let guard = state.0.lock().await;
    let session = guard.as_ref().ok_or("Connect to a remote service first")?;
    let (method, path, body, key) = match operation {
        Operation::List => (Method::GET, "/v1/coding/jobs".into(), None, None),
        Operation::Submit { key, payload } => {
            if !(16..=128).contains(&key.len())
                || !key
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-')
            {
                return Err("Invalid submission identity".into());
            }
            if payload.get("sharing_confirmed") != Some(&Value::Bool(true)) {
                return Err("Confirm source sharing before submission".into());
            }
            (
                Method::POST,
                "/v1/coding/jobs".into(),
                Some(payload),
                Some(key),
            )
        }
        Operation::Get { id } => (
            Method::GET,
            format!("/v1/coding/jobs/{}", identity(&id)?),
            None,
            None,
        ),
        Operation::Patch { id } => (
            Method::GET,
            format!("/v1/coding/jobs/{}/patch", identity(&id)?),
            None,
            None,
        ),
        Operation::Cancel { id } => (
            Method::POST,
            format!("/v1/coding/jobs/{}/cancel", identity(&id)?),
            None,
            None,
        ),
        Operation::Forget { id } => (
            Method::DELETE,
            format!("/v1/coding/jobs/{}", identity(&id)?),
            None,
            None,
        ),
        Operation::Project { id } => (
            Method::GET,
            format!("/v1/coding/projects/{}", identity(&id)?),
            None,
            None,
        ),
        Operation::ForgetProject { id } => (
            Method::DELETE,
            format!("/v1/coding/projects/{}", identity(&id)?),
            None,
            None,
        ),
        Operation::Decide { id, payload } => {
            if payload.candidate_sha256.len() != 64
                || !payload
                    .candidate_sha256
                    .bytes()
                    .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
            {
                return Err("Invalid candidate digest".into());
            }
            (
                Method::POST,
                format!("/v1/coding/jobs/{}/decisions", identity(&id)?),
                Some(serde_json::to_value(payload).map_err(|_| "Invalid decision")?),
                None,
            )
        }
    };
    request(session, method, &path, body, key).await
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn origins_require_clean_https() {
        assert!(origin("https://203.0.113.1").is_ok());
        for value in [
            "http://example.com",
            "https://user:pass@example.com",
            "https://example.com/path",
            "https://example.com/?key=x",
            "https://example.com/#x",
        ] {
            assert!(origin(value).is_err());
        }
    }

    #[test]
    fn resources_and_operations_cannot_supply_arbitrary_routes() {
        assert!(identity(&"a".repeat(32)).is_ok());
        assert!(identity("../health").is_err());
        assert!(serde_json::from_value::<Operation>(
            serde_json::json!({"operation":"get", "id":"a", "url":"https://elsewhere"})
        )
        .is_err());
        assert!(serde_json::from_value::<Decision>(
            serde_json::json!({"action":"apply", "candidate_sha256":"a", "approved":"true"})
        )
        .is_err());
    }
}
