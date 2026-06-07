#!/usr/bin/env python3
"""
Secure Vault — encrypted API key storage using Fernet symmetric encryption.
Keys are derived from a machine-specific secret (not stored on disk).
"""

import os
import json
import base64
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any

try:
    from cryptography.fernet import Fernet
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

VAULT_DIR = Path(__file__).parent.parent / "storage"
VAULT_FILE = VAULT_DIR / "vault.enc"
VAULT_META = VAULT_DIR / "vault_meta.json"

# Machine-specific key derivation (tied to hostname + user)
def _derive_key() -> bytes:
    """Derive a Fernet key from machine-specific attributes."""
    import socket
    secret = f"{socket.gethostname()}-{os.getlogin()}-marin-os-vault"
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


class SecureVault:
    """Encrypted key-value store for API keys and secrets."""

    def __init__(self):
        VAULT_DIR.mkdir(parents=True, exist_ok=True)
        self._fernet = Fernet(_derive_key()) if HAS_CRYPTO else None
        self._data: Dict[str, str] = {}
        self._load()

    def _load(self):
        """Load encrypted vault from disk."""
        if not VAULT_FILE.exists():
            self._data = {}
            return
        try:
            encrypted = VAULT_FILE.read_bytes()
            if self._fernet:
                decrypted = self._fernet.decrypt(encrypted)
                self._data = json.loads(decrypted)
            else:
                # Fallback: base64 obfuscation (not real encryption)
                self._data = json.loads(base64.b64decode(encrypted))
        except Exception as e:
            print(f"[Vault] Failed to load: {e}")
            self._data = {}

    def _save(self):
        """Encrypt and save vault to disk."""
        plain = json.dumps(self._data, indent=2).encode()
        if self._fernet:
            encrypted = self._fernet.encrypt(plain)
        else:
            encrypted = base64.b64encode(plain)
        VAULT_FILE.write_bytes(encrypted)
        # Set restrictive permissions
        os.chmod(VAULT_FILE, 0o600)

    def get(self, key: str, default: str = None) -> Optional[str]:
        """Get a secret value by key."""
        return self._data.get(key, default)

    def set(self, key: str, value: str):
        """Set a secret value."""
        self._data[key] = value
        self._save()

    def delete(self, key: str):
        """Delete a secret."""
        self._data.pop(key, None)
        self._save()

    def list_keys(self) -> list:
        """List all stored keys (not values)."""
        return list(self._data.keys())

    def migrate_from_settings(self, settings_path: str):
        """One-time migration from settings.json to encrypted vault."""
        if not os.path.exists(settings_path):
            return
        try:
            with open(settings_path) as f:
                settings = json.load(f)
            api_keys = settings.get("api_keys", {})
            migrated = 0
            for provider, key_data in api_keys.items():
                if isinstance(key_data, dict) and "api_key" in key_data:
                    vault_key = f"{provider}_api_key"
                    if not self.get(vault_key):
                        self.set(vault_key, key_data["api_key"])
                        migrated += 1
                elif isinstance(key_data, str):
                    vault_key = f"{provider}_api_key"
                    if not self.get(vault_key):
                        self.set(vault_key, key_data)
                        migrated += 1
            if migrated:
                print(f"[Vault] Migrated {migrated} API keys from settings.json")
        except Exception as e:
            print(f"[Vault] Migration error: {e}")


# Singleton
_vault: Optional[SecureVault] = None


def get_vault() -> SecureVault:
    global _vault
    if _vault is None:
        _vault = SecureVault()
    return _vault


# Convenience functions
def vault_get(key: str, default: str = None) -> Optional[str]:
    return get_vault().get(key, default)

def vault_set(key: str, value: str):
    get_vault().set(key, value)

def vault_delete(key: str):
    get_vault().delete(key)
