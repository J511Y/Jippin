"""CODEF password RSA 암호화 (ADR-0008: 기존 ``cryptography`` 의존성만 사용).

CODEF 는 세움터 password 를 평문 전송하지 않고 RSA 공개키로 암호화한 뒤 Base64
문자열로 보내라고 요구한다. 공개키는 ``settings.codef_public_key`` 로 주입되며
Base64 인코딩된 DER ``SubjectPublicKeyInfo`` 가 정본 형태다. PEM 형태도 허용한다.

평문 password 는 이 모듈 호출부에서만 잠깐 메모리에 존재해야 하고 로그/Redis/DB 어디에도
남기지 않는다(ADR-0008 §2.3). 이 모듈은 평문을 로깅하지 않는다.

TODO(실서버 검증): CODEF PDF 스펙상 패딩은 PKCS#1 v1.5 로 명시되어 있어 그대로
구현했다. 만약 실응답이 복호화 실패를 반환하면 OAEP 등 다른 패딩으로 재확인이 필요하다.
"""

from __future__ import annotations

import base64
import binascii

from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.serialization import (
    load_der_public_key,
    load_pem_public_key,
)

from .types import CodefError


def _load_public_key(public_key: str) -> rsa.RSAPublicKey:
    """``settings.codef_public_key`` 를 RSA 공개키로 로드한다.

    우선순위: (1) Base64(DER) → load_der, (2) PEM 폴백 → load_pem.
    """

    text = (public_key or "").strip()
    if not text:
        raise CodefError("CODEF RSA 공개키가 설정되지 않았습니다.")

    # 1) Base64(DER SubjectPublicKeyInfo) — 정본 형태.
    if "-----BEGIN" not in text:
        try:
            der = base64.b64decode(text, validate=True)
            key = load_der_public_key(der)
            if isinstance(key, rsa.RSAPublicKey):
                return key
        except (binascii.Error, ValueError):
            pass  # PEM 폴백으로 진행.

    # 2) PEM 폴백.
    try:
        pem_bytes = text.encode("ascii")
        key = load_pem_public_key(pem_bytes)
    except (UnicodeEncodeError, ValueError) as exc:
        raise CodefError("CODEF RSA 공개키를 해석할 수 없습니다.") from exc

    if not isinstance(key, rsa.RSAPublicKey):
        raise CodefError("CODEF RSA 공개키가 RSA 형식이 아닙니다.")
    return key


def encrypt_password(plain_password: str, public_key: str) -> str:
    """평문 password 를 RSA(PKCS#1 v1.5)로 암호화하고 Base64 문자열로 반환한다.

    반환값만 전송에 쓰고, 인자 ``plain_password`` 는 호출부가 사용 직후 폐기해야 한다.
    """

    key = _load_public_key(public_key)
    ciphertext = key.encrypt(plain_password.encode("utf-8"), padding.PKCS1v15())
    return base64.b64encode(ciphertext).decode("ascii")
