import faulthandler
import sys

import PySide6.QtCore
import pytest
from PySide6.QtCore import QSettings

if sys.platform == "win32":
    class _FileSettings(QSettings):
        """QSettings("org", "app") in an INI file instead of the registry.

        On Windows the native format is the registry, which QSettings.setPath
        cannot redirect: the tests wrote to (and cleared) the real settings
        under HKCU\\Software\\mosaicplayer. Swapped in before the app's modules
        import QSettings, so they get this class too.
        """

        def __init__(self, *args, **kwargs):
            if len(args) >= 1 and isinstance(args[0], str):
                super().__init__(QSettings.IniFormat, QSettings.UserScope, *args, **kwargs)
            else:
                super().__init__(*args, **kwargs)

    PySide6.QtCore.QSettings = _FileSettings
    QSettings = _FileSettings


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    """On Windows, turn off the faulthandler that pytest turns on.

    libmpv's LuaJIT raises (and itself handles) SEH exceptions whenever a player
    loads its built-in scripts. On Windows, faulthandler reports every such
    exception by walking all other threads' stacks while they run, which crashed
    the test process (access violation) in the GUI tests. The app itself does
    not enable faulthandler.
    """
    if sys.platform == "win32":
        faulthandler.disable()


@pytest.fixture(autouse=True, scope="session")
def isolated_settings(tmp_path_factory):
    """Keep tests away from the real ~/.config/mosaicplayer (window size, settings)."""
    folder = str(tmp_path_factory.mktemp("qsettings"))
    for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
        QSettings.setPath(fmt, QSettings.UserScope, folder)
    yield folder
