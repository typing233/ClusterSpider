from cryptography.fernet import Fernet

from clusterspider.config import settings


def get_fernet() -> Fernet:
    key = settings.fernet_key
    if not key:
        key = Fernet.generate_key().decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_api_key(plaintext: str) -> str:
    f = get_fernet()
    return f.encrypt(plaintext.encode()).decode()


def decrypt_api_key(ciphertext: str) -> str:
    f = get_fernet()
    return f.decrypt(ciphertext.encode()).decode()
