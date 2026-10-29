from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from urllib.parse import urlencode, parse_qs

import httpx
import jwt
from cryptography.fernet import Fernet


class AuthProvider(Enum):
    GITHUB = "github"
    GITLAB = "gitlab"
    GOOGLE = "google"
    MICROSOFT = "microsoft"
    DISCORD = "discord"
    SLACK = "slack"
    OIDC = "oidc"
    SAML = "saml"


@dataclass
class OAuthConfig:
    """OAuth provider configuration."""
    provider: AuthProvider
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: list[str] = field(default_factory=list)
    auth_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    pkce: bool = True


@dataclass
class UserInfo:
    """User information from OAuth provider."""
    provider: AuthProvider
    provider_user_id: str
    email: str
    name: str
    username: str | None = None
    avatar_url: str | None = None
    access_token: str = ""
    refresh_token: str | None = None
    expires_at: datetime | None = None
    raw_data: dict = field(default_factory=dict)


@dataclass
class Session:
    """User session."""
    id: str
    user_id: str
    provider: AuthProvider
    access_token: str
    refresh_token: str | None
    created_at: datetime
    expires_at: datetime
    scopes: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class OAuthProvider:
    """OAuth provider implementation."""
    
    # Predefined provider configurations
    PROVIDERS = {
        AuthProvider.GITHUB: {
            "auth_url": "https://github.com/login/oauth/authorize",
            "token_url": "https://github.com/login/oauth/access_token",
            "userinfo_url": "https://api.github.com/user",
            "default_scopes": ["read:user", "user:email", "repo"],
        },
        AuthProvider.GITLAB: {
            "auth_url": "https://gitlab.com/oauth/authorize",
            "token_url": "https://gitlab.com/oauth/token",
            "userinfo_url": "https://gitlab.com/api/v4/user",
            "default_scopes": ["read_user", "api"],
        },
        AuthProvider.GOOGLE: {
            "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_url": "https://oauth2.googleapis.com/token",
            "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
            "default_scopes": ["openid", "email", "profile"],
        },
        AuthProvider.MICROSOFT: {
            "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "userinfo_url": "https://graph.microsoft.com/v1.0/me",
            "default_scopes": ["openid", "profile", "email", "User.Read"],
        },
        AuthProvider.DISCORD: {
            "auth_url": "https://discord.com/api/oauth2/authorize",
            "token_url": "https://discord.com/api/oauth2/token",
            "userinfo_url": "https://discord.com/api/users/@me",
            "default_scopes": ["identify", "email"],
        },
        AuthProvider.SLACK: {
            "auth_url": "https://slack.com/oauth/v2/authorize",
            "token_url": "https://slack.com/api/oauth.v2.access",
            "userinfo_url": "https://slack.com/api/users.identity",
            "default_scopes": ["identity.basic", "identity.email", "identity.avatar"],
        },
    }
    
    def __init__(self, config: OAuthConfig):
        self.config = config
        self.provider_info = self.PROVIDERS.get(config.provider, {})
        self.state_store: dict[str, dict] = {}  # In production, use Redis
    
    def get_auth_url(self, state: str | None = None) -> tuple[str, str]:
        """Generate OAuth authorization URL."""
        if state is None:
            state = secrets.token_urlsafe(32)
        
        # Store state
        self.state_store[state] = {
            "created_at": time.time(),
            "pkce_verifier": None,
        }
        
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": self.config.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes or self.provider_info.get("default_scopes", [])),
            "state": state,
        }
        
        # PKCE
        if self.config.pkce:
            verifier = secrets.token_urlsafe(32)
            challenge = hashlib.sha256(verifier.encode()).digest()
            challenge_b64 = base64.urlsafe_b64encode(challenge).decode().rstrip("=")
            params["code_challenge"] = challenge_b64
            params["code_challenge_method"] = "S256"
            self.state_store[state]["pkce_verifier"] = verifier
        
        auth_url = self.config.auth_url or self.provider_info.get("auth_url", "")
        return f"{auth_url}?{urlencode(params)}", state
    
    async def exchange_code(self, code: str, state: str) -> UserInfo:
        """Exchange authorization code for tokens."""
        # Verify state
        stored = self.state_store.pop(state, None)
        if not stored:
            raise ValueError("Invalid or expired state")
        
        pkce_verifier = stored.get("pkce_verifier")
        
        token_url = self.config.token_url or self.provider_info.get("token_url", "")
        
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.redirect_uri,
        }
        
        if pkce_verifier:
            data["code_verifier"] = pkce_verifier
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Accept": "application/json"}
            response = await client.post(token_url, data=data, headers=headers)
            response.raise_for_status()
            token_data = response.json()
        
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in")
        token_type = token_data.get("token_type", "Bearer")
        
        # Get user info
        userinfo = await self.get_userinfo(access_token)
        
        return UserInfo(
            provider=self.config.provider,
            provider_user_id=str(userinfo.get("id", userinfo.get("sub", ""))),
            email=userinfo.get("email", ""),
            name=userinfo.get("name", userinfo.get("login", "")),
            username=userinfo.get("login", userinfo.get("preferred_username")),
            avatar_url=userinfo.get("avatar_url", userinfo.get("picture")),
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.now() + timedelta(seconds=expires_in) if expires_in else None,
            raw_data=userinfo,
        )
    
    async def get_userinfo(self, access_token: str) -> dict:
        """Get user info from provider."""
        userinfo_url = self.config.userinfo_url or self.provider_info.get("userinfo_url", "")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {access_token}"}
            response = await client.get(userinfo_url, headers=headers)
            response.raise_for_status()
            return response.json()
    
    async def refresh_token(self, refresh_token: str) -> tuple[str, str | None, datetime | None]:
        """Refresh access token."""
        token_url = self.config.token_url or self.provider_info.get("token_url", "")
        
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(token_url, data=data)
            response.raise_for_status()
            token_data = response.json()
        
        expires_in = token_data.get("expires_in")
        return (
            token_data["access_token"],
            token_data.get("refresh_token"),
            datetime.now() + timedelta(seconds=expires_in) if expires_in else None,
        )


class AuthManager:
    """Manages authentication and sessions."""
    
    def __init__(
        self,
        secret_key: str,
        providers: dict[AuthProvider, OAuthConfig],
        session_ttl_hours: int = 24,
        refresh_ttl_days: int = 30,
    ):
        self.secret_key = secret_key
        self.providers = {p.provider: OAuthProvider(c) for p, c in providers.items()}
        self.sessions: dict[str, Session] = {}
        self.user_sessions: dict[str, list[str]] = {}  # user_id -> session_ids
        self.session_ttl = timedelta(hours=session_ttl_hours)
        self.refresh_ttl = timedelta(days=refresh_ttl_days)
        self.fernet = Fernet(Fernet.generate_key())  # For encrypting tokens
    
    def create_session(self, user_info: UserInfo) -> Session:
        """Create a new session."""
        session_id = secrets.token_urlsafe(32)
        now = datetime.now()
        
        session = Session(
            id=session_id,
            user_id=user_info.provider_user_id,
            provider=user_info.provider,
            access_token=self._encrypt(user_info.access_token),
            refresh_token=self._encrypt(user_info.refresh_token) if user_info.refresh_token else None,
            created_at=now,
            expires_at=now + self.session_ttl,
            scopes=user_info.raw_data.get("scopes", []),
        )
        
        self.sessions[session_id] = session
        if user_info.provider_user_id not in self.user_sessions:
            self.user_sessions[user_info.provider_user_id] = []
        self.user_sessions[user_info.provider_user_id].append(session_id)
        
        return session
    
    def _encrypt(self, data: str) -> str:
        return self.fernet.encrypt(data.encode()).decode()
    
    def _decrypt(self, data: str) -> str:
        return self.fernet.decrypt(data.encode()).decode()
    
    def get_session(self, session_id: str) -> Session | None:
        session = self.sessions.get(session_id)
        if session and session.expires_at > datetime.now():
            return session
        elif session:
            self.delete_session(session_id)
        return None
    
    def get_user_sessions(self, user_id: str) -> list[Session]:
        session_ids = self.user_sessions.get(user_id, [])
        return [self.sessions[sid] for sid in session_ids if sid in self.sessions and self.sessions[sid].expires_at > datetime.now()]
    
    def delete_session(self, session_id: str) -> bool:
        session = self.sessions.pop(session_id, None)
        if session:
            user_sessions = self.user_sessions.get(session.user_id, [])
            if session_id in user_sessions:
                user_sessions.remove(session_id)
            return True
        return False
    
    def delete_user_sessions(self, user_id: str) -> int:
        session_ids = self.user_sessions.pop(user_id, [])
        count = 0
        for sid in session_ids:
            if sid in self.sessions:
                del self.sessions[sid]
                count += 1
        return count
    
    async def authenticate(self, provider: AuthProvider, code: str, state: str) -> Session | None:
        """Authenticate user via OAuth provider."""
        oauth = self.providers.get(provider)
        if not oauth:
            raise ValueError(f"Provider {provider} not configured")
        
        user_info = await oauth.exchange_code(code, state)
        return self.create_session(user_info)
    
    def get_auth_url(self, provider: AuthProvider) -> tuple[str, str]:
        """Get OAuth authorization URL."""
        oauth = self.providers.get(provider)
        if not oauth:
            raise ValueError(f"Provider {provider} not configured")
        return oauth.get_auth_url()
    
    def validate_token(self, token: str) -> dict | None:
        """Validate JWT token."""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            return payload
        except jwt.InvalidTokenError:
            return None
    
    def create_jwt(self, user_id: str, provider: AuthProvider, scopes: list[str], expires_delta: timedelta | None = None) -> str:
        """Create JWT token."""
        now = datetime.utcnow()
        expires = now + (expires_delta or self.session_ttl)
        
        payload = {
            "sub": user_id,
            "provider": provider.value,
            "scopes": scopes,
            "iat": now,
            "exp": expires,
        }
        
        return jwt.encode(payload, self.secret_key, algorithm="HS256")
    
    def cleanup_expired(self) -> int:
        """Remove expired sessions."""
        now = datetime.now()
        expired = [sid for sid, s in self.sessions.items() if s.expires_at <= now]
        for sid in expired:
            self.delete_session(sid)
        return len(expired)


class APIKeyManager:
    """Manages API keys for programmatic access."""
    
    def __init__(self, secret_key: str):
        self.secret_key = secret_key
        self.keys: dict[str, dict] = {}  # key_prefix -> key_data
    
    def create_key(
        self,
        name: str,
        user_id: str,
        scopes: list[str],
        expires_days: int | None = None,
        rate_limit: int = 1000,  # requests per hour
    ) -> tuple[str, str]:
        """Create a new API key. Returns (key_id, full_key)."""
        key_id = f"bf_{secrets.token_urlsafe(16)}"
        secret = secrets.token_urlsafe(32)
        full_key = f"{key_id}.{secret}"
        
        key_data = {
            "name": name,
            "user_id": user_id,
            "scopes": scopes,
            "created_at": datetime.now().isoformat(),
            "expires_at": (datetime.now() + timedelta(days=expires_days)).isoformat() if expires_days else None,
            "rate_limit": rate_limit,
            "last_used": None,
            "usage_count": 0,
            "hashed_secret": hashlib.sha256(secret.encode()).hexdigest(),
        }
        
        self.keys[key_id] = key_data
        return key_id, full_key
    
    def validate_key(self, full_key: str) -> dict | None:
        """Validate API key. Returns key data if valid."""
        try:
            key_id, secret = full_key.split(".", 1)
        except ValueError:
            return None
        
        key_data = self.keys.get(key_id)
        if not key_data:
            return None
        
        # Check expiration
        if key_data.get("expires_at"):
            if datetime.fromisoformat(key_data["expires_at"]) < datetime.now():
                return None
        
        # Verify secret
        if key_data["hashed_secret"] != hashlib.sha256(secret.encode()).hexdigest():
            return None
        
        # Update usage
        key_data["last_used"] = datetime.now().isoformat()
        key_data["usage_count"] += 1
        
        return key_data
    
    def revoke_key(self, key_id: str) -> bool:
        if key_id in self.keys:
            del self.keys[key_id]
            return True
        return False
    
    def list_keys(self, user_id: str | None = None) -> list[dict]:
        keys = []
        for key_id, data in self.keys.items():
            if user_id is None or data["user_id"] == user_id:
                keys.append({
                    "key_id": key_id,
                    "name": data["name"],
                    "scopes": data["scopes"],
                    "created_at": data["created_at"],
                    "expires_at": data.get("expires_at"),
                    "last_used": data["last_used"],
                    "usage_count": data["usage_count"],
                    "rate_limit": data["rate_limit"],
                })
        return keys


class SSOManager:
    """Single Sign-On manager for enterprise."""
    
    def __init__(self, auth_manager: AuthManager):
        self.auth_manager = auth_manager
        self.saml_configs: dict[str, dict] = {}
        self.oidc_configs: dict[str, dict] = {}
    
    def configure_saml(self, entity_id: str, config: dict):
        """Configure SAML IdP."""
        self.saml_configs[entity_id] = config
    
    def configure_oidc(self, issuer: str, config: dict):
        """Configure OIDC provider."""
        self.oidc_configs[issuer] = config
    
    def get_saml_metadata(self, entity_id: str) -> str | None:
        """Generate SAML metadata XML."""
        config = self.saml_configs.get(entity_id)
        if not config:
            return None
        
        # Generate SAML metadata XML
        # This is a simplified version
        return f"""<?xml version="1.0"?>
<EntityDescriptor xmlns="urn:oasis:names:tc:SAML:2.0:metadata" entityID="{entity_id}">
    <IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
        <KeyDescriptor use="signing">
            <KeyInfo xmlns="http://www.w3.org/2000/09/xmldsig#">
                <X509Data>
                    <X509Certificate>{config.get('certificate', '')}</X509Certificate>
                </X509Data>
            </KeyDescriptor>
            <SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="{config.get('sso_url')}"/>
        </IDPSSODescriptor>
</EntityDescriptor>"""
    
    async def initiate_sso(self, entity_id: str, relay_state: str | None = None) -> str:
        """Initiate SAML SSO flow."""
        config = self.saml_configs.get(entity_id)
        if not config:
            raise ValueError(f"SAML config not found for {entity_id}")
        
        # Generate SAML AuthnRequest
        request_id = f"_{secrets.token_hex(16)}"
        issue_instant = datetime.utcnow().isoformat() + "Z"
        
        authn_request = f"""<?xml version="1.0"?>
<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
    ID="{request_id}"
    Version="2.0"
    IssueInstant="{issue_instant}"
    Destination="{config.get('sso_url')}"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
    AssertionConsumerServiceURL="{config.get('acs_url')}">
    <saml:Issuer xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion">{entity_id}</saml:Issuer>
</samlp:AuthnRequest>"""
        
        # Encode and redirect
        import base64
        encoded = base64.b64encode(authn_request.encode()).decode()
        sso_url = config.get("sso_url", "")
        params = {"SAMLRequest": encoded}
        if relay_state:
            params["RelayState"] = relay_state
        
        return f"{sso_url}?{urlencode(params)}"
    
    def parse_saml_response(self, saml_response: str) -> dict | None:
        """Parse SAML Response."""
        import base64
        import xml.etree.ElementTree as ET
        
        try:
            decoded = base64.b64decode(saml_response).decode()
            root = ET.fromstring(decoded)
            
            # Extract assertions
            ns = {
                "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
                "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
            }
            
            assertions = root.findall(".//saml:Assertion", ns)
            for assertion in assertions:
                subject = assertion.find("saml:Subject", ns)
                name_id = subject.find("saml:NameID", ns) if subject is not None else None
                
                attributes = {}
                for attr in assertion.findall(".//saml:Attribute", ns):
                    name = attr.get("Name")
                    values = attr.findall("saml:AttributeValue", ns)
                    if values:
                        attributes[name] = values[0].text
                
                return {
                    "name_id": name_id.text if name_id is not None else None,
                    "attributes": attributes,
                    "session_index": assertion.find("saml:AuthnStatement", ns).get("SessionIndex") if assertion.find("saml:AuthnStatement", ns) is not None else None,
                }
        except Exception as e:
            print(f"SAML parsing error: {e}")
        
        return None


def create_auth_manager(
    secret_key: str,
    github_client_id: str = "",
    github_client_secret: str = "",
    github_redirect_uri: str = "",
    google_client_id: str = "",
    google_client_secret: str = "",
    google_redirect_uri: str = "",
    **extra_providers,
) -> AuthManager:
    """Create AuthManager with common providers."""
    providers = {}
    
    if github_client_id and github_client_secret:
        providers[AuthProvider.GITHUB] = OAuthConfig(
            provider=AuthProvider.GITHUB,
            client_id=github_client_id,
            client_secret=github_client_secret,
            redirect_uri=github_redirect_uri,
            scopes=["read:user", "user:email", "repo"],
        )
    
    if google_client_id and google_client_secret:
        providers[AuthProvider.GOOGLE] = OAuthConfig(
            provider=AuthProvider.GOOGLE,
            client_id=google_client_id,
            client_secret=google_client_secret,
            redirect_uri=google_redirect_uri,
            scopes=["openid", "email", "profile"],
        )
    
    # Add extra providers
    for provider_name, config_dict in extra_providers.items():
        try:
            provider = AuthProvider(provider_name)
            providers[provider] = OAuthConfig(
                provider=provider,
                **config_dict,
            )
        except ValueError:
            pass
    
    return AuthManager(secret_key, providers)