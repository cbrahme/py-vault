"""
PyVault Core Cryptography Engine with Dual-Slot Recovery Key Envelope
Version 2 (PV02)

Zero-Knowledge AES-256-GCM + PBKDF2-HMAC-SHA256.
Supports day-to-day Master Password and Emergency Recovery Key.
"""

import os
import json
import base64
import secrets
import string
from typing import Tuple, Dict, Any, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SALT_SIZE = 16       # 128-bit salt
NONCE_SIZE = 12      # 96-bit nonce for AES-GCM
KEY_SIZE = 32        # 256-bit AES key
PBKDF2_PW_ROUNDS = 600_000   # OWASP recommendation for master password
PBKDF2_RC_ROUNDS = 100_000   # High-entropy recovery key rounds


def generate_recovery_key() -> str:
    """
    Generates a high-entropy 128-bit emergency recovery key formatted as:
    RCV-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
    (32 alphanumeric characters in 8 groups of 4)
    """
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ" # Crockford Base32-like (no 0/O, 1/I confusion)
    raw = "".join(secrets.choice(alphabet) for _ in range(32))
    blocks = [raw[i:i+4] for i in range(0, 32, 4)]
    return "RCV-" + "-".join(blocks)


def normalize_recovery_key(key_str: str) -> str:
    """Strips 'RCV-', dashes, and whitespace, returning uppercase raw key."""
    cleaned = key_str.upper().strip()
    if cleaned.startswith("RCV-"):
        cleaned = cleaned[4:]
    return cleaned.replace("-", "").replace(" ", "").strip()


def derive_key(secret: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(secret.encode("utf-8"))


def create_new_vault_envelope(vault_data: dict, master_password: str) -> Tuple[bytes, str]:
    """
    Initializes a new vault with a fresh 256-bit Vault Key (VK).
    Wraps VK in two slots:
      Slot 1: Master Password
      Slot 2: Emergency Recovery Key
    Returns: (envelope_bytes, recovery_key_string)
    """
    recovery_key = generate_recovery_key()
    normalized_rc = normalize_recovery_key(recovery_key)

    vault_key = os.urandom(KEY_SIZE)

    # 1. Encrypt Vault Data with Vault Key
    vault_plaintext = json.dumps(vault_data, ensure_ascii=False).encode("utf-8")
    vault_nonce = os.urandom(NONCE_SIZE)
    aes_vk = AESGCM(vault_key)
    encrypted_vault = aes_vk.encrypt(vault_nonce, vault_plaintext, b"VAULT_PAYLOAD")

    # 2. Encrypt Vault Key with Master Password
    salt_pw = os.urandom(SALT_SIZE)
    key_pw = derive_key(master_password, salt_pw, PBKDF2_PW_ROUNDS)
    nonce_pw = os.urandom(NONCE_SIZE)
    encrypted_vk_pw = AESGCM(key_pw).encrypt(nonce_pw, vault_key, b"SLOT_PW")

    # 3. Encrypt Vault Key with Recovery Key
    salt_rc = os.urandom(SALT_SIZE)
    key_rc = derive_key(normalized_rc, salt_rc, PBKDF2_RC_ROUNDS)
    nonce_rc = os.urandom(NONCE_SIZE)
    encrypted_vk_rc = AESGCM(key_rc).encrypt(nonce_rc, vault_key, b"SLOT_RC")

    envelope = {
        "format": "PV02",
        "version": 2,
        "slot_pw": {
            "salt": base64.b64encode(salt_pw).decode("ascii"),
            "nonce": base64.b64encode(nonce_pw).decode("ascii"),
            "data": base64.b64encode(encrypted_vk_pw).decode("ascii"),
        },
        "slot_rc": {
            "salt": base64.b64encode(salt_rc).decode("ascii"),
            "nonce": base64.b64encode(nonce_rc).decode("ascii"),
            "data": base64.b64encode(encrypted_vk_rc).decode("ascii"),
        },
        "vault": {
            "nonce": base64.b64encode(vault_nonce).decode("ascii"),
            "data": base64.b64encode(encrypted_vault).decode("ascii"),
        }
    }

    return json.dumps(envelope).encode("utf-8"), recovery_key


def unlock_vault_envelope(envelope_bytes: bytes, secret: str, is_recovery_key: bool = False) -> Tuple[dict, bytes, dict]:
    """
    Unlocks vault using either Master Password or Emergency Recovery Key.
    Returns: (vault_data_dict, vault_key_bytes, full_envelope_dict)
    """
    try:
        envelope = json.loads(envelope_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError("Invalid vault file format.") from e

    if envelope.get("format") != "PV02":
        raise ValueError(f"Unsupported vault format: {envelope.get('format')}")

    if is_recovery_key:
        slot = envelope.get("slot_rc", {})
        secret_clean = normalize_recovery_key(secret)
        rounds = PBKDF2_RC_ROUNDS
        aad = b"SLOT_RC"
    else:
        slot = envelope.get("slot_pw", {})
        secret_clean = secret
        rounds = PBKDF2_PW_ROUNDS
        aad = b"SLOT_PW"

    salt = base64.b64decode(slot["salt"])
    nonce = base64.b64decode(slot["nonce"])
    enc_vk = base64.b64decode(slot["data"])

    # Decrypt Vault Key
    derived_k = derive_key(secret_clean, salt, rounds)
    try:
        vault_key = AESGCM(derived_k).decrypt(nonce, enc_vk, aad)
    except Exception as e:
        auth_type = "Recovery Key" if is_recovery_key else "Master Password"
        raise ValueError(f"Invalid {auth_type}. Decryption failed.") from e

    # Decrypt Vault Payload with Vault Key
    vault_info = envelope["vault"]
    vault_nonce = base64.b64decode(vault_info["nonce"])
    enc_vault_data = base64.b64decode(vault_info["data"])

    try:
        plaintext_bytes = AESGCM(vault_key).decrypt(vault_nonce, enc_vault_data, b"VAULT_PAYLOAD")
        vault_data = json.loads(plaintext_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError("Vault payload is corrupt or was tampered with.") from e

    return vault_data, vault_key, envelope


def unlock_vault_with_key(envelope_bytes: bytes, vault_key: bytes) -> Tuple[dict, bytes, dict]:
    """Unlocks vault payload directly with a known 256-bit Vault Key."""
    envelope = json.loads(envelope_bytes.decode("utf-8"))
    vault_info = envelope["vault"]
    vault_nonce = base64.b64decode(vault_info["nonce"])
    enc_vault_data = base64.b64decode(vault_info["data"])
    plaintext_bytes = AESGCM(vault_key).decrypt(vault_nonce, enc_vault_data, b"VAULT_PAYLOAD")
    vault_data = json.loads(plaintext_bytes.decode("utf-8"))
    return vault_data, vault_key, envelope


def reencrypt_vault_data(vault_data: dict, vault_key: bytes, envelope: dict) -> bytes:
    """Updates vault payload while preserving existing keys/slots."""
    vault_plaintext = json.dumps(vault_data, ensure_ascii=False).encode("utf-8")
    vault_nonce = os.urandom(NONCE_SIZE)
    encrypted_vault = AESGCM(vault_key).encrypt(vault_nonce, vault_plaintext, b"VAULT_PAYLOAD")

    envelope["vault"]["nonce"] = base64.b64encode(vault_nonce).decode("ascii")
    envelope["vault"]["data"] = base64.b64encode(encrypted_vault).decode("ascii")

    return json.dumps(envelope).encode("utf-8")


def reset_password_with_vault_key(vault_key: bytes, new_password: str, envelope: dict) -> bytes:
    """Re-encrypts Slot 1 with a new Master Password using the verified Vault Key."""
    salt_pw = os.urandom(SALT_SIZE)
    key_pw = derive_key(new_password, salt_pw, PBKDF2_PW_ROUNDS)
    nonce_pw = os.urandom(NONCE_SIZE)
    encrypted_vk_pw = AESGCM(key_pw).encrypt(nonce_pw, vault_key, b"SLOT_PW")

    envelope["slot_pw"] = {
        "salt": base64.b64encode(salt_pw).decode("ascii"),
        "nonce": base64.b64encode(nonce_pw).decode("ascii"),
        "data": base64.b64encode(encrypted_vk_pw).decode("ascii"),
    }
    return json.dumps(envelope).encode("utf-8")
