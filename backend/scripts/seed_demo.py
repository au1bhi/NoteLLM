"""Create one synthetic notebook source for a named existing user."""

import argparse
import shutil
import sys
import uuid
from pathlib import Path

from sqlmodel import Session, select

from app.core.db import engine
from app.models import Notebook, Source, User
from app.services.sources import delete_source, get_upload_path, process_source

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEMO_SOURCE_PATH = REPOSITORY_ROOT / "docs" / "demo" / "notellm_demo_source.md"
DEMO_NOTEBOOK_TITLE = "NoteLLM 答辩演示"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--email", required=True, help="Email of an existing local user."
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace this user's existing synthetic demo notebook if present.",
    )
    return parser.parse_args()


def remove_notebook(*, session: Session, notebook: Notebook) -> None:
    sources = session.exec(
        select(Source).where(Source.notebook_id == notebook.id)
    ).all()
    for source in sources:
        delete_source(session=session, source=source)
    session.delete(notebook)
    session.commit()


def create_demo_notebook(*, session: Session, user: User) -> Notebook:
    notebook = Notebook(
        owner_id=user.id,
        title=DEMO_NOTEBOOK_TITLE,
        description="仅用于本地答辩演示的合成资料，可安全删除。",
    )
    session.add(notebook)
    session.commit()
    session.refresh(notebook)
    source = Source(
        notebook_id=notebook.id,
        display_name=DEMO_SOURCE_PATH.name,
        media_type="text/markdown",
        file_size_bytes=DEMO_SOURCE_PATH.stat().st_size,
        storage_path=f"demo-{uuid.uuid4()}.md",
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    destination = get_upload_path(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DEMO_SOURCE_PATH, destination)
    process_source(session=session, source=source)
    if source.status != "ready":
        delete_source(session=session, source=source)
        session.delete(notebook)
        session.commit()
        raise RuntimeError("Could not process the synthetic demo source")
    return notebook


def main() -> None:
    args = parse_args()
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == args.email)).first()
        if not user:
            raise ValueError("No local user exists with the provided email")
        existing = session.exec(
            select(Notebook)
            .where(Notebook.owner_id == user.id)
            .where(Notebook.title == DEMO_NOTEBOOK_TITLE)
        ).first()
        if existing and not args.replace:
            sys.stdout.write(
                "The synthetic demo notebook already exists. Use --replace to recreate it.\n"
            )
            return
        if existing:
            remove_notebook(session=session, notebook=existing)
        notebook = create_demo_notebook(session=session, user=user)
        notebook_id = notebook.id
    sys.stdout.write(
        f"Created synthetic demo notebook {notebook_id}. Open it in the browser.\n"
    )


if __name__ == "__main__":
    main()
