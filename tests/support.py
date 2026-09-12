"""Shared bootstrap for the EasyPlayer tests.

Must be imported before PyQt6 - it selects the offscreen platform so the suite
runs without a display, and puts src/ on the path.
"""
import os
import sys
import time
import locale
import shutil
import atexit
import tempfile
import subprocess

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402

_app = None
_media = None


def app():
    """one QApplication for the whole suite"""
    global _app
    if _app is None:
        _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        # QApplication picks up the system locale; libmpv insists on C numerics.
        # EasyPlayer.main() does exactly this after creating the app.
        locale.setlocale(locale.LC_NUMERIC, "C")
    return _app


def spin(ms):
    """run the event loop for ms milliseconds"""
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()


def has(program):
    return shutil.which(program) is not None


# ---------------------------------------------------------------- fixtures

def mediaDir():
    """temp tree of generated media, built once per run

        <dir>/a.png  b.png  movie.mkv  notes.txt
        <dir>/sub/c.png
        <dir>/sub/deeper/d.png
        <dir>/.hidden/skip.png
    """
    global _media
    if _media:
        return _media
    _media = tempfile.mkdtemp(prefix='easyplayer-tests-')
    atexit.register(shutil.rmtree, _media, True)

    for sub in ('sub/deeper', '.hidden'):
        os.makedirs(os.path.join(_media, sub))

    makePicture(os.path.join(_media, 'a.png'), 1600, 900, '#dc3c3c', 'a')
    makePicture(os.path.join(_media, 'b.png'), 1200, 1600, '#3c78dc', 'b')
    makePicture(os.path.join(_media, 'sub', 'c.png'), 800, 600, '#3cb43c', 'c')
    makePicture(os.path.join(_media, 'sub', 'deeper', 'd.png'), 640, 480, '#c8a03c', 'd')
    makePicture(os.path.join(_media, '.hidden', 'skip.png'), 100, 100, '#000000', 'x')
    with open(os.path.join(_media, 'notes.txt'), 'w') as handle:
        handle.write('not media\n')
    makeVideo(os.path.join(_media, 'movie.mkv'))
    return _media


def makePicture(path, w, h, color, label):
    app()
    pixmap = QtGui.QPixmap(w, h)
    pixmap.fill(QtGui.QColor(color))
    painter = QtGui.QPainter(pixmap)
    painter.setPen(QtGui.QColor('white'))
    font = painter.font()
    font.setPointSize(max(12, h // 6))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, label)
    painter.end()
    pixmap.save(path)
    return path


def makeVideo(path, seconds=3):
    if not has('ffmpeg'):
        return None
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                    '-f', 'lavfi', '-i', 'testsrc=duration=%d:size=320x240:rate=10' % seconds,
                    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', path],
                   check=False)
    return path if os.path.exists(path) else None


def makeAvif(path):
    """an image Qt has no plugin for - exercises the ffmpeg fallback"""
    if not has('ffmpeg'):
        return None
    source = os.path.join(mediaDir(), 'a.png')
    subprocess.run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
                    '-i', source, '-c:v', 'libaom-av1', '-still-picture', '1', path],
                   check=False)
    return path if os.path.exists(path) else None


def media(name):
    return os.path.join(mediaDir(), name)


# ------------------------------------------------------------- gui driving

def canDriveGui():
    """the gui smoke test needs a real X display plus xdotool and ImageMagick"""
    if os.environ.get('EASYPLAYER_SKIP_GUI'):
        return False
    if not os.environ.get('DISPLAY'):
        return False
    return has('xdotool') and has('import')


class AppWindow:
    """launch src/EasyPlayer.py on a file and drive its window

    Deliberately not offscreen: this is the only check that the toolbar icons
    reach the screen at all. A missing icomap entry renders an empty button and
    nothing else in the suite would notice.
    """
    TITLE_RE = '^EasyPlayer - '

    def __init__(self, path):
        self.path = path
        self.process = None
        self.wid = None
        self._output = ''
        self.display = os.environ.get('DISPLAY')

    def __enter__(self):
        env = dict(os.environ, DISPLAY=self.display)
        self.process = subprocess.Popen(
            [sys.executable, 'EasyPlayer.py', self.path],
            cwd=SRC, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.wid = self._await()
        if not self.wid:
            self.__exit__(None, None, None)
            raise RuntimeError('EasyPlayer window never appeared')
        self._run(['xdotool', 'windowactivate', '--sync', self.wid])
        self.settle()
        return self

    def __exit__(self, *_):
        if not self.process:
            return False
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        try:
            self._output = self.process.stdout.read() or ''
        except Exception:
            pass
        finally:
            try:
                self.process.stdout.close()
            except Exception:
                pass
        return False

    def _run(self, argv, timeout=25):
        return subprocess.run(argv, capture_output=True, text=True,
                              timeout=timeout,
                              env=dict(os.environ, DISPLAY=self.display))

    def _await(self):
        # --sync blocks until a window matching the pattern exists
        try:
            done = self._run(['xdotool', 'search', '--sync', '--name', self.TITLE_RE])
        except subprocess.TimeoutExpired:
            return None
        ids = [line for line in done.stdout.split() if line.strip()]
        return ids[0] if ids else None

    def settle(self, seconds=1.5):
        time.sleep(seconds)

    def title(self):
        return self._run(['xdotool', 'getwindowname', self.wid]).stdout.strip()

    def key(self, combo):
        self._run(['xdotool', 'key', '--window', self.wid, combo])
        self.settle()

    def keyExpectTitle(self, combo, expected, timeout=10.0):
        """press combo and poll until the window title equals expected.

        The title appears before the folder list has finished loading into
        mpv, so an early keystroke can be a silent no-op. If nothing at all
        registered (title still unchanged), press once more - never when the
        title moved, so a slow but registered step is not doubled."""
        before = self.title()
        self._run(['xdotool', 'key', '--window', self.wid, combo])
        deadline = time.time() + timeout
        retried = False
        while time.time() < deadline:
            time.sleep(0.25)
            now = self.title()
            if now == expected:
                return True
            if not retried and now == before and time.time() > deadline - 6.0:
                self._run(['xdotool', 'key', '--window', self.wid, combo])
                retried = True
        return False

    def capture(self, target):
        self._run(['import', '-window', self.wid, target])
        return target

    def output(self):
        """stdout+stderr, collected when the window was closed"""
        return self._output


# ------------------------------------------------------- playback test rig

def initPlaylistModule():
    """Playlist keeps module level config/icon state - give it harmless stubs"""
    import Playlist

    class Config:
        def get(self, key, default=None): return default
        def set(self, key, value): pass
        def store(self): pass

    class Icons:
        def ico(self, key): return ""

    Playlist.init(Config(), Icons())


class StubMpv:
    def __init__(self, items):
        self._items = list(items)
        self.playlist = [{} for _ in items]
        self.playlist_pos = 0
        self.pause = True

    @property
    def path(self):
        if 0 <= self.playlist_pos < len(self._items):
            return self._items[self.playlist_pos]
        return None


class StubPlayer(QtCore.QObject):
    """the slice of Player that PlaybackController and SlideshowController touch"""
    syncPlayStatus = QtCore.pyqtSignal(int)

    def __init__(self, items, rig):
        super().__init__()
        self._rig = rig
        self.mpv = StubMpv(items)
        self.lastError = None
        self.isPlaylist = len(items) > 1
        self.shown = None

    def setPaused(self, paused):
        self.mpv.pause = paused

    def showImage(self, path):
        self.shown = path

    def hideImage(self):
        self.shown = None

    def hasNextTrack(self):
        return self.mpv.playlist_pos < len(self.mpv.playlist) - 1

    def nextTrack(self):
        """manual navigation wraps, like the real Player"""
        count = len(self.mpv.playlist)
        if count < 2:
            return
        self.mpv.playlist_pos = (self.mpv.playlist_pos + 1) % count
        self._rig.load()

    def prevTrack(self):
        count = len(self.mpv.playlist)
        if count < 2:
            return
        self.mpv.playlist_pos = (self.mpv.playlist_pos - 1) % count
        self._rig.load()


class StubSettings:
    def __init__(self, slideSeconds=1):
        self._slideSeconds = slideSeconds

    def getSlideDuration(self):
        return self._slideSeconds


class StubFrame:
    def __init__(self, settings):
        self.ui_Slider = QtWidgets.QSlider()
        self.ui_InfoLabel = QtWidgets.QLabel()
        self.settings = settings
        self.SLIDER_RESOLUTION = 1000 * 1000


class PlaybackRig:
    """real SlideshowController + real PlaybackController over a stub player"""

    def __init__(self, items, slideSeconds=1):
        app()
        from Slideshow import SlideshowController
        from EasyPlayer import PlaybackController

        self.items = list(items)
        self.settings = StubSettings(slideSeconds)
        self.player = StubPlayer(items, self)
        self.slideshow = SlideshowController(self.player, StubFrame(self.settings))
        self.playback = PlaybackController(self.player, self.slideshow)
        self.slideshow.slideEnded.connect(self.playback.onItemEnded)
        self.icon = 'Play'
        self.player.syncPlayStatus.connect(self._onSync)

    def _onSync(self, playing):
        self.icon = 'Pause' if playing else 'Play'

    def open(self, playing, follow):
        """as if a stream had just been opened with that intent"""
        self.playback.setInitial(playing=playing, follow=follow)
        self.load()

    def load(self):
        """a new item reached the screen"""
        path = self.player.mpv.path
        if path:
            self.slideshow.onTrackChanged(path)
        self.playback.onItemLoaded()

    @property
    def pos(self):
        return self.player.mpv.playlist_pos

    @property
    def timerArmed(self):
        return self.slideshow._slideTimer.isActive()

    @property
    def showingStill(self):
        return self.slideshow.isShowingStill()
