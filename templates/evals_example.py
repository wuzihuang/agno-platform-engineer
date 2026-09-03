"""Accuracy and tool-call reliability evals.

Install:
    uv add 'agno[openai]'
"""

from agno.agent import Agent
from agno.eval.accuracy import AccuracyEval
from agno.eval.reliability import ReliabilityEval
from agno.models.openai import OpenAIChat
from agno.tools.calculator import CalculatorTools


agent = Agent(
    id="calculator-agent",
    model=OpenAIChat(id="gpt-5.6-luna"),
    tools=[CalculatorTools()],
)

accuracy = AccuracyEval(
    name="Calculator Accuracy",
    model=OpenAIChat(id="o4-mini"),
    agent=agent,
    input="What is 10 * 5, then raised to the power of 2?",
    expected_output="2500",
    additional_guidelines="The final numeric answer must be 2500.",
    num_iterations=1,
)


if __name__ == "__main__":
    accuracy_result = accuracy.run(print_results=True)
    if accuracy_result is None:
        raise SystemExit("Accuracy eval returned no result")

    response = agent.run("What is 10 factorial?")
    reliability = ReliabilityEval(
        name="Calculator Tool Reliability",
        agent_response=response,
        expected_tool_calls=["factorial"],
    )
    reliability_result = reliability.run(print_results=True)
    if reliability_result is None:
        raise SystemExit("Reliability eval returned no result")
