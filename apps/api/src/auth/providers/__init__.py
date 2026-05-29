from __future__ import annotations

from enum import StrEnum
from types import ModuleType

from . import google, kakao, naver


class OAuthProvider(StrEnum):
    KAKAO = "kakao"
    NAVER = "naver"
    GOOGLE = "google"


PROVIDER_MODULES: dict[OAuthProvider, ModuleType] = {
    OAuthProvider.KAKAO: kakao,
    OAuthProvider.NAVER: naver,
    OAuthProvider.GOOGLE: google,
}


__all__ = ["OAuthProvider", "PROVIDER_MODULES", "google", "kakao", "naver"]
