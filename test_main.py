"""Test shopping list API"""

import uuid
from datetime import datetime

import pytest
from sqlmodel import Session, create_engine, SQLModel, StaticPool, select
from fastapi.testclient import TestClient

from main import (
    app,
    get_password_hash,
    ShoppingListUser,
    ShoppingList,
    Item,
    get_session,
)


@pytest.fixture(name="session")
def session_fixture():
    """In-memory database session fixture"""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    """FastAPI client fixture"""

    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture(name="test_user")
def user_fixture(session: Session):
    """Test user fixture for authentication and ownership"""
    user = ShoppingListUser(
        id=uuid.UUID("128f9fc6-dc62-4a22-859f-cd517c98a7d4"),
        name="test",
        password=get_password_hash("test"),
        created=datetime(2024, 11, 30, 20, 26, 50, 612472),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612472),
    )
    session.add(user)
    session.commit()
    return user


@pytest.fixture(name="access_token")
def token_fixture(client: TestClient, test_user: ShoppingListUser):
    """Auth token fixture using the test user"""
    response = client.post(
        "/auth/",
        data={"grant_type": "password", "username": "test", "password": "test"},
    )
    return response.json()["access_token"]


def test_auth(session: Session, client: TestClient):
    """Test authentication"""
    user = ShoppingListUser(
        id=uuid.UUID("128f9fc6-dc62-4a22-859f-cd517c98a7d4"),
        name="test",
        password=get_password_hash("test"),
        created=datetime(2024, 11, 30, 20, 26, 50, 612472),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612472),
    )
    session.add(user)
    session.commit()
    response = client.post(
        "/auth/",
        data={"grant_type": "password", "username": "test", "password": "test"},
    )
    assert response.status_code == 200
    response_json = response.json()
    assert "access_token" in response_json
    assert "token_type" in response_json

    response = client.get(
        "/lists/", headers={"Authorization": f"Bearer {response_json['access_token']}"}
    )
    assert response.status_code == 200

    client.cookies.set("bearer", response_json["access_token"])
    response = client.get("/lists/")
    client.cookies.delete("bearer")
    assert response.status_code == 200

    response = client.post(
        "/auth/",
        data={"grant_type": "password", "username": "test", "password": "wrong"},
    )
    assert response.status_code == 401


def test_get_lists(
    session: Session, client: TestClient, test_user: ShoppingListUser, access_token: str
):
    """Test retrieving and filtering lists"""
    shopping_list = ShoppingList(
        id=uuid.UUID("229b09f1-e6e3-4b79-9dc5-70d968f47de8"),
        user_id=test_user.id,
        open=True,
        created=datetime(2024, 11, 30, 20, 26, 50, 612473),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612473),
    )
    session.add(shopping_list)
    other_shopping_list = ShoppingList(
        id=uuid.UUID("fd1221f8-88b5-4108-b12c-79ea71159832"),
        user_id=test_user.id,
        open=False,
        created=datetime(2024, 11, 30, 20, 26, 50, 612474),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612474),
    )
    session.add(other_shopping_list)
    another_shopping_list = ShoppingList(
        id=uuid.UUID("eafc9b57-6502-4752-bed6-d5bdf1ccd034"),
        user_id=uuid.UUID("8067f1ef-2708-4535-8dec-79faa63b77d0"),
        open=True,
        created=datetime(2024, 11, 30, 20, 26, 50, 612474),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612474),
    )
    session.add(another_shopping_list)
    session.commit()
    response = client.get(
        "/lists/", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    response_json = response.json()
    assert len(response_json) == 2

    response = client.get(
        "/lists/",
        params={"open": True},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    response_json = response.json()
    assert len(response_json) == 1
    assert uuid.UUID(response_json[0]["id"]) == shopping_list.id

    response = client.get(
        "/lists/",
        params={"open": False},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    response_json = response.json()
    assert len(response_json) == 1
    assert uuid.UUID(response_json[0]["id"]) == other_shopping_list.id


def test_create_lists(session: Session, client: TestClient, access_token: str):
    """Test creating lists"""
    shopping_list = {"open": True, "items": []}
    response = client.post(
        "/lists/",
        headers={"Authorization": f"Bearer {access_token}"},
        json=shopping_list,
    )
    assert response.status_code == 400

    shopping_list["items"] = [
        {"name": "Milk", "open": True},
        {"name": "Eggs", "open": True},
    ]
    response = client.post(
        "/lists/",
        headers={"Authorization": f"Bearer {access_token}"},
        json=shopping_list,
    )
    assert response.status_code == 200
    response_json = response.json()
    reponse_id = uuid.UUID(response_json["id"])
    assert reponse_id is not None
    database_shopping_list = session.exec(
        select(ShoppingList).where(ShoppingList.id == reponse_id)
    ).first()
    assert database_shopping_list is not None
    shopping_list_items: list = shopping_list["items"]  # type: ignore
    assert len(database_shopping_list.items) == len(shopping_list_items)
    for database_item, item in zip(database_shopping_list.items, shopping_list_items):
        assert database_item.name == item["name"]

    response = client.post(
        "/lists/",
        headers={"Authorization": f"Bearer {access_token}"},
        json=shopping_list,
    )
    assert response.status_code == 403


def test_update_list(
    session: Session, client: TestClient, test_user: ShoppingListUser, access_token: str
):
    """Test updating lists"""
    shopping_list = ShoppingList(
        id=uuid.UUID("229b09f1-e6e3-4b79-9dc5-70d968f47de8"),
        user_id=test_user.id,
        open=True,
        created=datetime(2024, 11, 30, 20, 26, 50, 612473),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612473),
    )
    session.add(shopping_list)
    other_shopping_list = ShoppingList(
        id=uuid.UUID("fd1221f8-88b5-4108-b12c-79ea71159832"),
        user_id=test_user.id,
        open=False,
        created=datetime(2024, 11, 30, 20, 26, 50, 612474),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612474),
    )
    session.add(other_shopping_list)
    another_shopping_list = ShoppingList(
        id=uuid.UUID("eafc9b57-6502-4752-bed6-d5bdf1ccd034"),
        user_id=uuid.UUID("8067f1ef-2708-4535-8dec-79faa63b77d0"),
        open=True,
        created=datetime(2024, 11, 30, 20, 26, 50, 612474),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612474),
    )
    session.add(another_shopping_list)
    session.commit()

    update_list = {"open": True, "items": None}
    response = client.put(
        f"/lists/{other_shopping_list.id}/",
        headers={"Authorization": f"Bearer {access_token}"},
        json=update_list,
    )
    assert response.status_code == 400

    update_list = {"open": False, "items": None}
    response = client.put(
        f"/lists/{shopping_list.id}/",
        headers={"Authorization": f"Bearer {access_token}"},
        json=update_list,
    )
    assert response.status_code == 200
    response_json = response.json()
    assert response_json["open"] is False

    update_list = {"open": False, "items": None}
    response = client.put(
        f"/lists/{another_shopping_list.id}/",
        headers={"Authorization": f"Bearer {access_token}"},
        json=update_list,
    )
    # 404 instead of 401 because there's no need to tell an unauthorized user that a list they have no access to exists
    assert response.status_code == 404


def test_get_items(
    session: Session, client: TestClient, test_user: ShoppingListUser, access_token: str
):
    """Test retrieving items"""
    shopping_list = ShoppingList(
        id=uuid.UUID("229b09f1-e6e3-4b79-9dc5-70d968f47de8"),
        user_id=test_user.id,
        open=True,
        created=datetime(2024, 11, 30, 20, 26, 50, 612473),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612473),
    )
    session.add(shopping_list)
    item = Item(
        id=uuid.UUID("4ea719ea-03ab-432f-a98b-f0524d59d3cb"),
        list_id=shopping_list.id,
        open=True,
        name="Milk",
    )
    session.add(item)
    other_item = Item(
        id=uuid.UUID("9fb1d848-d396-4a3c-8137-e632453f0144"),
        list_id=shopping_list.id,
        open=True,
        name="Eggs",
    )
    session.add(other_item)
    other_shopping_list = ShoppingList(
        id=uuid.UUID("fd1221f8-88b5-4108-b12c-79ea71159832"),
        user_id=uuid.UUID("8067f1ef-2708-4535-8dec-79faa63b77d0"),
        open=True,
        created=datetime(2024, 11, 30, 20, 26, 50, 612474),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612474),
    )
    session.add(other_shopping_list)
    another_item = Item(
        id=uuid.UUID("00f8ec74-4ef9-413d-aa0b-08c2edf39e5e"),
        list_id=other_shopping_list.id,
        open=True,
        name="Someone else's Milk",
    )
    session.add(another_item)
    session.commit()

    response = client.get(
        f"/lists/{shopping_list.id}/items/",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    response_json = response.json()
    assert len(response_json) == 2

    response = client.get(
        f"/lists/{other_shopping_list.id}/items/",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    # 404 instead of 401 because there's no need to tell an unauthorized user that a list they have no access to exists
    assert response.status_code == 404


def test_update_item(
    session: Session, client: TestClient, test_user: ShoppingListUser, access_token: str
):
    """Test updating items"""
    shopping_list = ShoppingList(
        id=uuid.UUID("229b09f1-e6e3-4b79-9dc5-70d968f47de8"),
        user_id=test_user.id,
        open=True,
        created=datetime(2024, 11, 30, 20, 26, 50, 612473),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612473),
    )
    session.add(shopping_list)
    item = Item(
        id=uuid.UUID("4ea719ea-03ab-432f-a98b-f0524d59d3cb"),
        list_id=shopping_list.id,
        open=True,
        name="Milk",
    )
    session.add(item)
    other_shopping_list = ShoppingList(
        id=uuid.UUID("fd1221f8-88b5-4108-b12c-79ea71159832"),
        user_id=uuid.UUID("8067f1ef-2708-4535-8dec-79faa63b77d0"),
        open=True,
        created=datetime(2024, 11, 30, 20, 26, 50, 612474),
        updated=datetime(2024, 11, 30, 20, 26, 50, 612474),
    )
    session.add(other_shopping_list)
    other_item = Item(
        id=uuid.UUID("00f8ec74-4ef9-413d-aa0b-08c2edf39e5e"),
        list_id=other_shopping_list.id,
        open=True,
        name="Someone else's Milk",
    )
    session.add(other_item)
    session.commit()

    item_update = {"name": "Milk", "open": False}
    response = client.put(
        f"/lists/{shopping_list.id}/items/{item.id}",
        headers={"Authorization": f"Bearer {access_token}"},
        json=item_update,
    )
    assert response.status_code == 200
    response_json = response.json()
    assert response_json["open"] is False

    item_update = {"name": "Someone else's Milk", "open": False}
    response = client.put(
        f"/lists/{other_shopping_list.id}/items/{other_item.id}/",
        headers={"Authorization": f"Bearer {access_token}"},
        json=item_update,
    )
    assert response.status_code == 404
