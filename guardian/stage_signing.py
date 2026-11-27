"""Shared strict P-256 signing configuration for isolated Guardian V2."""
import base64
import hmac
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def load_signing_pair(private_value, public_value):
    try:
        if not isinstance(private_value, str) or not isinstance(public_value, str):
            raise ValueError
        private_value, public_value = private_value.strip(), public_value.strip()
        if not 1 <= len(private_value) <= 4096 or not 1 <= len(public_value) <= 256:
            raise ValueError
        der = base64.b64decode(private_value, validate=True)
        key = serialization.load_der_private_key(der, password=None)
        if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
            raise ValueError
        canonical = base64.urlsafe_b64encode(key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )).rstrip(b'=').decode('ascii')
        if not hmac.compare_digest(canonical, public_value):
            raise ValueError
        return key
    except (ValueError, TypeError, UnicodeError):
        raise ValueError('Invalid Guardian V2 signing pair') from None
