"""Tests for config validation and persistence."""

import json

from screenwatch.config import THEME_MODES, Config, Region


def test_defaults_are_not_ready():
    c = Config()
    assert c.is_ready is False


def test_ready_when_region_and_point_set():
    c = Config(region=Region(0, 0, 100, 100), click_x=5, click_y=5)
    assert c.is_ready is True


def test_invalid_region_is_not_ready():
    c = Config(region=Region(0, 0, 0, 0), click_x=5, click_y=5)
    assert c.is_ready is False


def test_clamp_bounds_values():
    c = Config(fps=999, sensitivity=500, pixel_threshold=-5, cooldown=-1,
               max_clicks=-10, downscale_max=1)
    c.clamp()
    assert 0.5 <= c.fps <= 60
    assert 1 <= c.sensitivity <= 100
    assert 0 <= c.pixel_threshold <= 255
    assert c.cooldown >= 0
    assert c.max_clicks == 0
    assert c.downscale_max >= 16


def test_clamp_fixes_bad_enums():
    c = Config(click_button="scroll", click_type="triple", compare_mode="magic")
    c.clamp()
    assert c.click_button == "left"
    assert c.click_type == "single"
    assert c.compare_mode == "previous"


def test_roundtrip_dict():
    c = Config(region=Region(1, 2, 3, 4), click_x=10, click_y=20, sensitivity=77)
    restored = Config.from_dict(c.to_dict())
    assert restored.region == Region(1, 2, 3, 4)
    assert restored.click_x == 10
    assert restored.click_y == 20
    assert restored.sensitivity == 77


def test_from_dict_ignores_unknown_keys():
    c = Config.from_dict({"sensitivity": 42, "totally_unknown": "x"})
    assert c.sensitivity == 42


def test_from_dict_handles_null_region():
    c = Config.from_dict({"region": None})
    assert c.region is None


def test_save_and_load(tmp_path):
    path = str(tmp_path / "cfg.json")
    c = Config(region=Region(5, 6, 7, 8), click_x=1, click_y=2, sensitivity=33)
    c.save(path)
    loaded = Config.load(path)
    assert loaded.region == Region(5, 6, 7, 8)
    assert loaded.sensitivity == 33


def test_load_missing_returns_defaults(tmp_path):
    loaded = Config.load(str(tmp_path / "does_not_exist.json"))
    assert isinstance(loaded, Config)
    assert loaded.region is None


def test_load_corrupt_returns_defaults(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ this is not json ")
    loaded = Config.load(str(path))
    assert isinstance(loaded, Config)


def test_save_is_atomic_and_valid_json(tmp_path):
    path = str(tmp_path / "cfg.json")
    Config(sensitivity=50).save(path)
    with open(path) as fh:
        data = json.load(fh)
    assert data["sensitivity"] == 50


# -- theme (appearance) ----------------------------------------------------
def test_theme_defaults_to_system():
    assert Config().theme == "system"


def test_clamp_fixes_bad_theme():
    c = Config(theme="chartreuse")
    c.clamp()
    assert c.theme == "system"


def test_every_theme_mode_survives_clamp():
    for mode in THEME_MODES:
        c = Config(theme=mode)
        c.clamp()
        assert c.theme == mode


def test_theme_roundtrips(tmp_path):
    path = str(tmp_path / "cfg.json")
    Config(theme="dark").save(path)
    assert Config.load(path).theme == "dark"
    with open(path) as fh:
        assert json.load(fh)["theme"] == "dark"


def test_config_predating_theme_field_still_loads(tmp_path):
    # A config written before `theme` existed must keep working and simply
    # pick up the default, rather than failing to load.
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"sensitivity": 42, "fps": 3.0}))
    c = Config.load(str(path))
    assert c.sensitivity == 42
    assert c.theme == "system"
