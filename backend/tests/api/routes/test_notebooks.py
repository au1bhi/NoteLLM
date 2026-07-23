import uuid

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from tests.utils.notebook import create_random_notebook
from tests.utils.user import authentication_token_from_email, create_random_user


def test_create_and_read_notebook(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = client.post(
        f"{settings.API_V1_STR}/notebooks/",
        headers=normal_user_token_headers,
        json={"title": "Course notes", "description": "RAG sources"},
    )
    assert response.status_code == 200
    notebook = response.json()
    assert notebook["title"] == "Course notes"
    assert notebook["description"] == "RAG sources"
    assert notebook["owner_id"]

    response = client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook['id']}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["id"] == notebook["id"]


def test_notebook_is_not_visible_to_another_user(
    client: TestClient, db: Session
) -> None:
    owner = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=owner.id)
    other_user = create_random_user(db)
    other_headers = authentication_token_from_email(
        client=client, email=other_user.email, db=db
    )

    response = client.get(f"{settings.API_V1_STR}/notebooks/", headers=other_headers)
    assert response.status_code == 200
    assert str(notebook.id) not in {entry["id"] for entry in response.json()["data"]}

    for method in ("get", "put", "delete"):
        response = getattr(client, method)(
            f"{settings.API_V1_STR}/notebooks/{notebook.id}",
            headers=other_headers,
            **({"json": {"title": "No access"}} if method == "put" else {}),
        )
        assert response.status_code == 404


def test_update_and_delete_notebook(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    created = client.post(
        f"{settings.API_V1_STR}/notebooks/",
        headers=normal_user_token_headers,
        json={"title": "Original"},
    ).json()
    response = client.put(
        f"{settings.API_V1_STR}/notebooks/{created['id']}",
        headers=normal_user_token_headers,
        json={"title": "Updated"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated"

    response = client.delete(
        f"{settings.API_V1_STR}/notebooks/{created['id']}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Notebook deleted successfully"


def test_read_notebook_not_found(
    client: TestClient, normal_user_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/notebooks/{uuid.uuid4()}",
        headers=normal_user_token_headers,
    )
    assert response.status_code == 404
