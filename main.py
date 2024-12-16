"""Shopping list API"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from contextlib import asynccontextmanager
from typing import Annotated, Generator, Optional

from passlib.context import CryptContext
import jwt
from fastapi import Depends, FastAPI, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, create_engine, Field, select, Relationship

# models


class Token(BaseModel):
    """JWT token model"""

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """JWT token data model"""

    username: str | None = None


class ShoppingListUser(SQLModel, table=True):
    """Shopping list user model"""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str
    password: str
    created: datetime = Field(default=datetime.now(timezone.utc))
    updated: datetime = Field(default=datetime.now(timezone.utc))


class SubmitShoppingList(BaseModel):
    """Shopping list submission model"""

    open: bool
    items: Optional[list["SubmitItem"]]


class ShoppingList(SQLModel, table=True):
    """Shopping list model"""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="shoppinglistuser.id")
    open: bool
    created: datetime = Field(default=datetime.now(timezone.utc))
    updated: datetime = Field(default=datetime.now(timezone.utc))
    items: list["Item"] = Relationship(back_populates="shopping_list")


class SubmitItem(BaseModel):
    """Shopping list item submission model"""

    name: str
    open: bool


class Item(SQLModel, table=True):
    """Shopping list item model"""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    list_id: uuid.UUID = Field(foreign_key="shoppinglist.id")
    open: bool
    name: str
    created: datetime = Field(default=datetime.now(timezone.utc))
    updated: datetime = Field(default=datetime.now(timezone.utc))
    shopping_list: ShoppingList = Relationship(back_populates="items")


# crypto boilerplate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Generate a hash from a plain password"""
    return pwd_context.hash(password)


# database boilerplate

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)


def create_db_and_tables():
    """Initialize all tables in the DB"""
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    """Get a database session in a context"""
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]

# auth boilerplate


SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = os.environ["ALGORITHM"]
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth")


def authenticate_user(
    session: Session, username: str, password: str
) -> ShoppingListUser | None:
    """Authenticate a user"""
    user = session.exec(
        select(ShoppingListUser).where(ShoppingListUser.name == username)
    ).first()
    if user is None:
        return None
    if not verify_password(password, user.password):
        return None
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a JWT token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_current_user(
    session: SessionDep, token: Annotated[str, Depends(oauth2_scheme)]
) -> ShoppingListUser:
    """Get user information for a token from the client"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except InvalidTokenError as exc:
        raise credentials_exception from exc
    user = session.exec(
        select(ShoppingListUser).where(ShoppingListUser.name == username)
    ).first()
    if user is None:
        raise credentials_exception
    return user


# app boilerplate


@asynccontextmanager
async def lifespan(app):
    """Lifespan definition for the app"""
    create_db_and_tables()
    yield


app = FastAPI(lifespan=lifespan)

origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/auth/")
async def get_access_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()], session: SessionDep
) -> Token:
    """Get a JWT token by user/password authentication"""
    user = authenticate_user(session, form_data.username, form_data.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.name}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


@app.get("/lists/")
async def get_lists(
    current_user: Annotated[ShoppingListUser, Depends(get_current_user)],
    session: SessionDep,
    open: Optional[bool] = None,
) -> list[ShoppingList]:
    """Get and filter shopping lists"""
    if open is not None:
        lists = session.exec(
            select(ShoppingList).where(
                ShoppingList.open == open, ShoppingList.user_id == current_user.id
            )
        ).all()
    else:
        lists = session.exec(
            select(ShoppingList).where(ShoppingList.user_id == current_user.id)
        ).all()
    return list(lists)


@app.post("/lists/")
async def create_list(
    submit_shopping_list: SubmitShoppingList,
    current_user: Annotated[ShoppingListUser, Depends(get_current_user)],
    session: SessionDep,
) -> ShoppingList:
    """Create a shopping list"""
    open_shopping_list = session.exec(
        select(ShoppingList).where(
            ShoppingList.open == True, ShoppingList.user_id == current_user.id
        )
    ).first()
    if open_shopping_list is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot have more than one open list",
        )

    assert submit_shopping_list.items is not None  # explicit here for mypy
    if len(submit_shopping_list.items) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create an empty shopping list",
        )

    shopping_list = ShoppingList(open=True, user_id=current_user.id)
    session.add(shopping_list)
    for submit_item in submit_shopping_list.items:
        item = Item(
            list_id=shopping_list.id, name=submit_item.name, open=submit_item.open
        )
        session.add(item)
    session.commit()
    session.refresh(shopping_list)
    return shopping_list


@app.put("/lists/{list_id}/")
async def update_list(
    submit_shopping_list: SubmitShoppingList,
    list_id: uuid.UUID,
    current_user: Annotated[ShoppingListUser, Depends(get_current_user)],
    session: SessionDep,
    response: Response,
) -> ShoppingList:
    """Update a shopping list"""
    if submit_shopping_list.open:
        open_shopping_list = session.exec(
            select(ShoppingList).where(
                ShoppingList.open == True, ShoppingList.user_id == current_user.id
            )
        ).first()
        if open_shopping_list is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot have more than one open list",
            )

    shopping_list = session.exec(
        select(ShoppingList).where(
            ShoppingList.id == list_id, ShoppingList.user_id == current_user.id
        )
    ).first()
    if shopping_list is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="List not found"
        )

    if submit_shopping_list.open is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return shopping_list

    shopping_list.open = submit_shopping_list.open
    session.add(shopping_list)
    session.commit()
    session.refresh(shopping_list)
    return shopping_list


@app.get("/lists/{list_id}/items/")
async def get_items(
    list_id: uuid.UUID,
    current_user: Annotated[ShoppingListUser, Depends(get_current_user)],
    session: SessionDep,
) -> list[Item]:
    """Get items of a shopping list"""
    shopping_list = session.exec(
        select(ShoppingList).where(
            ShoppingList.user_id == current_user.id, ShoppingList.id == list_id
        )
    ).first()
    # Also handles the case if the list doesn't belong to the user. That case
    # could return 401 unauthorized but no need to tell the user the list
    # exists and belongs to someone else.
    if shopping_list is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="List not found"
        )

    return shopping_list.items


@app.put("/lists/{list_id}/items/{item_id}/")
async def update_item(
    list_id,
    item_id,
    submit_item: SubmitItem,
    current_user: Annotated[ShoppingListUser, Depends(get_current_user)],
    session: SessionDep,
) -> Item:
    """Update shopping list item"""
    shopping_list = session.exec(
        select(ShoppingList).where(
            ShoppingList.user_id == current_user.id,
            ShoppingList.id == uuid.UUID(list_id),
        )
    ).first()
    # if the list does not exist (or does not belong to the user) then the item can't either
    if shopping_list is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    item = session.exec(
        select(Item).where(
            Item.id == uuid.UUID(item_id), Item.list_id == uuid.UUID(list_id)
        )
    ).first()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Item not found"
        )

    item.open = submit_item.open
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
