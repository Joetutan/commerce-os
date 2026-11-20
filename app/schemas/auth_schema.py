from pydantic import BaseModel


class ResponseToken(BaseModel):
    """OAuth2-style token response returned by login."""

    access_token: str
    token_type: str
