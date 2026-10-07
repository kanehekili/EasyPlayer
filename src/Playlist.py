# copyright (c) 2026 kanehekili (kanehekili.media@gmail.com)
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License,
# as published by the Free Software Foundation, either version 2 of the License, or (at your option) any
# later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied
# warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the  GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, see <https://www.gnu.org/licenses/>.

from PyQt6 import QtWidgets, QtGui
from PyQt6.QtCore import pyqtSignal
import re
import xml.etree.ElementTree as ET
import FFMPEGTools
from FFMPEGTools import OSTools
from Slideshow import PICTURE_EXTENSIONS

Log = FFMPEGTools.Log

PLAYLIST_EXTENSIONS = {'.m3u', '.m3u8', '.pls', '.xspf'}
MEDIA_EXTENSIONS = {
    '.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.ts', '.m2t',
    '.mts', '.m2ts',
    '.mp3', '.flac', '.ogg', '.wav', '.aac', '.m4a', '.opus', '.wma',
    '.m4v', '.mpg', '.mpeg', '.vob', '.3gp', '.rm', '.rmvb',
}

_ep_config = None
_icomap = None
_lastDir = None


def init(ep_config, icomap):
    global _ep_config, _icomap
    _ep_config = ep_config
    _icomap = icomap


def _getLastDir():
    if _lastDir:
        return _lastDir
    try:
        stored = _ep_config.get("lastDir", None)
        if stored and OSTools().isDirectory(stored):
            return stored
    except Exception:
        pass
    return OSTools().getHomeDirectory()


def _setLastDir(path):
    global _lastDir
    _ostools = OSTools()
    d = path if _ostools.isDirectory(path) else _ostools.getDirectory(path)
    if d and _ostools.isDirectory(d):
        _lastDir = d
        try:
            _ep_config.set("lastDir", d)
            _ep_config.store()
        except Exception:
            pass


def _scanTree(startFile):
    """Every picture/video in the start file's directory tree, sorted."""
    ostools = OSTools()
    root = ostools.getDirectory(startFile)
    if not root or not ostools.isDirectory(root):
        return []
    return ostools.collectFiles(root, MEDIA_EXTENSIONS | PICTURE_EXTENSIONS)


def _formatExts(exts):
    parts = sorted(exts)
    return ' '.join('*' + e for e in parts) + ' ' + ' '.join('*' + e.upper() for e in parts)


class PlaylistParser:
    """m3u/m3u8, pls and xspf - playlist formats are EasyPlayer's domain, not
    an OS service, so this does not belong in OSTools."""

    def parse(self, path):
        """Parse playlist file and return list of absolute paths/URLs."""
        ostools = OSTools()
        base = ostools.getDirectory(ostools.absolutePath(path))
        ext = ostools.getExtension(path).lower()
        entries = []

        def resolve(p):
            p = p.strip()
            if not p:
                return None
            if '://' in p:
                return p
            if not ostools.isAbsolute(p):
                p = ostools.joinPathes(base, p)
            return p

        try:
            if ext in ('.m3u', '.m3u8'):
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            r = resolve(line)
                            if r:
                                entries.append(r)
            elif ext == '.pls':
                with open(path, 'r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        m = re.match(r'File\d+=(.+)', line.strip(), re.IGNORECASE)
                        if m:
                            r = resolve(m.group(1))
                            if r:
                                entries.append(r)
            elif ext == '.xspf':
                ns = {'x': 'http://xspf.org/ns/0/'}
                for loc in ET.parse(path).findall('.//x:location', ns):
                    if loc.text:
                        r = resolve(loc.text)
                        if r:
                            entries.append(r)
        except (OSError, ET.ParseError):
            # unreadable or malformed playlist - expected. Anything else is a
            # bug and must not be swallowed.
            Log.info("Cannot read playlist %s", path)
        return entries


class PlaylistManager:
    def __init__(self):
        self._ostools = OSTools()

    def parse(self, path):
        return PlaylistParser().parse(path)

    def getLastDir(self):
        return _getLastDir()

    def setLastDir(self, path):
        _setLastDir(path)

    def formatExts(self, exts):
        return _formatExts(exts)

    def scanTree(self, startFile):
        return _scanTree(startFile)


class PlaylistListWidget(QtWidgets.QListWidget):
    """QListWidget: InternalMove reorder (Qt handles ghost + line indicator),
    plus OS URL drops for adding files."""
    filesDropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.setDragDropOverwriteMode(False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)


class PlaylistPanel(QtWidgets.QFrame):
    requestPlay      = pyqtSignal(int)  # double-click: play at this playlist index
    requestPrev      = pyqtSignal()
    requestNext      = pyqtSignal()
    requestNew       = pyqtSignal()
    requestPlayToggle = pyqtSignal()
    playlistModified = pyqtSignal()     # contents changed (dirty flag)

    def __init__(self, parent=None, sourcePath=None):
        super().__init__(parent)
        self._paths = []
        self._sourcePath = sourcePath
        self._rootDir = None
        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setFixedWidth(230)
        self._initUI()

    def _initUI(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.nameEdit = QtWidgets.QLineEdit()
        self.nameEdit.setPlaceholderText("Playlist name")
        layout.addWidget(self.nameEdit)

        btnBar = QtWidgets.QHBoxLayout()
        btnBar.setContentsMargins(0, 0, 0, 0)
        btnBar.setSpacing(2)

        def mkbtn(ico_key, tip):
            b = QtWidgets.QToolButton()
            b.setIcon(QtGui.QIcon(_icomap.ico(ico_key)))
            b.setToolTip(tip)
            return b

        self.btnNew  = mkbtn("newList",  "New playlist")
        self.btnPrev = mkbtn("prev",     "Previous track  (Ctrl+Left)")
        self.btnNext = mkbtn("next",     "Next track  (Ctrl+Right)")
        self.btnPlay = mkbtn("playStart", "Play / Pause  (Space)")
        self.btnAdd  = mkbtn("addFile",  "Add files")
        self.btnDel  = mkbtn("delItem",  "Remove selected")
        self.btnSave = mkbtn("saveList", "Save playlist as .m3u")

        for b in (self.btnNew, self.btnPrev, self.btnNext):
            btnBar.addWidget(b)
        btnBar.addStretch()
        btnBar.addWidget(self.btnPlay)
        btnBar.addStretch()
        for b in (self.btnAdd, self.btnDel, self.btnSave):
            btnBar.addWidget(b)
        layout.addLayout(btnBar)

        self.trackList = PlaylistListWidget(self)
        layout.addWidget(self.trackList)

        self.btnNew.clicked.connect(self._onNew)
        self.btnPrev.clicked.connect(self.requestPrev)
        self.btnNext.clicked.connect(self.requestNext)
        self.btnPlay.clicked.connect(self.requestPlayToggle)
        self.btnAdd.clicked.connect(self._onAddFiles)
        self.btnDel.clicked.connect(self._onDeleteSelected)
        self.btnSave.clicked.connect(self._onSave)
        self.trackList.itemDoubleClicked.connect(self._onDoubleClick)
        self.trackList.filesDropped.connect(self._onFilesDropped)
        self.trackList.model().rowsMoved.connect(self._syncPathsFromList)

    # ---- public API ----

    def setTracks(self, paths, name="", sourcePath=None, rootDir=None):
        self._paths = list(paths)
        self._rootDir = rootDir
        if sourcePath is not None:
            self._sourcePath = sourcePath
        self.nameEdit.setText(name)
        self._refreshList()

    def addPaths(self, paths):
        added = False
        for p in paths:
            if OSTools().getExtension(p).lower() not in MEDIA_EXTENSIONS | PICTURE_EXTENSIONS:
                Log.info("Skipping non-media file: %s", p)
                continue
            if p not in self._paths:
                self._paths.append(p)
                self._addItem(p)
                added = True
        if added:
            self.playlistModified.emit()

    def highlightIndex(self, idx):
        if idx is None or not (0 <= idx < self.trackList.count()):
            return
        self.trackList.blockSignals(True)
        self.trackList.setCurrentRow(idx)
        self.trackList.blockSignals(False)

    def setNavEnabled(self, enabled):
        self.btnPrev.setEnabled(enabled)
        self.btnNext.setEnabled(enabled)

    def setPlaying(self, isPlaying):
        ico = "playPause" if isPlaying else "playStart"
        self.btnPlay.setIcon(QtGui.QIcon(_icomap.ico(ico)))

    def getPaths(self):
        return list(self._paths)

    def getName(self):
        return self.nameEdit.text().strip()

    def currentIndex(self):
        return max(0, self.trackList.currentRow())

    # ---- private ----

    def _addItem(self, path):
        """subfolder entries show their path relative to the list's root, so
        they read as subfolder content instead of oddly sorted siblings"""
        label = (OSTools().relativePath(path, self._rootDir)
                 or OSTools().getFileNameOnly(path))
        item = QtWidgets.QListWidgetItem(label)
        item.setToolTip(path)
        self.trackList.addItem(item)

    def _refreshList(self):
        self.trackList.clear()
        for p in self._paths:
            self._addItem(p)

    def _syncPathsFromList(self):
        self._paths = [self.trackList.item(i).toolTip()
                       for i in range(self.trackList.count())]
        self.playlistModified.emit()

    def _onDoubleClick(self, item):
        self.requestPlay.emit(self.trackList.row(item))

    def _onNew(self):
        self._paths = []
        self._sourcePath = None
        self._rootDir = None
        self.nameEdit.setText("")
        self.trackList.clear()
        self.requestNew.emit()

    def _onAddFiles(self):
        result = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Add files", _getLastDir(),
            f"Media & Pictures ({_formatExts(MEDIA_EXTENSIONS | PICTURE_EXTENSIONS)});;All files (*)"
        )
        if result[0]:
            _setLastDir(result[0][0])
            self.addPaths(result[0])

    def _onDeleteSelected(self):
        row = self.trackList.currentRow()
        if row >= 0:
            self.trackList.takeItem(row)
            del self._paths[row]
            self.playlistModified.emit()

    def _onFilesDropped(self, paths):
        self.addPaths(paths)

    def _onSave(self):
        name = self.nameEdit.text().strip() or "playlist"
        initial = OSTools().joinPathes(_getLastDir(), name + ".m3u")
        result = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Playlist", initial,
            "M3U Playlist (*.m3u);;All files (*)"
        )
        if not result[0]:
            return
        path = result[0]
        self._sourcePath = path
        self.nameEdit.setText(OSTools().getPathWithoutExtension(OSTools().getFileNameOnly(path)))
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write('#EXTM3U\n')
                for p in self._paths:
                    f.write(p + '\n')
        except Exception:
            Log.exception("Saving playlist %s", path)
