"""
Verificación real de access tokens de Auth0 (RS256 vía JWKS) con PyJWT.

A diferencia del resto de la suite —que overridea `get_current_user`— aquí se
ejercita `validar_token()` de punta a punta: firma, audience, issuer, expiración
y resolución de clave por `kid`. Protege contra regresiones del motor de JWT.
"""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from src.platform.identity import auth0
from src.platform.identity.auth0 import Auth0Error, validar_token

KID = "test-key-1"
DOMAIN = "test-tenant.auth0.com"
AUDIENCE = "https://api.test/"


@pytest.fixture
def clave_privada():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks(clave_privada):
    jwk = json.loads(RSAAlgorithm.to_jwk(clave_privada.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


@pytest.fixture(autouse=True)
def _config(monkeypatch, jwks):
    monkeypatch.setattr(auth0.settings, "AUTH0_DOMAIN", DOMAIN)
    monkeypatch.setattr(auth0.settings, "AUTH0_AUDIENCE", AUDIENCE)
    monkeypatch.setattr(auth0, "_obtener_jwks", lambda: jwks)


def _firmar(clave, *, kid=KID, **overrides):
    claims = {
        "sub": "auth0|123",
        "aud": AUDIENCE,
        "iss": f"https://{DOMAIN}/",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    claims.update(overrides)
    return jwt.encode(claims, clave, algorithm="RS256", headers={"kid": kid})


def test_token_valido_devuelve_claims(clave_privada):
    claims = validar_token(_firmar(clave_privada))
    assert claims["sub"] == "auth0|123"


def test_audience_incorrecta_rechaza(clave_privada):
    with pytest.raises(Auth0Error):
        validar_token(_firmar(clave_privada, aud="https://otra-api/"))


def test_issuer_incorrecto_rechaza(clave_privada):
    with pytest.raises(Auth0Error):
        validar_token(_firmar(clave_privada, iss="https://malicioso/"))


def test_token_expirado_rechaza(clave_privada):
    with pytest.raises(Auth0Error):
        validar_token(_firmar(clave_privada, exp=int(time.time()) - 10))


def test_kid_desconocido_rechaza(clave_privada):
    with pytest.raises(Auth0Error):
        validar_token(_firmar(clave_privada, kid="kid-inexistente"))


def test_firma_de_otra_clave_rechaza():
    """kid válido, pero el token lo firmó una clave distinta a la del JWKS."""
    otra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(Auth0Error):
        validar_token(_firmar(otra))
