import pytest
from pydantic import ValidationError

from agno_app.schemas import AssistantAnswer


def test_assistant_answer_contract():
    answer = AssistantAnswer(message="Done", suggested_actions=["Open settings"])
    assert answer.message == "Done"
    assert not answer.needs_human


def test_empty_message_is_rejected():
    with pytest.raises(ValidationError):
        AssistantAnswer(message="")
