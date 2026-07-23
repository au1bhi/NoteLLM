"""Run the fixed synthetic retrieval evaluation against configured providers."""

import argparse
import csv
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.models import Notebook, Source, User
from app.services.answers import GroundedAnswer, answer_question
from app.services.chat import get_chat_provider
from app.services.embeddings import get_embedding_provider
from app.services.retrieval import retrieve_chunks
from app.services.sources import delete_source, get_upload_path, process_source

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIRECTORY = REPOSITORY_ROOT / "docs" / "evaluation"
SOURCES_DIRECTORY = EVALUATION_DIRECTORY / "sources"
QUESTIONS_PATH = EVALUATION_DIRECTORY / "questions.csv"


@dataclass(frozen=True)
class EvaluationQuestion:
    expected_answer_terms: tuple[str, ...]
    expected_source: str
    identifier: str
    text: str


@dataclass(frozen=True)
class EvaluationResult:
    answer: str | None
    answer_latency_ms: float | None
    citation_matches_expected_source: bool | None
    citation_sources: tuple[str, ...]
    expected_source: str
    identifier: str
    keyword_match: bool | None
    question: str
    retrieval_hit: bool
    retrieval_latency_ms: float


def load_questions() -> list[EvaluationQuestion]:
    with QUESTIONS_PATH.open(encoding="utf-8", newline="") as input_file:
        rows = list(csv.DictReader(input_file))
    questions = [
        EvaluationQuestion(
            expected_answer_terms=tuple(
                term.strip()
                for term in row["expected_answer_terms"].split(";")
                if term.strip()
            ),
            expected_source=row["expected_source"],
            identifier=row["id"],
            text=row["question"],
        )
        for row in rows
    ]
    if not 30 <= len(questions) <= 50:
        raise ValueError("The fixed evaluation set must contain 30 to 50 questions")
    if any(
        not question.expected_answer_terms
        or not question.expected_source
        or not question.identifier
        or not question.text
        for question in questions
    ):
        raise ValueError(
            "Every evaluation question needs an id, source, terms, and text"
        )
    return questions


def percentile_95(values: list[float]) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * 0.95))
    return ordered[index]


def current_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        check=False,
        cwd=REPOSITORY_ROOT,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def render_report(results: list[EvaluationResult], *, answers_enabled: bool) -> str:
    retrieval_latencies = [result.retrieval_latency_ms for result in results]
    retrieval_recall = mean(result.retrieval_hit for result in results)
    lines = [
        "# 固定评测结果",
        "",
        "本报告由 `backend/scripts/evaluate_retrieval.py` 从合成语料生成。"
        "运行会创建并清理临时评测数据，不使用用户上传资料。",
        "",
        "## 配置",
        "",
        f"- 运行时间（UTC）：{datetime.now(UTC).isoformat()}",
        f"- 代码提交：{current_commit()}",
        f"- 问题数：{len(results)}",
        "- 检索：pgvector cosine distance，Top-K=5",
        "- 分块：1,000 字符，150 字符重叠",
        f"- 嵌入模型：{settings.EMBEDDING_MODEL or '未配置'}（{settings.EMBEDDING_DIMENSIONS} 维）",
        (
            f"- 聊天模型：{settings.LLM_MODEL or '未调用'}"
            if answers_enabled
            else "- 聊天模型：未调用"
        ),
        "",
        "## 自动指标",
        "",
        f"- Recall@5：{retrieval_recall:.1%}",
        f"- 检索平均耗时：{mean(retrieval_latencies):.0f} ms",
        f"- 检索 P95 耗时：{percentile_95(retrieval_latencies):.0f} ms",
    ]
    if answers_enabled:
        answered = [result for result in results if result.answer is not None]
        answer_latencies = [
            result.answer_latency_ms
            for result in answered
            if result.answer_latency_ms is not None
        ]
        citation_matches = [
            result.citation_matches_expected_source
            for result in answered
            if result.citation_matches_expected_source is not None
        ]
        keyword_matches = [
            result.keyword_match
            for result in answered
            if result.keyword_match is not None
        ]
        lines.extend(
            [
                f"- 回答数：{len(answered)}",
                f"- 回答平均耗时：{mean(answer_latencies):.0f} ms",
                f"- 回答 P95 耗时：{percentile_95(answer_latencies):.0f} ms",
                f"- 引用正确率（自动）：{mean(citation_matches):.1%}",
                f"- 关键词命中率（忠实度筛查）：{mean(keyword_matches):.1%}",
            ]
        )
    lines.extend(
        [
            "",
            "## 解释与人工复核",
            "",
            "引用正确率只检查至少一条已验证引用是否来自标注的期望来源；"
            "关键词命中率不等同于回答忠实度。论文定稿前应逐题阅读答案和引用摘录，"
            "记录人工忠实度结论及异常原因。",
            "",
            "## 逐题结果",
            "",
            "| ID | Recall@5 | 检索 ms | 回答 ms | 引用来源匹配 | 关键词命中 |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for result in results:
        answer_latency = (
            f"{result.answer_latency_ms:.0f}" if result.answer_latency_ms else "-"
        )
        citation_match = (
            "-"
            if result.citation_matches_expected_source is None
            else "是"
            if result.citation_matches_expected_source
            else "否"
        )
        keyword_match = (
            "-"
            if result.keyword_match is None
            else "是"
            if result.keyword_match
            else "否"
        )
        lines.append(
            f"| {result.identifier} | {'是' if result.retrieval_hit else '否'} | "
            f"{result.retrieval_latency_ms:.0f} | {answer_latency} | {citation_match} | "
            f"{keyword_match} |"
        )
    if answers_enabled:
        lines.extend(
            [
                "",
                "## 人工忠实度复核表",
                "",
                "下表只包含合成语料的输出。请逐题核对回答是否仅由引用来源支持，"
                "并将“待人工复核”替换为“通过”或“未通过”，再简述异常原因。",
                "",
                "| ID | 问题 | 期望来源 | 模型回答 | 已验证引用来源 | 人工忠实度 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for result in results:
            lines.append(
                f"| {result.identifier} | {markdown_cell(result.question)} | "
                f"{result.expected_source} | {markdown_cell(result.answer or '')} | "
                f"{', '.join(result.citation_sources)} | 待人工复核 |"
            )
    return "\n".join(lines) + "\n"


def prepare_sources(*, session: Session, notebook: Notebook) -> list[Source]:
    sources: list[Source] = []
    for source_file in sorted(SOURCES_DIRECTORY.glob("*.md")):
        source = Source(
            notebook_id=notebook.id,
            display_name=source_file.name,
            media_type="text/markdown",
            file_size_bytes=source_file.stat().st_size,
            storage_path=f"evaluation-{uuid.uuid4()}.md",
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        destination = get_upload_path(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, destination)
        process_source(session=session, source=source)
        if source.status != "ready":
            raise RuntimeError(
                f"Could not process evaluation source {source_file.name}"
            )
        sources.append(source)
    if not sources:
        raise ValueError("No evaluation sources were found")
    return sources


def evaluate(
    *,
    session: Session,
    notebook: Notebook,
    questions: list[EvaluationQuestion],
    answers_enabled: bool,
) -> list[EvaluationResult]:
    embedding_provider = get_embedding_provider()
    chat_provider = get_chat_provider() if answers_enabled else None
    results: list[EvaluationResult] = []
    for question in questions:
        retrieval_started_at = time.perf_counter()
        retrieved = retrieve_chunks(
            session=session,
            embedding_provider=embedding_provider,
            notebook_id=notebook.id,
            query=question.text,
        )
        retrieval_latency_ms = (time.perf_counter() - retrieval_started_at) * 1000
        retrieval_hit = any(
            item.source_display_name == question.expected_source for item in retrieved
        )
        answer: GroundedAnswer | None = None
        answer_latency_ms: float | None = None
        if chat_provider:
            answer_started_at = time.perf_counter()
            answer = answer_question(
                chat_provider=chat_provider,
                embedding_provider=embedding_provider,
                notebook_id=notebook.id,
                query=question.text,
                session=session,
            )
            answer_latency_ms = (time.perf_counter() - answer_started_at) * 1000
        cited_sources = (
            {citation.source_display_name for citation in answer.citations}
            if answer
            else set()
        )
        results.append(
            EvaluationResult(
                answer=answer.content if answer else None,
                answer_latency_ms=answer_latency_ms,
                citation_matches_expected_source=(
                    question.expected_source in cited_sources if answer else None
                ),
                citation_sources=tuple(sorted(cited_sources)),
                expected_source=question.expected_source,
                identifier=question.identifier,
                keyword_match=(
                    all(
                        term in answer.content
                        for term in question.expected_answer_terms
                    )
                    if answer
                    else None
                ),
                question=question.text,
                retrieval_hit=retrieval_hit,
                retrieval_latency_ms=retrieval_latency_ms,
            )
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional Markdown report path, relative to the current directory.",
    )
    parser.add_argument(
        "--with-answers",
        action="store_true",
        help="Also call the configured chat provider to measure citations and answers.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    questions = load_questions()
    with Session(engine) as session:
        user = User(
            email=f"evaluation-{uuid.uuid4()}@example.invalid",
            hashed_password="evaluation-only",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        notebook = Notebook(title="Fixed evaluation notebook", owner_id=user.id)
        session.add(notebook)
        session.commit()
        session.refresh(notebook)
        sources: list[Source] = []
        try:
            sources = prepare_sources(session=session, notebook=notebook)
            results = evaluate(
                session=session,
                notebook=notebook,
                questions=questions,
                answers_enabled=args.with_answers,
            )
        finally:
            for source in sources:
                delete_source(session=session, source=source)
            session.delete(user)
            session.commit()
    report = render_report(results, answers_enabled=args.with_answers)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(report, encoding="utf-8")
    sys.stdout.write(report)


if __name__ == "__main__":
    main()
