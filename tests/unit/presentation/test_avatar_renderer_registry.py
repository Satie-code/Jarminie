"""Unit tests for presentation.avatar_renderer_registry."""

import pytest

from config.schema import PresentationConfig
from presentation.avatar_renderer_registry import UnknownAvatarBackendError, create_avatar_renderer
from presentation.vtube_studio_renderer import VTubeStudioAvatarRenderer


def test_create_avatar_renderer_resolves_vtube_studio_by_default():
    renderer = create_avatar_renderer(PresentationConfig())
    assert isinstance(renderer, VTubeStudioAvatarRenderer)


def test_create_avatar_renderer_passes_the_config_through():
    config = PresentationConfig(vtube_studio_host="192.168.1.50")
    renderer = create_avatar_renderer(config)
    assert renderer._config is config


def test_create_avatar_renderer_raises_for_an_unknown_backend():
    config = PresentationConfig(avatar_backend="unreal_bridge")
    with pytest.raises(UnknownAvatarBackendError, match="unreal_bridge"):
        create_avatar_renderer(config)


def test_unknown_backend_error_names_every_registered_option():
    config = PresentationConfig(avatar_backend="does_not_exist")
    with pytest.raises(UnknownAvatarBackendError, match="vtube_studio"):
        create_avatar_renderer(config)


def test_create_avatar_renderer_never_silently_falls_back():
    """A typo/blank value must raise, never silently resolve to the
    default backend (Acceptance Criteria: "never a silent fallback")."""
    config = PresentationConfig(avatar_backend="vtube_studioo")  # typo
    with pytest.raises(UnknownAvatarBackendError):
        create_avatar_renderer(config)
