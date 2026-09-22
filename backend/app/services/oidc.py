import os
import base64
import httpx2 as httpx
from typing import Optional
import jwt as pyjwt
from jwt import PyJWKClient
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key_bytes(hex_key: str) -> bytes:
    if len(hex_key) != 64:
        raise ValueError(
            f"SESSION_ENCRYPTION_KEY must be exactly 64 hex characters (32 bytes); "
            f"got {len(hex_key)} characters. "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return bytes.fromhex(hex_key)


def encrypt_cookie(plaintext: str, hex_key: str) -> str:
    key = _key_bytes(hex_key)
    aesgcm = AESGCM(key[:32])
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ct).decode()


def decrypt_cookie(token: str, hex_key: str) -> Optional[str]:
    try:
        key = _key_bytes(hex_key)
        aesgcm = AESGCM(key[:32])
        raw = base64.urlsafe_b64decode(token.encode())
        nonce, ct = raw[:12], raw[12:]
        return aesgcm.decrypt(nonce, ct, None).decode()
    except Exception:
        return None


async def discover_endpoints(issuer_url: str) -> dict:
    url = issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


async def exchange_code(
    code: str,
    token_endpoint: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10,
        )
    resp.raise_for_status()
    return resp.json()


async def get_userinfo(userinfo_endpoint: str, access_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
    resp.raise_for_status()
    return resp.json()


def verify_id_token(id_token: str, jwks_uri: str, client_id: str, issuer: str) -> dict:
    jwks_client = PyJWKClient(jwks_uri)
    signing_key = jwks_client.get_signing_key_from_jwt(id_token)
    return pyjwt.decode(
        id_token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=client_id,
        issuer=issuer,
    )
