"""Encryption module for securing МЭШ credentials using Fernet symmetric encryption."""
from cryptography.fernet import Fernet
import os
from typing import Optional


class CredentialEncryption:
    """Handle encryption/decryption of МЭШ credentials."""

    def __init__(self, key: Optional[str] = None):
        """
        Initialize encryption with a key.

        Args:
            key: Base64-encoded Fernet key. If None, loads from ENCRYPTION_KEY env var.
        """
        if key is None:
            key = os.getenv('ENCRYPTION_KEY')

        if not key:
            raise ValueError(
                "ENCRYPTION_KEY not found. Generate one with: "
                "python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        self.cipher = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string.

        Args:
            plaintext: The string to encrypt

        Returns:
            Base64-encoded encrypted string
        """
        if not plaintext:
            return ""

        encrypted = self.cipher.encrypt(plaintext.encode())
        return encrypted.decode()

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a string.

        Args:
            ciphertext: Base64-encoded encrypted string

        Returns:
            Decrypted plaintext string
        """
        if not ciphertext:
            return ""

        decrypted = self.cipher.decrypt(ciphertext.encode())
        return decrypted.decode()


def generate_key() -> str:
    """Generate a new Fernet key for encryption."""
    return Fernet.generate_key().decode()


# Global encryption instance (initialized in bot.py)
_encryptor: Optional[CredentialEncryption] = None


def get_encryptor() -> CredentialEncryption:
    """Get global encryption instance."""
    global _encryptor
    if _encryptor is None:
        _encryptor = CredentialEncryption()
    return _encryptor


# For convenience in other modules
def encrypt(plaintext: str) -> str:
    """Encrypt a string using global encryptor."""
    return get_encryptor().encrypt(plaintext)


def decrypt(ciphertext: str) -> str:
    """Decrypt a string using global encryptor."""
    return get_encryptor().decrypt(ciphertext)
