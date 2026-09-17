"""Tests for the memory service (async Qdrant client)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.memory import (
    _collection_name,
    delete_project_memory,
    list_projects,
    search_memory,
    store_memory,
)


class TestCollectionNaming:
    """Test collection name generation (slug + stable hash)."""

    def test_simple_name(self):
        """Should prefix simple names."""
        assert _collection_name("udyat").startswith("project_udyat_")

    def test_name_with_spaces(self):
        """Should replace spaces with underscores."""
        assert _collection_name("my project").startswith("project_my_project_")

    def test_name_with_special_chars(self):
        """Should sanitize special characters."""
        assert _collection_name("my-project.v2").startswith("project_my_project_v2_")

    def test_uppercase_normalized(self):
        """Should lowercase the name."""
        assert _collection_name("MyProject").startswith("project_myproject_")

    def test_no_collisions_between_similar_names(self):
        """Names that sanitize to the same slug must still get distinct collections."""
        names = {"my-project", "my_project", "My Project", "MY-PROJECT"}
        collections = {_collection_name(n) for n in names}
        assert len(collections) == len(collections) - 0  # all distinct
        assert len(set(collections)) == 4

    def test_deterministic(self):
        """Same project name must always yield the same collection name."""
        assert _collection_name("my-project") == _collection_name("my-project")


@pytest.fixture
def mock_async_qdrant():
    """Async Qdrant client mock."""
    client = AsyncMock()
    client.upsert = AsyncMock(return_value=None)
    client.query_points = AsyncMock(return_value=MagicMock(points=[]))
    client.scroll = AsyncMock(return_value=([], None))
    client.create_collection = AsyncMock(return_value=None)
    client.delete_collection = AsyncMock(return_value=None)
    client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    client.get_collection = AsyncMock(side_effect=Exception("not found"))
    return client


@pytest.mark.asyncio
class TestMemoryOperations:
    """Test memory CRUD operations."""

    async def test_store_memory(self, mock_async_qdrant):
        """Should store a memory entry."""
        mock_embedding = [0.1] * 384

        with (
            patch("app.services.memory.get_qdrant", return_value=mock_async_qdrant),
            patch("app.services.memory.ensure_collection", new_callable=AsyncMock),
            patch("app.services.memory.get_embedding", new_callable=AsyncMock, return_value=mock_embedding),
        ):
            point_id = await store_memory(
                text="test content",
                project="test",
                file="test.py",
                memory_type="code",
            )
            assert point_id is not None
            mock_async_qdrant.upsert.assert_awaited_once()

    async def test_search_memory(self, mock_async_qdrant):
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
        mock_async_qdrant.query_points = AsyncMock(
            return_value=MagicMock(points=[mock_hit])
        )
        mock_embedding = [0.1] * 384

        with (
            patch("app.services.memory.get_qdrant", return_value=mock_async_qdrant),
            patch("app.services.memory.get_embedding", new_callable=AsyncMock, return_value=mock_embedding),
        ):
            results = await search_memory(query="test", project="test")
            assert len(results) == 1
            assert results[0]["text"] == "found content"
            assert results[0]["score"] == 0.95

    async def test_delete_project_memory(self, mock_async_qdrant):
        """Should delete a project's collection."""
        expected = _collection_name("test")
        mock_collection = MagicMock()
        mock_collection.name = expected
        mock_async_qdrant.get_collections = AsyncMock(
            return_value=MagicMock(collections=[mock_collection])
        )

        with patch("app.services.memory.get_qdrant", return_value=mock_async_qdrant):
            result = await delete_project_memory("test")
            assert result is True
            mock_async_qdrant.delete_collection.assert_awaited_once_with(
                collection_name=expected
            )

    async def test_list_projects(self, mock_async_qdrant):
        """Should list all projects (stripping the hash suffix)."""
        mock_c1 = MagicMock()
        mock_c1.name = _collection_name("udyat")
        mock_c2 = MagicMock()
        mock_c2.name = _collection_name("chatapp")
        mock_c3 = MagicMock()
        mock_c3.name = "other_collection"

        mock_async_qdrant.get_collections = AsyncMock(
            return_value=MagicMock(collections=[mock_c1, mock_c2, mock_c3])
        )

        with patch("app.services.memory.get_qdrant", return_value=mock_async_qdrant):
            projects = await list_projects()
            assert "udyat" in projects
            assert "chatapp" in projects
            assert len(projects) == 2  # "other_collection" excluded

    async def test_search_all_projects_empty(self, mock_async_qdrant):
        """Searching without a project scans every project collection."""
        mock_embedding = [0.1] * 384
        with (
            patch("app.services.memory.get_qdrant", return_value=mock_async_qdrant),
            patch("app.services.memory.get_embedding", new_callable=AsyncMock, return_value=mock_embedding),
        ):
            results = await search_memory(query="test")
            assert results == []
            mock_async_qdrant.get_collections.assert_awaited()
