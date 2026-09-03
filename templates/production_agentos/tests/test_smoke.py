def test_agent_has_stable_id():
    from agno_app.agent import assistant

    assert assistant.id == "support-assistant-v1"


def test_agentos_app_builds():
    from agno_app.app import app

    paths = {route.path for route in app.routes}
    assert "/health" in paths
    assert "/openapi.json" in paths
