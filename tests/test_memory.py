import os

os.environ["MOCK_LLM"] = "true"

from factory.memory import format_lessons_for_prompt, load_lessons, record_feedback, record_state_learning
from factory.nodes.learner import learner_node


def test_learning_extracts_next_client_route_config_lesson(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_MEMORY_DIR", str(tmp_path))
    state = {
        "job_id": "job_memory",
        "user_request": "build a war room",
        "prd": {"subcategory": "war_room", "agent_type": "monitoring"},
        "test_results": {
            "passed": 3,
            "failed": 1,
            "errors": [
                "app/page.tsx: client component must not export Next route config `revalidate`"
            ],
        },
        "quality_review": {"score": 80, "grade": "B"},
        "verification": {"skipped": True},
        "log": [],
    }

    result = record_state_learning(state)

    assert result["run_recorded"] is True
    assert result["lessons_added"] == 1
    lessons = load_lessons("war_room")
    assert len(lessons) == 1
    assert "revalidate" in lessons[0]["lesson"]
    assert "Relevant lessons" in format_lessons_for_prompt(state)


def test_learner_node_never_blocks_and_updates_state(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_MEMORY_DIR", str(tmp_path))
    state = {
        "job_id": "job_ok",
        "user_request": "hello",
        "prd": {"subcategory": "war_room"},
        "test_results": {"passed": 1, "failed": 0, "errors": []},
        "log": [],
    }

    final = learner_node(state)

    assert final["current_stage"] == "done"
    assert final["learning"]["run_recorded"] is True


def test_learn_feedback_is_saved_as_global_lesson(tmp_path, monkeypatch):
    monkeypatch.setenv("FACTORY_MEMORY_DIR", str(tmp_path))

    result = record_feedback(
        "Always run npm build before Vercel deploy.",
        source="test",
        context={},
        learn=True,
    )

    assert result["recorded"] is True
    assert result["learned"] is True
    assert "npm build" in format_lessons_for_prompt({"prd": {"subcategory": "war_room"}})
