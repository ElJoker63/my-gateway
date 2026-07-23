"""Tests for the memory service."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from app.services.memory import (
    _collection_name,
    store_memory,
    search_memory,
    list_projects,
    delete_project_memory,
)


class TestCollectionNaming:
    """Test collection name generation."""

    def test_simple_name(self):
        """Should handle simple names."""
        assert _collection_name("udyat") == "project_udyat"

    def test_name_with_spaces(self):
        """Should replace spaces with underscores."""
        assert _collection_name("my project") == "project_my_project"

    def test_name_with_special_chars(self):
        """Should sanitize special characters."""
        assert _collection_name("my-project.v2") == "project_my_project_v2"

    def test_uppercase_normalized(self):
        """Should lowercase the name."""
        assert _collection_name("MyProject") == "project_myproject"


@pytest.mark.asyncio
class TestMemoryOperations:
    """Test memory CRUD operations."""

    async def test_store_memory(self, mock_qdrant):
        """Should store a memory entry."""
        mock_embedding = [0.1] * 384

        with (
            patch("app.services.memory.get_qdrant", return_value=mock_qdrant),
            patch("app.services.memory.ensure_collection"),
            patch("app.services.memory.get_embedding", new_callable=AsyncMock, return_value=mock_embedding),
        ):
            point_id = await store_memory(
                text="test content",
                project="test",
                file="test.py",
                memory_type="code",
            )
            assert point_id is not None
            mock_qdrant.upsert.assert_called_once()

    async def test_search_memory(self, mock_qdrant):
        """Should search for memories."""
        mock_hit = MagicMock()
        mock_hit.id = "test-id"
        mock_hit.score = 0.95
        mock_hit.payload = {
            "text": "found content",
            "project": "test",
            "file": "test.py",
            "type": "code",
            "timestamp": "2024-01-01T00:00:00",
        }
        mock_qdrant.search = MagicMock(return_value=[mock_hit])
        mock_embedding = [0.1] * 384

        with (
            patch("app.services.memory.get_qdrant", return_value=mock_qdrant),
            patch("app.services.memory.get_embedding", new_callable=AsyncMock, return_value=mock_embedding),
        ):
            results = await search_memory(query="test", project="test")
            assert len(results) == 1
            assert results[0]["text"] == "found content"
            assert results[0]["score"] == 0.95

    async def test_delete_project_memory(self, mock_qdrant):
        """Should delete a project's collection."""
        mock_collection = MagicMock()
        mock_collection.name = "project_test"
        mock_qdrant.get_collections = MagicMock(
            return_value=MagicMock(collections=[mock_collection])
        )

        with patch("app.services.memory.get_qdrant", return_value=mock_qdrant):
            result = await delete_project_memory("test")
            assert result is True
            mock_qdrant.delete_collection.assert_called_once_with(
                collection_name="project_test"
            )

    async def test_list_projects(self, mock_qdrant):
        """Should list all projects."""
        mock_c1 = MagicMock()
        mock_c1.name = "project_udyat"
        mock_c2 = MagicMock()
        mock_c2.name = "project_chatapp"
        mock_c3 = MagicMock()
        mock_c3.name = "other_collection"

        mock_qdrant.get_collections = MagicMock(
            return_value=MagicMock(collections=[mock_c1, mock_c2, mock_c3])
        )

        with patch("app.services.memory.get_qdrant", return_value=mock_qdrant):
            projects = await list_projects()
            assert "udyat" in projects
            assert "chatapp" in projects
            assert len(projects) == 2  # "other_collection" excluded
