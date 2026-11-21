"""Global audio rules (plan 2.5); no players needed."""

from mosaicplayer.audio import MPV_MAX, MasterAudio, effective_volume
from mosaicplayer.config import _valid


def test_effective_volume_is_tile_times_master_clamped():
    assert effective_volume(0.5, 0.6) == 0.3
    assert effective_volume(1.0, 0.0) == 0.0
    assert effective_volume(1.5, 1.0) == MPV_MAX  # mpv refuses more than 130 %
    assert effective_volume(-1, 1.0) == 0.0


def test_master_clamps_and_signals_only_real_changes():
    m = MasterAudio(volume=2.0)
    assert m.volume == 1.0
    seen = []
    m.changed.connect(lambda: seen.append(1))
    m.set_volume(1.0)
    m.set_muted(False)
    assert not seen
    m.set_volume(0.333)
    assert m.volume == 0.33 and len(seen) == 1
    m.set_volume(-1)
    assert m.volume == 0.0


def test_silence_combines_master_mute_and_solo_audio():
    m = MasterAudio()
    a, b = object(), object()
    assert not m.silences(a)
    m.set_solo_audio(True)
    m.set_solo_tile(a)
    assert not m.silences(a) and m.silences(b)
    m.set_muted(True)
    assert m.silences(a)


def test_saved_master_volume_is_checked():
    assert _valid("master_volume", "0.4", 1.0) == 0.4
    assert _valid("master_volume", "7", 1.0) == 1.0
    assert _valid("master_volume", "nan", 1.0) is None
