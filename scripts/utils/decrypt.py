"""
Decrypt pipeuncle.com API responses.
Encryption: AES-ECB, PKCS7 padding, key: 0f5ef28c56b64e67
"""
import base64
import json
import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

KEY = b"0f5ef28c56b64e67"

def decrypt(encrypted_data: str) -> str:
    """Decrypt AES-ECB encrypted data."""
    cipher = AES.new(KEY, AES.MODE_ECB)
    encrypted_bytes = base64.b64decode(encrypted_data)
    decrypted = cipher.decrypt(encrypted_bytes)
    # Remove PKCS7 padding
    decrypted = unpad(decrypted, AES.block_size, style='pkcs7')
    return decrypted.decode('utf-8')

def api_get(url: str, params: dict = None) -> dict:
    """Make a GET request to pipeuncle API and decrypt the response."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") == 200 and data.get("data"):
        decrypted = decrypt(data["data"])
        try:
            data["data"] = json.loads(decrypted)
        except json.JSONDecodeError:
            data["data"] = decrypted
    return data

# Test: decrypt and show category data
if __name__ == "__main__":
    result = api_get("https://www.pipeuncle.com/api/goods/category")
    print(json.dumps(result, ensure_ascii=False, indent=2)[:5000])
