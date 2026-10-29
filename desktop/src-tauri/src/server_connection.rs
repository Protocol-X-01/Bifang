use serde::{Deserialize, Serialize};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ServerConnection {
    version: u8,
    origin: String,
    api_key: String,
}

impl ServerConnection {
    pub(crate) fn parse(line: &[u8]) -> Option<Self> {
        if line.len() > 2048 {
            return None;
        }
        let payload = std::str::from_utf8(line)
            .ok()?
            .strip_prefix("BIFANG_DESKTOP_READY ")?;
        let connection: Self = serde_json::from_str(payload).ok()?;
        let port = connection
            .origin
            .strip_prefix("http://127.0.0.1:")?
            .parse::<u16>()
            .ok()?;
        if connection.version != 1
            || port == 0
            || connection.origin != format!("http://127.0.0.1:{port}")
            || connection.api_key.len() != 64
            || !connection
                .api_key
                .bytes()
                .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        {
            return None;
        }
        Some(connection)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_only_bounded_loopback_bootstrap() {
        let line = |origin: &str, key: &str| {
            format!(
                "BIFANG_DESKTOP_READY {}",
                serde_json::json!({
                    "version": 1, "origin": origin, "api_key": key,
                })
            )
        };
        let key = "a".repeat(64);
        assert!(ServerConnection::parse(line("http://127.0.0.1:49152", &key).as_bytes()).is_some());
        for origin in [
            "http://example.com:1234",
            "http://127.0.0.1:0",
            "http://127.0.0.1:1234/path",
            "http://127.0.0.1:1234@evil.test",
            "http://127.0.0.1:01234",
        ] {
            assert!(ServerConnection::parse(line(origin, &key).as_bytes()).is_none());
        }
        assert!(
            ServerConnection::parse(line("http://127.0.0.1:1234", "short").as_bytes()).is_none()
        );
        assert!(ServerConnection::parse(&vec![b'a'; 2049]).is_none());
    }
}
