"""Unit tests for presentation.asset_manager (Sprint 5.6)."""

import pytest

from presentation.asset_manager import AssetManager


@pytest.fixture
def assets_root(tmp_path):
    (tmp_path / "icons").mkdir()
    (tmp_path / "icons" / "jarvis.png").write_bytes(b"fake-png-bytes")
    (tmp_path / "colors.json").write_text("{}")
    return tmp_path


@pytest.fixture
def manager(assets_root) -> AssetManager:
    return AssetManager(assets_root)


def test_resolve_succeeds_for_a_real_existing_file(manager, assets_root):
    resolved = manager.resolve("colors.json")
    assert resolved == assets_root / "colors.json"
    assert resolved.exists()


def test_resolve_succeeds_for_a_real_existing_nested_file(manager, assets_root):
    resolved = manager.resolve("icons/jarvis.png")
    assert resolved == assets_root / "icons" / "jarvis.png"
    assert resolved.exists()


def test_resolve_succeeds_for_a_real_existing_directory(manager, assets_root):
    resolved = manager.resolve("icons")
    assert resolved == assets_root / "icons"
    assert resolved.is_dir()


def test_resolve_fails_with_a_clear_error_for_a_missing_asset(manager):
    with pytest.raises(FileNotFoundError, match="missing_file.png"):
        manager.resolve("missing_file.png")


def test_resolve_error_names_the_full_attempted_path(manager, assets_root):
    with pytest.raises(FileNotFoundError) as exc_info:
        manager.resolve("nested/missing.png")
    assert str(assets_root / "nested" / "missing.png") in str(exc_info.value)


def test_default_assets_root_points_at_the_project_assets_folder():
    manager = AssetManager()
    # The project's own real assets/ folder exists (Part 3's repository
    # structure) even though it currently holds only a .gitkeep — this
    # confirms the default resolves to it, not asserting any specific
    # asset exists inside it yet.
    with pytest.raises(FileNotFoundError) as exc_info:
        manager.resolve("definitely_does_not_exist.png")
    assert "assets" in str(exc_info.value)
