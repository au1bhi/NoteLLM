from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from tests.utils.notebook import create_random_notebook
from tests.utils.user import authentication_token_from_email, create_random_user


def test_create_list_and_read_conversation(
    client: TestClient,
    db: Session,
) -> None:
    user = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=user.id)
    headers = authentication_token_from_email(client=client, email=user.email, db=db)

    created = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
        json={"title": "Grounded notes"},
    )
    assert created.status_code == 200
    conversation = created.json()

    listed = client.get(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=headers,
    )
    assert listed.status_code == 200
    assert conversation["id"] in {item["id"] for item in listed.json()["data"]}

    detail = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}", headers=headers
    )
    assert detail.status_code == 200
    assert detail.json()["messages"] == []


def test_user_cannot_read_another_users_conversation(
    client: TestClient,
    db: Session,
) -> None:
    owner = create_random_user(db)
    notebook = create_random_notebook(db=db, owner_id=owner.id)
    owner_headers = authentication_token_from_email(
        client=client, email=owner.email, db=db
    )
    conversation = client.post(
        f"{settings.API_V1_STR}/notebooks/{notebook.id}/conversations/",
        headers=owner_headers,
        json={},
    ).json()
    other_user = create_random_user(db)
    other_headers = authentication_token_from_email(
        client=client, email=other_user.email, db=db
    )

    response = client.get(
        f"{settings.API_V1_STR}/conversations/{conversation['id']}",
        headers=other_headers,
    )
    assert response.status_code == 404
