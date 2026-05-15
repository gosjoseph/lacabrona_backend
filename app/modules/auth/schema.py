from typing import Optional, TypedDict


class AuthClaims(TypedDict, total=False):
    user_type: str
    internal_id: str
    role: str


class GoogleProfile(TypedDict, total=False):
    full_name: str
    first_name: str
    last_name: str
