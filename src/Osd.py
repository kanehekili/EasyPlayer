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

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import pyqtSlot
import FFMPEGTools

Log = FFMPEGTools.Log

HIDE_DELAY_MS = 3000
ICON_SIZE = 32

_icomap = None


def init(icomap):
    global _icomap
    _icomap = icomap


def _section():
    """the bar is dark: flat(light) icons vanish on it, so any flat theme
    takes its OSD icons from flat(dark)"""
    return "flat(dark)" if _icomap.section.startswith("flat") else _icomap.section


def _icon(key):
    return QtGui.QIcon(_icomap.ico(key, _section()))


class OsdOverlay(QtWidgets.QWidget):
    """Control bar at the bottom of the player while fullscreen.

    A plain child widget - never drawn on the GL surface (see SpectrumOverlay).
    The background is opaque on purpose: alpha over the mpv FBO does not blend.
    """

    mouseActive = QtCore.pyqtSignal()  # movement over the bar - its children eat it otherwise

    # positional, matching the action tuple MainFrame hands over
    BUTTON_KEYS = ("prev", "playStart", "stopAction", "next")

    def __init__(self, player, actions):
        super().__init__(player)
        self._player = player
        self._borrowed = []
        self._keys = {}
        self._playBtn = None
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(self._style())
        self._box = QtWidgets.QVBoxLayout(self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(0)
        self._box.addWidget(self._makeButtonRow(actions))
        self._trackMoves()
        player.installEventFilter(self)

    def _style(self):
        color = self.palette().color(QtGui.QPalette.ColorRole.Window)
        bc = color.darker(120)
        darker = color.darker(150)
        lighter = color.lighter(140)
        return ("OsdOverlay { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
                " stop:0 %s, stop:1.0 %s); border: 1px solid %s; }"
                % (darker.name(), lighter.name(), bc.name()))

    def _makeButtonRow(self, actions):
        row = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(row)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)
        lay.addStretch()
        for action, key in zip(actions, self.BUTTON_KEYS):
            btn = QtWidgets.QToolButton()
            btn.setDefaultAction(action)  # tooltip and enabled state follow
            btn.setAutoRaise(True)
            btn.setIconSize(QtCore.QSize(ICON_SIZE, ICON_SIZE))
            self._keys[btn] = key
            # a default action re-syncs the button's icon whenever the action
            # changes - put the OSD's own icon back afterwards
            action.changed.connect(lambda b=btn: b.setIcon(_icon(self._keys[b])))
            btn.setIcon(_icon(key))
            if key == "playStart":
                self._playBtn = btn
            lay.addWidget(btn)
        lay.addStretch()
        return row

    def setPlaying(self, isPlaying):
        """the play button is the one icon that changes while the bar lives"""
        if self._playBtn is None:
            return
        self._keys[self._playBtn] = "playPause" if isPlaying else "playStart"
        self._playBtn.setIcon(_icon(self._keys[self._playBtn]))

    def borrow(self, widget):
        """info row / slider live in here while fullscreen"""
        self._borrowed.append(widget)
        self._box.insertWidget(self._box.count() - 1, widget)
        widget.show()
        self._trackMoves()
        self._reposition()

    def giveBack(self):
        """hand the borrowed widgets back in the order they were taken"""
        taken = self._borrowed
        self._borrowed = []
        for widget in taken:
            self._box.removeWidget(widget)
        return taken

    def _trackMoves(self):
        """the player never sees moves over the bar - its children consume them"""
        self.setMouseTracking(True)
        for child in self.findChildren(QtWidgets.QWidget):
            child.setMouseTracking(True)
            child.installEventFilter(self)

    def mouseMoveEvent(self, event):
        self.mouseActive.emit()
        super().mouseMoveEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Type.MouseMove:
            self.mouseActive.emit()
        elif obj is self._player and event.type() == QtCore.QEvent.Type.Resize:
            self._reposition()
        return False

    def showEvent(self, event):
        self._reposition()
        super().showEvent(event)

    def _reposition(self):
        height = self.sizeHint().height()
        self.setGeometry(0, self._player.height() - height, self._player.width(), height)


class OsdController(QtCore.QObject):
    """Visible while the mouse moves, gone after HIDE_DELAY_MS without movement.

    Owns the bar's visibility and the mouse cursor in fullscreen, nothing else -
    the buttons are MainFrame's actions, the slider is MainFrame's slider.
    """

    def __init__(self, player, actions):
        super().__init__(player)
        self._player = player
        self._overlay = OsdOverlay(player, actions)
        self._overlay.hide()
        self._overlay.mouseActive.connect(self.wake)
        self._enabled = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(HIDE_DELAY_MS)
        self._timer.timeout.connect(self._onTimeout)

    def enable(self):
        self._enabled = True
        self.wake()

    def disable(self):
        self._enabled = False
        self._timer.stop()
        self._overlay.hide()

    def setPlaying(self, isPlaying):
        self._overlay.setPlaying(isPlaying)

    def takeWidgets(self, *widgets):
        for widget in widgets:
            self._overlay.borrow(widget)

    def releaseWidgets(self):
        return self._overlay.giveBack()

    @pyqtSlot()
    def wake(self):
        if not self._enabled:
            return
        if not self._overlay.isVisible():
            self._overlay.show()
            self._overlay.raise_()  # above the image and spectrum overlays
            self._player.restoreCursor()
        self._timer.start()

    def raiseToTop(self):
        """something was raised over the video - the bar has to stay on top of it"""
        if self._overlay.isVisible():
            self._overlay.raise_()

    def _onTimeout(self):
        if not self._enabled:
            return
        if QtWidgets.QApplication.mouseButtons() != QtCore.Qt.MouseButton.NoButton: # @UndefinedVariable
            self._timer.start()  # a button is held - do not pull the bar out of a drag
            return
        self._overlay.hide()
        self._player.setCursor(QtCore.Qt.CursorShape.BlankCursor)
