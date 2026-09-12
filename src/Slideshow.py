from PyQt6 import QtWidgets, QtCore, QtGui
import FFMPEGTools
from FFMPEGTools import OSTools, FFmpegPicture

Log = FFMPEGTools.Log

#.avif/.heic/.heif usually have no Qt plugin - ImageOverlay falls back to ffmpeg
PICTURE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.tiff', '.tif',
                      '.avif', '.heic', '.heif'}


class ImageOverlay(QtWidgets.QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._pixmap = None
        self._factor = 1.0
        self._panX = 0.0
        self._panY = 0.0

    def setImage(self, path):
        self._pixmap = self._load(path)
        self.resetTransform()

    def _load(self, path):
        """Qt first; anything it has no plugin for goes through ffmpeg"""
        pixmap = QtGui.QPixmap(path)
        if not pixmap.isNull():
            return pixmap
        raw = FFmpegPicture.decodeStill(path)
        if not raw:
            Log.info("no decoder for %s", path)
            return pixmap
        decoded = QtGui.QPixmap()
        decoded.loadFromData(raw, "PNG")
        return decoded

    def clearImage(self):
        self._pixmap = None
        self.resetTransform()

    def resetTransform(self):
        self.setTransform(1.0, 0.0, 0.0)

    def setTransform(self, factor, panX, panY):
        """same geometry model as mpv: fit, scaled by factor, shifted by pan*scaled"""
        self._factor = factor
        self._panX = panX
        self._panY = panY
        self.update()

    def imageSize(self):
        if self._pixmap and not self._pixmap.isNull():
            return self._pixmap.width(), self._pixmap.height()
        return None, None

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtCore.Qt.GlobalColor.black)
        srcW, srcH = self.imageSize()
        w, h = self.width(), self.height()
        if srcW and w > 0 and h > 0:
            painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, True)
            fit = min(w / srcW, h / srcH)
            sizeX, sizeY = srcW * fit * self._factor, srcH * fit * self._factor
            startX = (w - sizeX) / 2 + self._panX * sizeX
            startY = (h - sizeY) / 2 + self._panY * sizeY
            u0, u1 = self._visibleRange(startX, sizeX, w)
            v0, v1 = self._visibleRange(startY, sizeY, h)
            src = QtCore.QRectF(u0 * srcW, v0 * srcH, (u1 - u0) * srcW, (v1 - v0) * srcH)
            dst = QtCore.QRectF(startX + u0 * sizeX, startY + v0 * sizeY,
                                (u1 - u0) * sizeX, (v1 - v0) * sizeY)
            painter.drawPixmap(dst, self._pixmap, src)
        painter.end()

    def _visibleRange(self, start, size, winSize):
        """source fraction that lands inside the widget - keeps a deep zoom
        from scaling the whole pixmap"""
        lo = max(0.0, min(1.0, -start / size))
        hi = max(0.0, min(1.0, (winSize - start) / size))
        return lo, hi


class SlideshowController(QtCore.QObject):
    """Shows stills and times them. It owns no play/pause state - PlaybackController
    starts and stops it, and is told when a slide has run its course."""
    slideEnded = QtCore.pyqtSignal()

    def __init__(self, player, mainframe):
        super().__init__()
        self._player = player
        self._ui_Slider = mainframe.ui_Slider
        self._ui_InfoLabel = mainframe.ui_InfoLabel
        self._settings = mainframe.settings
        self._SLIDER_RESOLUTION = mainframe.SLIDER_RESOLUTION
        self._active = False
        self._currentPath = None
        self._slideTimer = QtCore.QTimer(self)
        self._slideTimer.setSingleShot(True)
        self._slideTimer.timeout.connect(self._onSlideTimeout)

    def isActive(self):
        return self._active

    def isShowingStill(self):
        return self._active

    def isOverlayVisible(self):
        return self._player._imageOverlay.isVisible()

    def isPicture(self, path):
        return OSTools().getExtension(path).lower() in PICTURE_EXTENSIONS

    def setRunning(self, running):
        """arm or disarm the slide timer - the only transport control this class has"""
        if not running:
            self._slideTimer.stop()
            return
        if self._active:
            self._slideTimer.start(self._settings.getSlideDuration() * 1000)

    def onTrackChanged(self, path):
        """Returns True if handled as a slide, False if caller should handle it."""
        if self.isPicture(path):
            if self._active and path == self._currentPath:
                return True
            self._currentPath = path
            self._active = True
            self._slideTimer.stop()
            self._player.showImage(path)
            QtCore.QTimer.singleShot(50, self._updateSlideProgress)
            return True
        self._active = False
        self._currentPath = None
        self._player.hideImage()
        self._slideTimer.stop()
        return False

    def onSlideDurationChanged(self, seconds):
        if self._slideTimer.isActive():
            self._slideTimer.setInterval(seconds * 1000)

    def _onSlideTimeout(self):
        self.slideEnded.emit()

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
