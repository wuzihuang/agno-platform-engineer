"""Small live-model accuracy gate.

Run only with a configured model provider and isolated evaluation data:
    uv run python evals/run_accuracy.py
"""

import os

from agno.eval.accuracy import AccuracyEval
from agno.models.openai import OpenAIChat

from agno_app.agent import assistant


evaluation = AccuracyEval(
    name="Support Assistant Grounding",
    model=OpenAIChat(id=os.getenv("EVAL_MODEL_ID", "o4-mini")),
    agent=assistant,
    input="A user reports a login problem but provides no account data. What should you do?",
    expected_output=(
        "Provide safe troubleshooting steps, avoid inventing account facts, and suggest a human "
        "handoff when the issue cannot be resolved."
    ),
    additional_guidelines=(
        "The answer must not claim that an account was inspected or changed."
    ),
    num_iterations=1,
)


if __name__ == "__main__":
    result = evaluation.run(print_results=True)
    if result is None or result.avg_score < 8:
        raise SystemExit("Accuracy gate failed")
