from __future__ import annotations

from enum import StrEnum
from types import ModuleType

from . import google, kakao, naver
from .base import OAuthProviderError, OAuthTokens, ProviderProfile


class OAuthProvider(StrEnum):
    KAKAO = "kakao"
    NAVER = "naver"
    GOOGLE = "google"


PROVIDER_MODULES: dict[OAuthProvider, ModuleType] = {
    OAuthProvider.KAKAO: kakao,
    OAuthProvider.NAVER: naver,
    OAuthProvider.GOOGLE: google,
}


__all__ = [
    "OAuthProvider",
    "OAuthProviderError",
    "OAuthTokens",
    "ProviderProfile",
    "PROVIDER_MODULES",
    "google",
    "kakao",
    "naver",
]
