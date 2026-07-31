import uuid
from dataclasses import dataclass

from sqlmodel import Session

from app.services.chat import ChatProvider
from app.services.overview import sample_ready_chunks

MAX_SECTIONS = 6
MAX_FAQS = 6


@dataclass(frozen=True)
class StudySection:
    title: str
    content: str


@dataclass(frozen=True)
class StudyFaq:
    question: str
    answer: str


@dataclass(frozen=True)
class StudyGuide:
    sections: list[StudySection]
    faqs: list[StudyFaq]


def build_study_guide_prompt(*, excerpts: str) -> str:
    return f"""Based on the source excerpts below, create a concise study guide: up to {MAX_SECTIONS} sections (each with a short title and a dense summary that could be printed), and up to {MAX_FAQS} frequently asked questions with clear answers.
Return valid JSON with exactly two fields: \"sections\" (an array of objects {{"title": string, "content": string}}) and \"faqs\" (an array of objects {{"question": string, "answer": string}}).

Source excerpts:
{excerpts}
"""


def generate_study_guide(
    *,
    session: Session,
    notebook_id: uuid.UUID,
    chat_provider: ChatProvider,
) -> StudyGuide:
    sampled = sample_ready_chunks(session, notebook_id)
    if not sampled:
        return StudyGuide(sections=[], faqs=[])

    data = chat_provider.complete_json(
        prompt=build_study_guide_prompt(excerpts="\n\n".join(sampled))
    )
    raw_sections = data.get("sections", [])
    raw_faqs = data.get("faqs", [])

    sections: list[StudySection] = []
    for item in raw_sections if isinstance(raw_sections, list) else []:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        content = item.get("content")
        if isinstance(title, str) and isinstance(content, str) and title.strip():
            sections.append(StudySection(title=title.strip(), content=content.strip()))
        if len(sections) >= MAX_SECTIONS:
            break

    faqs: list[StudyFaq] = []
    for item in raw_faqs if isinstance(raw_faqs, list) else []:
        if not isinstance(item, dict):
            continue
        question = item.get("question")
        answer = item.get("answer")
        if isinstance(question, str) and isinstance(answer, str) and question.strip():
            faqs.append(StudyFaq(question=question.strip(), answer=answer.strip()))
        if len(faqs) >= MAX_FAQS:
            break

    return StudyGuide(sections=sections, faqs=faqs)
