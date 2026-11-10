"""
PyVault Data Models and Vault Manager with Recovery Key Support
"""

import os
import sys
import time
import uuid
import secrets
import string
import threading
import subprocess
from typing import List, Optional, Dict, Any, Tuple
from .crypto import (
    create_new_vault_envelope,
    unlock_vault_envelope,
    unlock_vault_with_key,
    reencrypt_vault_data,
    reset_password_with_vault_key,
    generate_recovery_key,
    normalize_recovery_key
)


def generate_password(length: int = 20, use_symbols: bool = True, use_numbers: bool = True) -> str:
    """Generate a high-entropy cryptographically secure random password."""
    chars = string.ascii_letters
    if use_numbers:
        chars += string.digits
    if use_symbols:
        chars += "!@#$%^&*()-_=+[]{}|;:,.<>?"

    password_chars = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase)
    ]
    if use_numbers:
        password_chars.append(secrets.choice(string.digits))
    if use_symbols:
        password_chars.append(secrets.choice("!@#$%^&*()-_=+[]{}|;:,.<>?"))

    remaining_len = max(0, length - len(password_chars))
    for _ in range(remaining_len):
        password_chars.append(secrets.choice(chars))

    secrets.SystemRandom().shuffle(password_chars)
    return "".join(password_chars)


def copy_to_clipboard_timed(text: str, timeout_seconds: int = 20):
    """Copies text to the system clipboard and securely clears it after timeout_seconds."""
    def _copy(val: str):
        if sys.platform == "darwin":
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE, close_fds=True)
            p.communicate(input=val.encode("utf-8"))
        elif sys.platform.startswith("linux"):
            try:
                p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE, close_fds=True)
                p.communicate(input=val.encode("utf-8"))
            except FileNotFoundError:
                try:
                    p = subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE, close_fds=True)
                    p.communicate(input=val.encode("utf-8"))
                except FileNotFoundError:
                    pass

    _copy(text)

    def _clear():
        time.sleep(timeout_seconds)
        _copy("")

    t = threading.Thread(target=_clear, daemon=True)
    t.start()


class VaultEntry:
    def __init__(
        self,
        title: str,
        username: str,
        password: str,
        url: str = "",
        notes: str = "",
        entry_id: Optional[str] = None,
        updated_at: Optional[int] = None
    ):
        self.id = entry_id or str(uuid.uuid4())
        self.title = title.strip()
        self.username = username.strip()
        self.password = password
        self.url = url.strip()
        self.notes = notes.strip()
        self.updated_at = updated_at or int(time.time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "username": self.username,
            "password": self.password,
            "url": self.url,
            "notes": self.notes,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VaultEntry":
        return cls(
            entry_id=data.get("id"),
            title=data.get("title", ""),
            username=data.get("username", ""),
            password=data.get("password", ""),
            url=data.get("url", ""),
            notes=data.get("notes", ""),
            updated_at=data.get("updated_at")
        )


class Vault:
    def __init__(self, filepath: str = "vault.enc"):
        self.filepath = filepath
        self.entries: List[VaultEntry] = []
        self.vault_key: Optional[bytes] = None
        self.envelope: Optional[dict] = None
        self.updated_at: int = int(time.time())

    @property
    def exists(self) -> bool:
        return os.path.exists(self.filepath)

    def initialize(self, master_password: str) -> str:
        """
        Creates a new vault file.
        Returns the generated Emergency Recovery Key.
        """
        vault_data = {
            "version": 2,
            "updated_at": int(time.time()),
            "entries": []
        }
        envelope_bytes, recovery_key = create_new_vault_envelope(vault_data, master_password)
        
        # Save atomically
        tmp_path = self.filepath + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(envelope_bytes)
        os.replace(tmp_path, self.filepath)

        # Unlock in memory
        self.unlock(master_password)
        return recovery_key

    def unlock(self, master_password: str):
        """Unlocks vault using Master Password."""
        if not self.exists:
            raise FileNotFoundError(f"Vault file '{self.filepath}' does not exist.")
        with open(self.filepath, "rb") as f:
            data = f.read()

        vault_data, vault_key, envelope = unlock_vault_envelope(data, master_password, is_recovery_key=False)
        self.vault_key = vault_key
        self.envelope = envelope
        self.updated_at = vault_data.get("updated_at", int(time.time()))
        self.entries = [VaultEntry.from_dict(item) for item in vault_data.get("entries", [])]

    def reload_from_disk(self):
        """Reloads vault payload from disk using the active Vault Key."""
        if not self.vault_key or not self.exists:
            return
        with open(self.filepath, "rb") as f:
            data = f.read()
        vault_data, _, envelope = unlock_vault_with_key(data, self.vault_key)
        self.envelope = envelope
        self.updated_at = vault_data.get("updated_at", int(time.time()))
        self.entries = [VaultEntry.from_dict(item) for item in vault_data.get("entries", [])]

    def recover(self, recovery_key: str):
        """Unlocks vault using Emergency Recovery Key."""
        if not self.exists:
            raise FileNotFoundError(f"Vault file '{self.filepath}' does not exist.")
        with open(self.filepath, "rb") as f:
            data = f.read()

        vault_data, vault_key, envelope = unlock_vault_envelope(data, recovery_key, is_recovery_key=True)
        self.vault_key = vault_key
        self.envelope = envelope
        self.updated_at = vault_data.get("updated_at", int(time.time()))
        self.entries = [VaultEntry.from_dict(item) for item in vault_data.get("entries", [])]

    def reset_master_password(self, new_password: str):
        """Sets a new Master Password using the verified Vault Key."""
        if not self.vault_key or not self.envelope:
            raise ValueError("Vault must be unlocked before resetting master password.")
        
        updated_envelope_bytes = reset_password_with_vault_key(self.vault_key, new_password, self.envelope)
        tmp_path = self.filepath + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(updated_envelope_bytes)
        os.replace(tmp_path, self.filepath)

    def save(self):
        """Saves updated entries using the existing Vault Key."""
        if not self.vault_key or not self.envelope:
            raise ValueError("Vault must be unlocked before saving.")

        vault_data = {
            "version": 2,
            "updated_at": int(time.time()),
            "entries": [entry.to_dict() for entry in self.entries]
        }
        updated_bytes = reencrypt_vault_data(vault_data, self.vault_key, self.envelope)
        tmp_path = self.filepath + ".tmp"
        with open(tmp_path, "wb") as f:
            f.write(updated_bytes)
        os.replace(tmp_path, self.filepath)

    def add(self, title: str, username: str, password: str, url: str = "", notes: str = "") -> VaultEntry:
        for entry in self.entries:
            if entry.title.lower() == title.lower():
                raise ValueError(f"Entry with title '{title}' already exists. Use update instead.")
        entry = VaultEntry(title=title, username=username, password=password, url=url, notes=notes)
        self.entries.append(entry)
        return entry

    def delete(self, entry_id: str) -> bool:
        initial_len = len(self.entries)
        self.entries = [e for e in self.entries if e.id != entry_id]
        return len(self.entries) < initial_len

    def get_by_title(self, title: str) -> Optional[VaultEntry]:
        for entry in self.entries:
            if entry.title.lower() == title.lower():
                return entry
        return None

    def search(self, query: str) -> List[VaultEntry]:
        q = query.lower()
        return [
            e for e in self.entries
            if q in e.title.lower() or q in e.username.lower() or q in e.url.lower()
        ]
