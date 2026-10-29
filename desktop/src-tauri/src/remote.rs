use reqwest::{header, Client, Method, Url};
use serde::Deserialize;
use serde_json::Value;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};
use tauri::State;
use tokio::sync::Mutex;

pub struct RemoteState(
    Mutex<Option<Session>>,
    Mutex<Option<PendingPair>>,
    AtomicU64,
);

impl Default for RemoteState {
    fn default() -> Self {
        Self(Mutex::new(None), Mutex::new(None), AtomicU64::new(1))
    }
}

struct Session {
    client: Client,
    origin: Url,
    pair_attempt: Option<u64>,
}

struct PendingPair {
    session: Session,
    proof: String,
    attempt: u64,
    expires: Instant,
    next_poll: Instant,
    transport_failures: u8,
}

enum PairRequestError {
    Transport(reqwest::Error),
    Invalid(String),
}

impl From<String> for PairRequestError {
    fn from(message: String) -> Self {
        Self::Invalid(message)
    }
}

impl From<&str> for PairRequestError {
    fn from(message: &str) -> Self {
        Self::Invalid(message.into())
    }
}

impl From<PairRequestError> for String {
    fn from(error: PairRequestError) -> Self {
        match error {
            PairRequestError::Invalid(message) => message,
            PairRequestError::Transport(error) if error.is_timeout() =>
                "Pairing connection timed out. Check the network and try a new code.".into(),
            PairRequestError::Transport(error) if error.is_connect() =>
                "Could not establish the pairing HTTPS connection. Check network access and device time.".into(),
            PairRequestError::Transport(_) =>
                "Pairing connection interrupted. Start a new code after checking connectivity.".into(),
        }
    }
}

fn defer_pair_transport_failure(pair: &mut PendingPair) -> bool {
    pair.transport_failures += 1;
    if pair.transport_failures > 3 || Instant::now() >= pair.expires {
        return false;
    }
    pair.next_poll = Instant::now() + Duration::from_secs(5);
    true
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PairStart {
    device_code: String,
    user_code: String,
    expires_in: u64,
    interval: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PairToken {
    access_token: String,
    token_type: String,
    expires_in: u64,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PairFailure {
    error: String,
    interval: u64,
}

#[derive(Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
pub struct PairDecision {
    user_code: String,
    authenticator_code: String,
    approved: bool,
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
    AuthSession,
    Models { provider: String },
    PairedDevices,
    ApproveDevice { payload: PairDecision },
    RevokeDevice { id: String },
}

fn opaque(value: &str) -> bool {
    value.len() == 43
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-')
}

fn user_code(value: &str) -> bool {
    value.len() == 9
        && value.as_bytes()[4] == b'-'
        && value.bytes().enumerate().all(|(position, byte)| {
            position == 4 || b"ABCDEFGHJKLMNPQRSTUVWXYZ23456789".contains(&byte)
        })
}

fn https_session(
    endpoint: Url,
    token: Option<&str>,
    pair_attempt: Option<u64>,
) -> Result<Session, String> {
    let mut headers = header::HeaderMap::new();
    if let Some(token) = token {
        if !(16..=512).contains(&token.len()) || !token.bytes().all(|byte| byte.is_ascii_graphic())
        {
            return Err("Enter a valid client access token, not a provider key".into());
        }
        let mut authorization = header::HeaderValue::from_str(&format!("Bearer {token}"))
            .map_err(|_| "Invalid access token".to_string())?;
        authorization.set_sensitive(true);
        headers.insert(header::AUTHORIZATION, authorization);
    }
    Ok(Session {
        origin: endpoint,
        pair_attempt,
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
    })
}

async fn pair_request(session: &Session, path: &str, body: Value) -> Result<(bool, Value), PairRequestError> {
    let url = session
        .origin
        .join(path)
        .map_err(|_| "Invalid pairing route".to_string())?;
    let mut response = session
        .client
        .post(url)
        .json(&body)
        .send()
        .await
        .map_err(PairRequestError::Transport)?;
    let success = response.status().is_success();
    if !success && !matches!(response.status().as_u16(), 400 | 429) {
        return Err("Pairing is unavailable on this service".into());
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(PairRequestError::Transport)?
    {
        if bytes.len() + chunk.len() > 4096 {
            return Err("Pairing response exceeds its limit".into());
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok((
        success,
        serde_json::from_slice(&bytes).map_err(|_| "Invalid pairing response".to_string())?,
    ))
}

async fn cancel_pending(pair: &PendingPair) -> Result<(), String> {
    let (success, value) = pair_request(
        &pair.session,
        "/v1/auth/device/cancel",
        serde_json::json!({"device_code": pair.proof}),
    )
    .await?;
    if success && value.get("cancelled") == Some(&Value::Bool(true)) {
        Ok(())
    } else {
        Err("Local pairing cleared; the service could not confirm cancellation".into())
    }
}

async fn close_session(session: Option<Session>) -> Result<(), String> {
    if let Some(session) = session {
        if session.pair_attempt.is_some() {
            request(&session, Method::DELETE, "/v1/auth/session", None, None).await?;
        }
    }
    Ok(())
}

async fn coding_contract(session: &Session) -> Result<Value, String> {
    let schema = request(session, Method::GET, "/v1/coding/schema", None, None).await?;
    if !schema.get("submission").is_some_and(Value::is_object)
        || !schema.get("decision").is_some_and(Value::is_object)
    {
        return Err("Service does not expose the coding contract".into());
    }
    Ok(schema)
}

async fn retire(session: Option<Session>, pair: Option<PendingPair>) -> Result<(), String> {
    let cancellation = if let Some(pair) = pair {
        cancel_pending(&pair).await
    } else {
        Ok(())
    };
    let revocation = close_session(session).await;
    cancellation?;
    revocation
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
    let mut pair_guard = state.1.lock().await;
    let previous = guard.take();
    retire(previous, pair_guard.take()).await?;
    let endpoint = origin(&endpoint)?;
    let session = https_session(endpoint, Some(&token), None)?;
    let schema = coding_contract(&session).await?;
    *guard = Some(session);
    Ok(schema)
}

#[tauri::command]
pub async fn remote_disconnect(state: State<'_, RemoteState>) -> Result<(), String> {
    let mut guard = state.0.lock().await;
    let mut pair_guard = state.1.lock().await;
    let previous = guard.take();
    retire(previous, pair_guard.take()).await?;
    Ok(())
}

#[tauri::command]
pub async fn remote_pair_begin(
    endpoint: String,
    label: String,
    state: State<'_, RemoteState>,
) -> Result<Value, String> {
    let guard = state.0.lock().await;
    let mut pending = state.1.lock().await;
    if guard.is_some() || pending.is_some() {
        return Err("Disconnect or cancel the current pairing first".into());
    }
    if label.is_empty()
        || label.len() > 64
        || !label
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || b" ._-".contains(&byte))
    {
        return Err("Enter a short device name".into());
    }
    let session = https_session(origin(&endpoint)?, None, None)?;
    let (success, value) = pair_request(
        &session,
        "/v1/auth/device/start",
        serde_json::json!({"label": label}),
    )
    .await?;
    if !success {
        return Err("Pairing is busy; wait a minute before trying again".into());
    }
    let reply: PairStart =
        serde_json::from_value(value).map_err(|_| "Invalid pairing challenge".to_string())?;
    if !opaque(&reply.device_code)
        || !user_code(&reply.user_code)
        || !(1..=300).contains(&reply.expires_in)
        || !(1..=30).contains(&reply.interval)
    {
        return Err("Invalid pairing challenge".into());
    }
    let attempt = state.2.fetch_add(1, Ordering::Relaxed);
    *pending = Some(PendingPair {
        session,
        proof: reply.device_code,
        attempt,
        expires: Instant::now() + Duration::from_secs(reply.expires_in),
        next_poll: Instant::now() + Duration::from_secs(reply.interval),
        transport_failures: 0,
    });
    Ok(
        serde_json::json!({"attempt": attempt.to_string(), "user_code": reply.user_code, "expires_in": reply.expires_in, "interval": reply.interval}),
    )
}

#[tauri::command]
pub async fn remote_pair_poll(
    attempt: String,
    state: State<'_, RemoteState>,
) -> Result<Value, String> {
    poll_pair(&state, &attempt).await
}

async fn poll_pair(state: &RemoteState, attempt: &str) -> Result<Value, String> {
    let mut guard = state.0.lock().await;
    let mut pending = state.1.lock().await;
    let pair = pending.as_mut().ok_or("Start pairing first")?;
    if attempt.parse::<u64>().ok() != Some(pair.attempt) {
        return Err("This pairing request is no longer current".into());
    }
    if Instant::now() >= pair.expires {
        if let Some(expired) = pending.take() {
            let _ = cancel_pending(&expired).await;
        }
        return Err("Pairing expired; start a new request".into());
    }
    if Instant::now() < pair.next_poll {
        return Ok(
            serde_json::json!({"status": "pending", "retry_after": pair.next_poll.saturating_duration_since(Instant::now()).as_secs().max(1)}),
        );
    }
    let result = pair_request(
        &pair.session,
        "/v1/auth/device/token",
        serde_json::json!({"device_code": pair.proof}),
    )
    .await;
    let (success, value) = match result {
        Ok(reply) => {
            pair.transport_failures = 0;
            reply
        }
        Err(PairRequestError::Transport(error)) => {
            if defer_pair_transport_failure(pair) {
                return Ok(serde_json::json!({"status": "pending", "retry_after": 5}));
            }
            return Err(PairRequestError::Transport(error).into());
        }
        Err(error) => return Err(error.into()),
    };
    if !success {
        let failure: PairFailure =
            serde_json::from_value(value).map_err(|_| "Invalid pairing result".to_string())?;
        if matches!(
            failure.error.as_str(),
            "authorization_pending" | "slow_down"
        ) && (1..=30).contains(&failure.interval)
        {
            pair.next_poll = Instant::now() + Duration::from_secs(failure.interval);
            return Ok(serde_json::json!({"status": "pending", "retry_after": failure.interval}));
        }
        if let Some(stopped) = pending.take() {
            let _ = cancel_pending(&stopped).await;
        }
        return Err("Pairing was declined or expired; start a new request".into());
    }
    let issued: PairToken =
        serde_json::from_value(value).map_err(|_| "Invalid paired session".to_string())?;
    if !opaque(&issued.access_token)
        || issued.token_type != "Bearer"
        || !(1..=3600).contains(&issued.expires_in)
    {
        return Err("Invalid paired session".into());
    }
    let session = https_session(
        pair.session.origin.clone(),
        Some(&issued.access_token),
        Some(pair.attempt),
    )?;
    coding_contract(&session).await?;
    let profile = request(&session, Method::GET, "/v1/auth/session", None, None).await?;
    if profile.get("authentication").and_then(Value::as_str) != Some("device")
        || Instant::now() >= pair.expires
    {
        close_session(Some(session)).await?;
        return Err("Paired session did not confirm the device identity".into());
    }
    *guard = Some(session);
    *pending = None;
    Ok(serde_json::json!({"status": "connected", "expires_in": issued.expires_in}))
}

#[tauri::command]
pub async fn remote_pair_cancel(
    attempt: String,
    state: State<'_, RemoteState>,
) -> Result<(), String> {
    let attempt = attempt
        .parse::<u64>()
        .map_err(|_| "Invalid pairing request".to_string())?;
    cancel_attempt(&state, attempt).await
}

async fn cancel_attempt(state: &RemoteState, attempt: u64) -> Result<(), String> {
    let mut guard = state.0.lock().await;
    let mut pending = state.1.lock().await;
    let previous = if guard
        .as_ref()
        .is_some_and(|session| session.pair_attempt == Some(attempt))
    {
        guard.take()
    } else {
        None
    };
    let pair = if pending.as_ref().is_some_and(|pair| pair.attempt == attempt) {
        pending.take()
    } else {
        None
    };
    retire(previous, pair).await
}

#[tauri::command]
pub async fn remote_operation(
    operation: Operation,
    state: State<'_, RemoteState>,
) -> Result<Value, String> {
    let guard = state.0.lock().await;
    let session = guard.as_ref().ok_or("Connect to a remote service first")?;
    let (method, path, body, key) = match operation {
        Operation::Models { provider } => {
            if !matches!(provider.as_str(), "nebius" | "nvidia") {
                return Err("Choose a supported model provider".into());
            }
            (Method::GET, format!("/v1/models/{provider}"), None, None)
        }
        Operation::AuthSession => (Method::GET, "/v1/auth/session".into(), None, None),
        Operation::PairedDevices => (Method::GET, "/v1/auth/devices".into(), None, None),
        Operation::RevokeDevice { id } => (
            Method::DELETE,
            format!("/v1/auth/devices/{}", identity(&id)?),
            None,
            None,
        ),
        Operation::ApproveDevice { payload } => {
            if !user_code(&payload.user_code)
                || !matches!(payload.authenticator_code.len(), 6 | 8)
                || !payload
                    .authenticator_code
                    .bytes()
                    .all(|byte| byte.is_ascii_digit())
            {
                return Err("Enter the phone pairing code and current Authenticator code".into());
            }
            (
                Method::POST,
                "/v1/auth/device/approve".into(),
                Some(serde_json::to_value(payload).map_err(|_| "Invalid pairing decision")?),
                None,
            )
        }
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

    fn pairing_http_fixture(replies: Vec<Option<(u16, &'static str)>>) -> (Url, std::thread::JoinHandle<Vec<String>>) {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let address = listener.local_addr().unwrap();
        let worker = std::thread::spawn(move || {
            let mut routes = Vec::new();
            for reply in replies {
                let deadline = Instant::now() + Duration::from_secs(10);
                let mut connection = loop {
                    match listener.accept() {
                        Ok((stream, _)) => break stream,
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock && Instant::now() < deadline =>
                            std::thread::sleep(Duration::from_millis(5)),
                        Err(error) => panic!("Fixture accept failed: {error}"),
                    }
                };
                connection.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
                let mut bytes = Vec::new();
                let mut buffer = [0; 1024];
                loop {
                    let count = connection.read(&mut buffer).unwrap();
                    assert!(count > 0);
                    bytes.extend_from_slice(&buffer[..count]);
                    assert!(bytes.len() < 8192);
                    if let Some(end) = bytes.windows(4).position(|part| part == b"\r\n\r\n") {
                        let header = std::str::from_utf8(&bytes[..end]).unwrap();
                        let length: usize = header.lines().find_map(|line| {
                            let (name, value) = line.split_once(':')?;
                            name.eq_ignore_ascii_case("content-length").then(|| value.trim().parse().unwrap())
                        }).unwrap_or(0);
                        if bytes.len() >= end + 4 + length {
                            routes.push(header.lines().next().unwrap().split_whitespace().nth(1).unwrap().to_string());
                            break;
                        }
                    }
                }
                if let Some((status, body)) = reply {
                    write!(connection, "HTTP/1.1 {status} Fixture\r\nContent-Length: {}\r\nConnection: close\r\nContent-Type: application/json\r\n\r\n{body}", body.len()).unwrap();
                } else {
                    connection.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\nConnection: close\r\n\r\n{\"access_token\":").unwrap();
                }
            }
            routes
        });
        (Url::parse(&format!("http://{address}")).unwrap(), worker)
    }

    #[test]
    fn interrupted_exchange_recovers_then_cancels_a_consumed_grant() {
        tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(async {
            let (endpoint, worker) = pairing_http_fixture(vec![
                None,
                Some((400, r#"{"error":"authorization_pending","interval":5}"#)),
                Some((400, r#"{"error":"invalid_grant","interval":5}"#)),
                Some((200, r#"{"cancelled":true}"#)),
            ]);
            let state = RemoteState::default();
            let deadline = Instant::now() + Duration::from_secs(300);
            *state.1.lock().await = Some(PendingPair {
                session: Session { origin: endpoint, pair_attempt: None, client: Client::builder().no_proxy().timeout(Duration::from_secs(2)).build().unwrap() },
                proof: "a".repeat(43), attempt: 1, expires: deadline,
                next_poll: Instant::now(), transport_failures: 0,
            });
            let retry = poll_pair(&state, "1").await.unwrap();
            assert_eq!(retry, serde_json::json!({"status":"pending","retry_after":5}));
            {
                let mut guard = state.1.lock().await;
                let pair = guard.as_mut().unwrap();
                assert_eq!(pair.transport_failures, 1);
                assert_eq!(pair.expires, deadline);
                pair.next_poll = Instant::now();
            }
            assert_eq!(poll_pair(&state, "1").await.unwrap()["status"], "pending");
            {
                let mut guard = state.1.lock().await;
                let pair = guard.as_mut().unwrap();
                assert_eq!(pair.transport_failures, 0);
                pair.next_poll = Instant::now();
            }
            assert!(poll_pair(&state, "1").await.is_err());
            assert!(state.0.lock().await.is_none());
            assert!(state.1.lock().await.is_none());
            assert_eq!(worker.join().unwrap(), vec![
                "/v1/auth/device/token", "/v1/auth/device/token", "/v1/auth/device/token", "/v1/auth/device/cancel",
            ]);
        });
    }

    #[test]
    fn stale_cancellation_preserves_newer_native_state() {
        tokio::runtime::Builder::new_current_thread()
            .enable_all()
            .build()
            .unwrap()
            .block_on(async {
                let state = RemoteState::default();
                *state.0.lock().await = Some(
                    https_session(origin("https://fixture.test").unwrap(), None, Some(2)).unwrap(),
                );
                *state.1.lock().await = Some(PendingPair {
                    session: https_session(origin("https://fixture.test").unwrap(), None, None)
                        .unwrap(),
                    proof: "a".repeat(43),
                    attempt: 2,
                    expires: Instant::now() + Duration::from_secs(300),
                    next_poll: Instant::now(),
                    transport_failures: 0,
                });
                cancel_attempt(&state, 1).await.unwrap();
                assert_eq!(state.0.lock().await.as_ref().unwrap().pair_attempt, Some(2));
                assert_eq!(state.1.lock().await.as_ref().unwrap().attempt, 2);
            });
    }

    #[test]
    fn polling_transport_retries_are_bounded_and_do_not_extend_expiry() {
        let deadline = Instant::now() + Duration::from_secs(300);
        let mut pair = PendingPair {
            session: https_session(origin("https://fixture.test").unwrap(), None, None).unwrap(),
            proof: "a".repeat(43),
            attempt: 1,
            expires: deadline,
            next_poll: Instant::now(),
            transport_failures: 0,
        };
        for expected in 1..=3 {
            assert!(defer_pair_transport_failure(&mut pair));
            assert_eq!(pair.transport_failures, expected);
            assert_eq!(pair.expires, deadline);
            assert!(pair.next_poll > Instant::now());
        }
        assert!(!defer_pair_transport_failure(&mut pair));
        pair.transport_failures = 0;
        pair.expires = Instant::now();
        assert!(!defer_pair_transport_failure(&mut pair));
    }

    #[test]
    fn pairing_identifiers_and_replies_are_strict() {
        assert!(opaque(&"a".repeat(43)));
        for value in [
            "a".repeat(42),
            "a".repeat(44),
            format!("{}=", "a".repeat(42)),
        ] {
            assert!(!opaque(&value));
        }
        assert!(user_code("ABCD-EFGH"));
        for value in [
            "ABCD-EFGI",
            "ABCD-EFG0",
            "abcd-efgh",
            "ABCD/EFGH",
            "ABCDEFGH",
        ] {
            assert!(!user_code(value));
        }
        let reply = serde_json::json!({"access_token": "a".repeat(43), "token_type": "Bearer", "expires_in": 3600});
        assert!(serde_json::from_value::<PairToken>(reply.clone()).is_ok());
        let mut extra = reply.clone();
        extra["redirect"] = serde_json::json!("https://elsewhere.test");
        assert!(serde_json::from_value::<PairToken>(extra).is_err());
        let mut wrong = reply;
        wrong["expires_in"] = serde_json::json!("3600");
        assert!(serde_json::from_value::<PairToken>(wrong).is_err());
    }

    #[test]
    fn pairing_commands_cannot_supply_secrets_or_routes_as_extra_fields() {
        assert!(serde_json::from_value::<Operation>(serde_json::json!({
            "operation": "approve_device", "payload": {"user_code": "ABCD-EFGH", "authenticator_code": "123456", "approved": true}
        })).is_ok());
        for extra in ["url", "secret", "subject", "access_token"] {
            let mut payload = serde_json::json!({"user_code": "ABCD-EFGH", "authenticator_code": "123456", "approved": true});
            payload[extra] = serde_json::json!("unexpected");
            assert!(serde_json::from_value::<PairDecision>(payload).is_err());
        }
    }

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
