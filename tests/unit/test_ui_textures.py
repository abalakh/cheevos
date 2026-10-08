import contextlib
import logging
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from cheevos.ui.pyui import generated, primitives, texture_budget
from cheevos.ui.pyui.texture_budget import TextureLru


@dataclass
class Entry:
    texture: object
    width: int
    height: int


def entry(name, width=10, height=10):
    return Entry(texture=name, width=width, height=height)


def lru(budget_pixels):
    destroyed = []
    return TextureLru(budget_pixels * 4, destroyed.append), destroyed


def test_evicts_the_least_recently_used_over_budget():
    cache, destroyed = lru(250)  # room for two 10x10 textures
    cache["a"] = entry("A")
    cache["b"] = entry("B")
    assert cache.get("a").texture == "A"  # "a" is now the most recent
    cache["c"] = entry("C")
    assert destroyed == ["B"]
    assert list(cache) == ["a", "c"]
    assert cache.used == 2 * 100 * 4


def test_never_evicts_the_texture_just_added():
    cache, destroyed = lru(10)
    cache["small"] = entry("S", 2, 2)
    cache["huge"] = entry("H", 100, 100)
    assert list(cache) == ["huge"]
    assert destroyed == ["S"]


def test_replacing_an_entry_frees_the_old_texture():
    cache, destroyed = lru(1000)
    cache["a"] = entry("old")
    cache["a"] = entry("new")
    assert destroyed == ["old"]
    assert cache.used == 100 * 4
    assert cache.get("missing", "default") == "default"


def test_clear_after_pyui_destroyed_everything():
    cache, destroyed = lru(1000)
    cache["a"] = entry("A")
    for value in cache.values():  # what PyUI's clear_cache does first
        destroyed.append(value.texture)
    cache.clear()
    assert (len(cache), cache.used, destroyed) == (0, 0, ["A"])


def fake_display():
    return SimpleNamespace(
        _text_texture_cache=SimpleNamespace(cache={"t": entry("T")}),
        _image_texture_cache=SimpleNamespace(cache={}),
    )


def test_install_budgets_both_caches_and_keeps_their_textures():
    pytest.importorskip("sdl2")
    display = fake_display()
    texture_budget.install(display, 640, 480)
    text = display._text_texture_cache.cache
    assert isinstance(text, TextureLru)
    assert text.get("t").texture == "T"
    assert text.budget == int(640 * 480 * 4 * texture_budget.TEXT_SCREENS)
    assert isinstance(display._image_texture_cache.cache, TextureLru)
    texture_budget.install(display, 640, 480)  # twice is harmless
    assert display._text_texture_cache.cache is text


def test_install_leaves_an_unexpected_pyui_alone(caplog):
    pytest.importorskip("sdl2")
    display = SimpleNamespace(_text_texture_cache=SimpleNamespace(cache=[]))
    with caplog.at_level(logging.WARNING):
        texture_budget.install(display, 640, 480)
    assert display._text_texture_cache.cache == []
    assert "unbounded" in caplog.text


@pytest.mark.parametrize("fail", [False, True])
def test_session_destroys_textures_once_and_restores_empty_host_dicts(monkeypatch, fail):
    sdl2 = pytest.importorskip("sdl2")
    destroyed = []
    monkeypatch.setattr(sdl2, "SDL_DestroyTexture", destroyed.append)

    class Cache:
        def __init__(self, entries):
            self.cache = entries

        def clear_cache(self):
            for value in self.cache.values():
                destroyed.append(value.texture)
            self.cache.clear()

    host_text = {"host": entry("HOST")}
    host_image = {}
    display = SimpleNamespace(
        _text_texture_cache=Cache(host_text), _image_texture_cache=Cache(host_image)
    )
    expected = pytest.raises(RuntimeError) if fail else contextlib.nullcontext()
    with expected, texture_budget.installed(display, 10, 10):
        images = display._image_texture_cache.cache
        images["a"] = entry("A")
        images["b"] = entry("B")
        images["c"] = entry("C")  # A is evicted, and cannot be freed again on return.
        if fail:
            raise RuntimeError("screen failed")
    assert destroyed == ["HOST", "A", "B", "C"]
    assert display._text_texture_cache.cache is host_text
    assert display._image_texture_cache.cache is host_image
    assert host_text == host_image == {}


def tiny_png(path, shade):
    path.write_bytes(generated.encode_png(8, 8, bytes([shade, shade, shade, 255]) * 64))
    return path


def test_sharp_copies_are_reused_remade_and_bounded(tmp_path):
    pytest.importorskip("sdl2.sdlimage")
    scratch = tmp_path / "scratch"
    first = tiny_png(tmp_path / "shot0.png", 10)
    copy = primitives.sharp_scaled(first, 64, 64, scratch)
    assert copy == scratch / "sharp" / "shot0@8x.bmp"
    assert copy.exists()
    assert primitives.sharp_scaled(first, 64, 64, scratch) == copy
    copy.unlink()
    assert primitives.sharp_scaled(first, 64, 64, scratch).exists()  # made again
    for index in range(1, 7):
        primitives.sharp_scaled(tiny_png(tmp_path / f"shot{index}.png", index), 64, 64, scratch)
    assert len(list((scratch / "sharp").glob("*.bmp"))) == primitives.SHARP_COPIES
    assert (scratch / "sharp" / "shot6@8x.bmp").exists()


def test_a_source_that_already_fills_the_box_is_used_as_is(tmp_path):
    pytest.importorskip("sdl2.sdlimage")
    source = tiny_png(tmp_path / "big.png", 1)
    assert primitives.sharp_scaled(source, 8, 8, tmp_path / "scratch") == source
