from PyQt6 import QtWidgets, QtCore, QtGui
from FFMPEGTools import OSTools

PICTURE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif'}


class ImageOverlay(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._pixmap = None

    def setImage(self, path):
        self._pixmap = QtGui.QPixmap(path)
        self.update()

    def clearImage(self):
        self._pixmap = None
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtCore.Qt.GlobalColor.black)
        if self._pixmap and not self._pixmap.isNull():
            scaled = self._pixmap.scaled(
                self.size(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        painter.end()


class SlideshowController(QtCore.QObject):
    def __init__(self, player, mainframe):
        super().__init__()
        self._player = player
        self._ui_Slider = mainframe.ui_Slider
        self._ui_InfoLabel = mainframe.ui_InfoLabel
        self._settings = mainframe.settings
        self._SLIDER_RESOLUTION = mainframe.SLIDER_RESOLUTION
        self._active = False
        self._slideTimer = QtCore.QTimer(self)
        self._slideTimer.setSingleShot(True)
        self._slideTimer.timeout.connect(self._onSlideTimeout)

    def isActive(self):
        return self._active

    def isOverlayVisible(self):
        return self._player._imageOverlay.isVisible()

    def onTrackChanged(self, path):
        """Returns True if handled as a slide, False if caller should handle it."""
        ext = OSTools().getExtension(path).lower()
        if ext in PICTURE_EXTENSIONS:
            self._active = True
            self._slideTimer.stop()
            self._player.mpv.pause = True
            self._player.showImage(path)
            self._slideTimer.start(self._settings.getSlideDuration() * 1000)
            QtCore.QTimer.singleShot(50, self._updateSlideProgress)
            return True
        self._active = False
        self._player.hideImage()
        self._slideTimer.stop()
        return False

    def onSlideDurationChanged(self, seconds):
        if self._slideTimer.isActive():
            self._slideTimer.setInterval(seconds * 1000)

    def togglePlay(self):
        if self._slideTimer.isActive():
            self._slideTimer.stop()
            self._player.syncPlayStatus.emit(False)
        else:
            self._slideTimer.start(self._settings.getSlideDuration() * 1000)
            self._player.syncPlayStatus.emit(True)

    def _onSlideTimeout(self):
        pos = self._player.mpv.playlist_pos
        count = len(self._player.mpv.playlist)
        if pos is not None and pos < count - 1:
            self._player.hideImage()
            self._player.mpv.pause = False
            self._player.nextTrack()
        else:
            self._active = False
            self._player.syncPlayStatus.emit(False)

    def _updateSlideProgress(self):
        pos = self._player.mpv.playlist_pos or 0
        count = len(self._player.mpv.playlist)
        dur = self._settings.getSlideDuration()
        if count > 0:
            sliderPos = int(self._SLIDER_RESOLUTION * (pos + 1) / count)
            self._ui_Slider.blockSignals(True)
            self._ui_Slider.setSliderPosition(sliderPos)
            self._ui_Slider.blockSignals(False)

        def fmt(s):
            s = int(s)
            return '{:02}:{:02}:{:02}'.format(s // 3600, s % 3600 // 60, s % 60)
        self._ui_InfoLabel.setText(fmt(pos * dur) + "  \u25C6  " + fmt(count * dur))
