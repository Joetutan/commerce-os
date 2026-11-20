"""MVP auth tests covering the flow from HTTP entry to the database."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.configs.auth_security import security
from app.configs.env_settings import get_settings
from app.models.user_model import User, UserRole

REGISTER_URL = "/api/v1/auth/register"
LOGIN_URL = "/api/v1/auth/login"
ME_URL = "/api/v1/auth/me"
PASSWORD = "correct-horse-battery-staple"


def _payload(**overrides: str) -> dict[str, str]:
    """Return a valid registration body, with optional field overrides."""
    data = {
        "username": "alice",
        "email": "alice@example.com",
        "password": PASSWORD,
    }
    data.update(overrides)
    return data


def _register(client, **overrides: str):
    """POST a registration request and return the response."""
    return client.post(REGISTER_URL, json=_payload(**overrides))


def _login(
    client,
    email: str = "alice@example.com",
    password: str = PASSWORD,
):
    """POST login form data and return the response."""
    return client.post(
        LOGIN_URL,
        data={"username": email, "password": password},
    )


def _auth_header(token: str) -> dict[str, str]:
    """Return an `Authorization: Bearer` header for `token`."""
    return {"Authorization": f"Bearer {token}"}


def test_register_success(client, db_session) -> None:
    response = _register(client)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "username", "email"}
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"

    user_id = UUID(body["id"])
    user = db_session.get(User, user_id)
    assert user is not None
    assert user.password_hash != PASSWORD
    assert security().verify_password(PASSWORD, user.password_hash)
    assert user.role == UserRole.CUSTOMER

    stored_role = db_session.execute(
        text("select role from users where id = :id"),
        {"id": user_id},
    ).scalar_one()
    assert stored_role == "customer"


def test_register_rejects_invalid_email(client) -> None:
    response = _register(client, email="string")

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "email"]


def test_register_rejects_duplicate_email(client) -> None:
    assert _register(client).status_code == 201

    response = _register(client, username="bob")

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


def test_login_success(client) -> None:
    registered = _register(client)
    response = _login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"

    settings = get_settings()
    payload = jwt.decode(
        body["access_token"],
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )
    assert payload["sub"] == registered.json()["id"]


def test_login_rejects_wrong_password(client) -> None:
    assert _register(client).status_code == 201

    response = _login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Credentials"


def test_login_unknown_email_matches_wrong_password(client) -> None:
    assert _register(client).status_code == 201

    wrong_password = _login(client, password="wrong-password")
    unknown_email = _login(client, email="nobody@example.com")

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_me_with_valid_token(client) -> None:
    registered = _register(client)
    token = _login(client).json()["access_token"]

    response = client.get(ME_URL, headers=_auth_header(token))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == registered.json()["id"]
    assert body["username"] == "alice"
    assert body["email"] == "alice@example.com"


def test_me_rejects_malformed_token(client) -> None:
    response = client.get(ME_URL, headers=_auth_header("not-a-token"))

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_rejects_expired_token(client) -> None:
    registered = _register(client)
    settings = get_settings()
    expired = jwt.encode(
        {
            "sub": registered.json()["id"],
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get(ME_URL, headers=_auth_header(expired))

    assert response.status_code == 401


def test_duplicate_email_violates_db_constraint(db_session) -> None:
    db_session.add(
        User(
            username="alice",
            email="alice@example.com",
            password_hash="not-a-real-hash",
        )
    )
    db_session.commit()

    db_session.add(
        User(
            username="bob",
            email="alice@example.com",
            password_hash="not-a-real-hash",
        )
    )

    try:
        db_session.commit()
    except IntegrityError:
        db_session.rollback()
    else:
        raise AssertionError("duplicate email should violate the unique constraint")
