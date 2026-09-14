"""Tests for recommendation dispatcher, backend selection, and fallback (Track 2)."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.rec_common import RecommenderError, recommend_rule, skill_match
from app.services.recommendations import _build_outputs, recommendation_status


def _make_challenge(**kwargs):
    c = MagicMock()
    c.id = kwargs.get("id", uuid.uuid4())
    c.slug = kwargs.get("slug", "test-challenge")
    c.title = kwargs.get("title", "Test Challenge")
    c.category = kwargs.get("category", "web")
    c.difficulty = kwargs.get("difficulty", "easy")
    c.points = kwargs.get("points", 100)
    c.difficulty_score = kwargs.get("difficulty_score", 0.3)
    c.status = kwargs.get("status", "published")
    return c


def _make_skill(**kwargs):
    s = MagicMock()
    s.id = kwargs.get("id", uuid.uuid4())
    s.slug = kwargs.get("slug", "test-skill")
    s.name = kwargs.get("name", "Test Skill")
    s.icon = kwargs.get("icon", "🔧")
    return s


class TestBuildOutputs:
    def test_builds_with_correct_source(self):
        c = _make_challenge()
        items = [{"challenge": c, "skills": [], "score": 0.5}]
        results = _build_outputs(items, "graph")
        assert len(results) == 1
        assert results[0].source == "graph"
        assert results[0].recommendation_score == 0.5

    def test_includes_skills(self):
        c = _make_challenge()
        s = _make_skill()
        items = [{"challenge": c, "skills": [s], "score": 1.0}]
        results = _build_outputs(items, "rule")
        assert len(results[0].skills) == 1
        assert results[0].skills[0].name == "Test Skill"


class TestRecommendRule:
    @pytest.mark.asyncio
    async def test_empty_competency_sorts_by_points(self):
        c1 = _make_challenge(points=200)
        c2 = _make_challenge(points=50)
        items = [
            {"challenge": c1, "skills": []},
            {"challenge": c2, "skills": []},
        ]
        result = await recommend_rule(items, {}, 2)
        assert result[0]["challenge"].points == 50

    @pytest.mark.asyncio
    async def test_with_competency_scores(self):
        skill_id = uuid.uuid4()
        s = _make_skill(id=skill_id)
        c = _make_challenge(difficulty_score=0.5)
        items = [{"challenge": c, "skills": [s]}]
        competency = {skill_id: 50.0}
        result = await recommend_rule(items, competency, 10)
        assert len(result) == 1
        assert "score" in result[0]


class TestSkillMatch:
    def test_no_skills_returns_zero(self):
        c = _make_challenge()
        assert skill_match(c, [], {}) == 0.0

    def test_matching_skill(self):
        c = _make_challenge()
        sid = uuid.uuid4()
        s = _make_skill(id=sid)
        result = skill_match(c, [s], {sid: 75.0})
        assert result == 75.0


class TestRecommendationStatus:
    @pytest.mark.asyncio
    async def test_returns_rule_backend(self):
        with patch("app.services.recommendations.get_settings") as mock_settings:
            mock_settings.return_value.recommendation_backend = "rule"
            result = await recommendation_status()
            assert result["backend"] == "rule"
            assert result["healthy"] is True
            assert result["model_path"] is None

    @pytest.mark.asyncio
    async def test_returns_gnn_unhealthy_when_missing(self):
        with patch("app.services.recommendations.get_settings") as mock_settings:
            mock_settings.return_value.recommendation_backend = "gnn"
            mock_settings.return_value.gnn_model_path = "/nonexistent/model.onnx"
            with patch(
                "app.services.rec_gnn.load_gnn_session",
                side_effect=RecommenderError("not found"),
            ):
                result = await recommendation_status()
                assert result["backend"] == "gnn"
                assert result["healthy"] is False
