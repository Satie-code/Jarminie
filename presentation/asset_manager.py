"""AssetManager (Sprint 5.6 — Level 5 Part A).

A thin, shared helper both concrete renderers (Sprint 5.7's
JarvisRenderer, Sprint 5.8's VTubeStudioAvatarRenderer) use to resolve
asset paths (color/icon/font resources under assets/, the existing
top-level folder from Part 3's own repository structure) rather than
each renderer hardcoding paths independently.

Deliberately does NOT load/decode any actual image, font, or audio
asset this sprint — it only resolves and validates paths. Real asset
loading is each concrete renderer's own job (Sprint 5.7 loads whatever
Qt resources it needs directly; Sprint 5.8's VTube Studio integration
doesn't load local avatar assets at all, since the avatar lives inside
the external VTube Studio process — see that sprint's own Architecture
Notes). Keeping AssetManager this thin avoids guessing at a loading API
two renderers with genuinely different asset needs would both have to
conform to.
"""

from pathlib import Path

_DEFAULT_ASSETS_ROOT = Path(__file__).parent.parent / "assets"


class AssetManager:
    """Constructor DI per 03_Engineering_Standards.md: receives the
    assets_root it resolves against, defaulting to this project's
    existing top-level assets/ folder — never hardcoded inside a
    concrete renderer. A real, if intentionally small, class rather
    than a bag of free functions, so it can be swapped/faked in
    renderer tests the same way MemoryStore/SqliteClient already are."""

    def __init__(self, assets_root: Path | None = None) -> None:
        self._assets_root = assets_root if assets_root is not None else _DEFAULT_ASSETS_ROOT

    def resolve(self, relative_path: str) -> Path:
        """Join relative_path against assets_root and return it only if
        it genuinely exists (file or directory) — a loud, specific
        failure at resolution time (naming the attempted path) is
        preferable to a renderer silently drawing nothing, the same
        "fail loud where the cost of silent failure is confusion, fail
        soft where the cost is a crashed session" judgment this project
        applies throughout (e.g. DeviceControlConfig.
        use_recycle_bin_for_delete's own "refuse to run rather than
        silently downgrade" precedent)."""
        resolved = self._assets_root / relative_path
        if not resolved.exists():
            raise FileNotFoundError(
                f"Asset not found: {resolved!s} "
                f"(assets_root={self._assets_root!s}, relative_path={relative_path!r})"
            )
        return resolved
