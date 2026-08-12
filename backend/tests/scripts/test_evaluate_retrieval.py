import sys
from collections.abc import Generator
from pathlib import Path

import pytest

_SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIRECTORY))

from evaluate_retrieval import (  # noqa: E402
    EvaluationResult,
    load_questions,
    percentile_95,
    render_report,
)


@pytest.fixture(scope="session", autouse=True)
def db() -> Generator[None]:
    """Keep this module offline: do not open the session-scoped Postgres fixture."""
    yield


def _result(**overrides: object) -> EvaluationResult:
    values: dict[str, object] = {
        "answer": None,
        "answer_latency_ms": None,
        "citation_matches_expected_source": None,
        "citation_sources": (),
        "expected_source": "rag_workflow.md",
        "identifier": "Q01",
        "keyword_match": None,
        "question": "默认分块长度是多少？",
        "retrieval_hit": True,
        "retrieval_latency_ms": 12.0,
    }
    values.update(overrides)
    return EvaluationResult(**values)  # type: ignore[arg-type]


def test_load_questions_reads_fixed_evaluation_set() -> None:
    questions = load_questions()

    assert 30 <= len(questions) <= 50
    assert len(questions) == 34
    assert questions[0].identifier == "Q01"
    assert questions[0].expected_source
    assert questions[0].text
    assert questions[0].expected_answer_terms
    assert all(
        question.identifier
        and question.text
        and question.expected_source
        and question.expected_answer_terms
        for question in questions
    )


def test_percentile_95_of_one_through_one_hundred() -> None:
    values = [float(number) for number in range(1, 101)]

    assert 90 <= percentile_95(values) <= 100


def test_render_report_includes_recall_and_question_count_without_answers() -> None:
    results = [
        _result(identifier="Q01"),
        _result(identifier="Q02", retrieval_hit=False, retrieval_latency_ms=40.0),
    ]

    report = render_report(results, answers_enabled=False)

    assert "Recall@" in report
    assert "问题数：2" in report
    assert "待人工复核" not in report


def test_render_report_includes_manual_faithfulness_table_when_answers_enabled() -> None:
    results = [
        _result(
            answer="默认分块长度为 1000 字符。",
            answer_latency_ms=250.0,
            citation_matches_expected_source=True,
            citation_sources=("rag_workflow.md",),
            keyword_match=True,
        )
    ]

    report = render_report(results, answers_enabled=True)

    assert "| ID | 问题 | 期望来源 | 模型回答 | 已验证引用来源 | 人工忠实度 |" in report
    assert "待人工复核" in report
