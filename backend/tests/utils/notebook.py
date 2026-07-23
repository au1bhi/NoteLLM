import uuid

from sqlmodel import Session

from app.models import Notebook
from tests.utils.utils import random_lower_string


def create_random_notebook(*, db: Session, owner_id: uuid.UUID) -> Notebook:
    notebook = Notebook(title=random_lower_string(), owner_id=owner_id)
    db.add(notebook)
    db.commit()
    db.refresh(notebook)
    return notebook
