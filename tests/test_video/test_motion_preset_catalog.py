"""Unit tests for the 56 Motion Preset Library and Catalog."""

from video.motion_presets import (
    MotionPresetCatalog,
    PresetCategory,
    count_presets,
)


def test_preset_count_is_56():
    catalog = MotionPresetCatalog.get_instance()
    assert catalog.count() == 56
    assert count_presets() == 56


def test_each_category_has_eight_presets():
    catalog = MotionPresetCatalog.get_instance()
    for cat in PresetCategory:
        cat_presets = catalog.list_presets(cat)
        assert (
            len(cat_presets) == 8
        ), f"Category {cat.value} should have exactly 8 presets, got {len(cat_presets)}"


def test_all_preset_ids_unique():
    catalog = MotionPresetCatalog.get_instance()
    all_specs = catalog.list_presets()
    ids = [p.preset_id for p in all_specs]
    assert len(ids) == 56
    assert len(set(ids)) == 56


def test_preset_spec_validity():
    catalog = MotionPresetCatalog.get_instance()
    for spec in catalog.list_presets():
        assert spec.preset_id and isinstance(spec.preset_id, str)
        assert spec.name and isinstance(spec.name, str)
        assert spec.description and len(spec.description) > 10
        assert 0.0 <= spec.duration_min <= spec.duration_default <= spec.duration_max
        assert spec.render_type in ("ffmpeg", "pil_overlay", "hybrid")
        assert len(spec.tags) >= 2
        assert isinstance(spec.parameters, dict)
        # Test serialization
        d = spec.to_dict()
        assert d["preset_id"] == spec.preset_id
        assert d["category"] == spec.category.value


def test_catalog_query_and_fallbacks():
    catalog = MotionPresetCatalog.get_instance()
    # Test valid lookup
    p = catalog.get("opener_breaking_red_flash")
    assert p is not None
    assert p.category == PresetCategory.OPENER

    # Test tag lookup
    urgents = catalog.find_by_tag("urgent")
    assert len(urgents) >= 1

    # Test fallback
    fallback = catalog.get_or_default("non_existent_preset_xyz")
    assert fallback is not None
    assert fallback.preset_id == "photo_slow_push_in"


def test_manifest_export():
    catalog = MotionPresetCatalog.get_instance()
    manifest = catalog.export_manifest()
    assert manifest["total_presets"] == 56
    assert len(manifest["categories"]) == 7
    for cat_name, items in manifest["categories"].items():
        assert len(items) == 8
