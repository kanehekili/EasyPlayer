"""Ctrl+wheel zoom and drag-pan.

The geometry model is mpv's: the source is fitted into the window, scaled by
`factor`, then shifted by `pan * scaledSize`. ImageOverlay copies that model so
stills and video behave identically - the helpers below recompute it
independently and compare.
"""
import math
import unittest
import support

from PyQt6 import QtGui, QtCore, QtWidgets
from EasyPlayer import ZoomController, ZOOM_MAX, Player
from Slideshow import ImageOverlay


class FakeMpv:
    def __init__(self, dw, dh):
        self.dwidth, self.dheight = dw, dh
        self.video_zoom = 0.0
        self.video_pan_x = 0.0
        self.video_pan_y = 0.0


class FakeOverlay:
    def __init__(self):
        self.visible = False
        self.size = (None, None)
        self.transform = None

    def isVisible(self): return self.visible
    def imageSize(self): return self.size
    def setTransform(self, f, px, py): self.transform = (f, px, py)


class ZoomRig(QtWidgets.QWidget):
    """the slice of Player that ZoomController touches, with the real cursor slot"""
    zoomChanged = QtCore.pyqtSignal(bool)
    _onZoomChanged = Player._onZoomChanged

    def __init__(self, w, h, dw, dh):
        super().__init__()
        self.resize(w, h)
        self.mpv = FakeMpv(dw, dh)
        self._imageOverlay = FakeOverlay()
        self._dragPos = None
        self.zoomCtrl = ZoomController(self)
        self.zoomChanged.connect(self._onZoomChanged)

    def cursorName(self):
        return self.cursor().shape().name

    def placement(self, axis):
        """where the source lands on screen, recomputed from mpv's own formula"""
        zoom = self.zoomCtrl
        if self._imageOverlay.isVisible():
            srcW, srcH = self._imageOverlay.imageSize()
        else:
            srcW, srcH = self.mpv.dwidth, self.mpv.dheight
        fit = min(self.width() / srcW, self.height() / srcH)
        if axis == 'x':
            win, size, pan = self.width(), srcW * fit * zoom.factor, zoom.panX
        else:
            win, size, pan = self.height(), srcH * fit * zoom.factor, zoom.panY
        start = (win - size) / 2 + pan * size
        return start, size

    def relativeAt(self, pos, axis):
        """which point of the source sits under a screen coordinate, 0..1"""
        start, size = self.placement(axis)
        return (pos - start) / size


class ZoomMathTest(unittest.TestCase):

    def setUp(self):
        support.app()

    def test_pointerStaysOnTheSamePoint(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        mx, my = 400.0, 200.0
        before = (rig.relativeAt(mx, 'x'), rig.relativeAt(my, 'y'))
        for _ in range(6):
            rig.zoomCtrl.zoomAt(1, mx, my)
        after = (rig.relativeAt(mx, 'x'), rig.relativeAt(my, 'y'))
        self.assertAlmostEqual(before[0], after[0], places=6)
        self.assertAlmostEqual(before[1], after[1], places=6)
        self.assertGreater(rig.zoomCtrl.factor, 1.0)

    def test_noBlackBarsWhileZoomed(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        for _ in range(6):
            rig.zoomCtrl.zoomAt(1, 400.0, 200.0)
        for axis, window in (('x', 1600), ('y', 900)):
            start, size = rig.placement(axis)
            self.assertLessEqual(start, 1e-9, axis + ' leading edge')
            self.assertGreaterEqual(start + size, window - 1e-9, axis + ' trailing edge')

    def test_zoomOutReturnsToIdentity(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        for _ in range(6):
            rig.zoomCtrl.zoomAt(1, 400.0, 200.0)
        for _ in range(30):
            rig.zoomCtrl.zoomAt(-1, 400.0, 200.0)
        self.assertEqual(rig.zoomCtrl.factor, 1.0)
        self.assertAlmostEqual(rig.zoomCtrl.panX, 0.0, places=9)
        self.assertAlmostEqual(rig.zoomCtrl.panY, 0.0, places=9)

    def test_neverBelowHundredPercent(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        for _ in range(50):
            rig.zoomCtrl.zoomAt(-1, 800.0, 450.0)
        self.assertEqual(rig.zoomCtrl.factor, 1.0)

    def test_cappedAtMaximum(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        for _ in range(200):
            rig.zoomCtrl.zoomAt(1, 800.0, 450.0)
        self.assertEqual(rig.zoomCtrl.factor, ZOOM_MAX)
        self.assertAlmostEqual(rig.mpv.video_zoom, math.log2(ZOOM_MAX), places=9)

    def test_letterboxedAxisStaysCentred(self):
        """16:9 source in a 4:3 window - the short axis must not pan while it fits"""
        rig = ZoomRig(1200, 900, 1920, 1080)
        rig.zoomCtrl.zoomAt(3, 100.0, 500.0)
        start, size = rig.placement('y')
        self.assertLess(size, 900, 'precondition: still letterboxed')
        self.assertAlmostEqual(rig.zoomCtrl.panY, 0.0, places=9)

    def test_cornerCursorClampsToEdge(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        rig.zoomCtrl.zoomAt(20, 0.0, 0.0)
        self.assertAlmostEqual(rig.placement('x')[0], 0.0, places=6)
        self.assertAlmostEqual(rig.placement('y')[0], 0.0, places=6)

    def test_noVideoIsNotZoomable(self):
        rig = ZoomRig(1600, 900, None, None)
        self.assertFalse(rig.zoomCtrl.isZoomable())
        rig.zoomCtrl.zoomAt(1, 10.0, 10.0)
        self.assertEqual(rig.zoomCtrl.factor, 1.0)

    def test_visibleImageIsZoomable(self):
        rig = ZoomRig(1600, 900, None, None)
        rig._imageOverlay.visible = True
        rig._imageOverlay.size = (4000, 3000)
        self.assertTrue(rig.zoomCtrl.isZoomable())


class DragPanTest(unittest.TestCase):

    def setUp(self):
        support.app()

    def test_dragMovesTheImageOneToOne(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        rig.zoomCtrl.zoomAt(8, 800.0, 450.0)
        before = rig.placement('x')[0]
        rig.zoomCtrl.panBy(37.0, 0.0)
        self.assertAlmostEqual(rig.placement('x')[0] - before, 37.0, places=6)

    def test_dragClampsAtEveryEdge(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        rig.zoomCtrl.zoomAt(8, 800.0, 450.0)
        for _ in range(200):
            rig.zoomCtrl.panBy(50.0, 50.0)
        self.assertLessEqual(rig.placement('x')[0], 1e-9)
        self.assertLessEqual(rig.placement('y')[0], 1e-9)
        for _ in range(400):
            rig.zoomCtrl.panBy(-50.0, -50.0)
        startX, sizeX = rig.placement('x')
        startY, sizeY = rig.placement('y')
        self.assertGreaterEqual(startX + sizeX, 1600 - 1e-9)
        self.assertGreaterEqual(startY + sizeY, 900 - 1e-9)

    def test_dragOnlyWhileZoomed(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        self.assertFalse(rig.zoomCtrl.isActive())
        rig.zoomCtrl.zoomAt(1, 10.0, 10.0)
        self.assertTrue(rig.zoomCtrl.isActive())


class CursorTest(unittest.TestCase):
    """open hand while zoomed, closed hand while dragging, arrow at 100%"""

    def setUp(self):
        support.app()
        self.rig = ZoomRig(1600, 900, 1920, 1080)

    def test_arrowUntilZoomed(self):
        self.assertEqual(self.rig.cursorName(), 'ArrowCursor')
        self.rig.zoomCtrl.zoomAt(3, 800.0, 450.0)
        self.assertEqual(self.rig.cursorName(), 'OpenHandCursor')

    def test_dragKeepsTheClosedHand(self):
        self.rig.zoomCtrl.zoomAt(3, 800.0, 450.0)
        self.rig._dragPos = QtCore.QPointF(800.0, 450.0)
        self.rig.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
        self.rig.zoomCtrl.panBy(20.0, 10.0)          # fires _apply mid-drag
        self.assertEqual(self.rig.cursorName(), 'ClosedHandCursor')
        self.rig._dragPos = None
        self.rig._onZoomChanged(self.rig.zoomCtrl.isActive())
        self.assertEqual(self.rig.cursorName(), 'OpenHandCursor')

    def test_staleEventDuringDragIsIgnored(self):
        self.rig.zoomCtrl.zoomAt(3, 800.0, 450.0)
        self.rig._dragPos = QtCore.QPointF(1.0, 1.0)
        self.rig.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
        self.rig.zoomChanged.emit(False)             # e.g. a queued reset
        support.spin(10)
        self.assertEqual(self.rig.cursorName(), 'ClosedHandCursor')

    def test_backToArrowAtHundredPercent(self):
        self.rig.zoomCtrl.zoomAt(3, 800.0, 450.0)
        for _ in range(30):
            self.rig.zoomCtrl.zoomAt(-1, 800.0, 450.0)
        self.assertEqual(self.rig.cursorName(), 'ArrowCursor')

    def test_resetLeavesMpvClean(self):
        self.rig.zoomCtrl.zoomAt(10, 100.0, 100.0)
        self.rig.zoomCtrl.reset()
        self.assertEqual(self.rig.zoomCtrl.factor, 1.0)
        self.assertEqual(self.rig.mpv.video_zoom, 0.0)
        self.assertEqual(self.rig.mpv.video_pan_x, 0.0)
        self.assertEqual(self.rig.mpv.video_pan_y, 0.0)


class OverlayRoutingTest(unittest.TestCase):
    """a visible still is zoomed by the overlay, mpv must be left alone"""

    def setUp(self):
        support.app()

    def test_stillGoesToTheOverlay(self):
        rig = ZoomRig(1600, 900, 1920, 1080)
        rig._imageOverlay.visible = True
        rig._imageOverlay.size = (4000, 3000)
        self.assertEqual(rig.zoomCtrl._sourceSize(), (4000, 3000))
        rig.zoomCtrl.zoomAt(5, 400.0, 200.0)
        self.assertIsNotNone(rig._imageOverlay.transform)
        self.assertEqual(rig.mpv.video_zoom, 0.0, 'mpv must not be touched')
        self.assertEqual(rig.mpv.video_pan_x, 0.0)


class ImageOverlayRenderTest(unittest.TestCase):
    """paint the overlay offscreen and read the pixels back"""

    W, H = 800, 400
    SRC_W, SRC_H = 400, 300

    def setUp(self):
        support.app()
        self.pixmap = QtGui.QPixmap(self.SRC_W, self.SRC_H)
        painter = QtGui.QPainter(self.pixmap)
        painter.fillRect(0, 0, 200, 150, QtGui.QColor(255, 0, 0))        # TL
        painter.fillRect(200, 0, 200, 150, QtGui.QColor(0, 255, 0))      # TR
        painter.fillRect(0, 150, 200, 150, QtGui.QColor(0, 0, 255))      # BL
        painter.fillRect(200, 150, 200, 150, QtGui.QColor(255, 255, 0))  # BR
        painter.end()
        self.overlay = ImageOverlay(None)
        self.overlay.resize(self.W, self.H)
        self.overlay._pixmap = self.pixmap
        self.overlay.resetTransform()

    def render(self):
        image = QtGui.QImage(self.W, self.H, QtGui.QImage.Format.Format_RGB32)
        self.overlay.render(image)
        return image

    def quadrant(self, image, x, y):
        colour = image.pixelColor(int(x), int(y))
        rgb = (colour.red(), colour.green(), colour.blue())
        names = {'red': (255, 0, 0), 'green': (0, 255, 0), 'blue': (0, 0, 255),
                 'yellow': (255, 255, 0), 'black': (0, 0, 0)}
        for name, ref in names.items():
            if max(abs(a - b) for a, b in zip(rgb, ref)) < 40:
                return name
        return rgb

    def test_identityIsCentredAndLetterboxed(self):
        image = self.render()
        fit = min(self.W / self.SRC_W, self.H / self.SRC_H)
        iw = self.SRC_W * fit
        x0 = (self.W - iw) / 2
        self.assertEqual(self.quadrant(image, 20, self.H / 2), 'black', 'left bar')
        self.assertEqual(self.quadrant(image, self.W - 20, self.H / 2), 'black', 'right bar')
        self.assertEqual(self.quadrant(image, x0 + iw * 0.25, self.H * 0.25), 'red')
        self.assertEqual(self.quadrant(image, x0 + iw * 0.75, self.H * 0.25), 'green')
        self.assertEqual(self.quadrant(image, x0 + iw * 0.25, self.H * 0.75), 'blue')
        self.assertEqual(self.quadrant(image, x0 + iw * 0.75, self.H * 0.75), 'yellow')

    def test_zoomFillsTheBars(self):
        self.overlay.setTransform(2.0, 0.0, 0.0)
        image = self.render()
        self.assertNotEqual(self.quadrant(image, 5, self.H / 2), 'black')
        self.assertNotEqual(self.quadrant(image, self.W - 5, self.H / 2), 'black')

    def test_panShowsTheRequestedCorner(self):
        fit = min(self.W / self.SRC_W, self.H / self.SRC_H)
        iw, ih = self.SRC_W * fit * 2, self.SRC_H * fit * 2
        limX = max(0.0, (iw - self.W) / (2 * iw))
        limY = max(0.0, (ih - self.H) / (2 * ih))

        self.overlay.setTransform(2.0, limX, limY)      # push right/down -> show top-left
        image = self.render()
        corners = [self.quadrant(image, 5, 5), self.quadrant(image, self.W - 5, 5),
                   self.quadrant(image, 5, self.H - 5), self.quadrant(image, self.W - 5, self.H - 5)]
        self.assertNotIn('black', corners, 'no bars when panned to the limit')
        self.assertNotIn('blue', corners, 'bottom half must be off screen')
        self.assertNotIn('yellow', corners)

        self.overlay.setTransform(2.0, -limX, -limY)    # show bottom-right
        image = self.render()
        corners = [self.quadrant(image, 5, 5), self.quadrant(image, self.W - 5, 5),
                   self.quadrant(image, 5, self.H - 5), self.quadrant(image, self.W - 5, self.H - 5)]
        self.assertNotIn('red', corners, 'top half must be off screen')
        self.assertNotIn('green', corners)

    def test_deepZoomDoesNotScaleTheWholePixmap(self):
        """a full pre-scale of this would be 48000x32000 px - must stay quick"""
        import time
        big = QtGui.QPixmap(6000, 4000)
        big.fill(QtGui.QColor(10, 200, 90))
        self.overlay._pixmap = big
        self.overlay.setTransform(8.0, 0.0, 0.0)
        started = time.time()
        image = self.render()
        self.assertLess(time.time() - started, 1.0)
        self.assertEqual(self.quadrant(image, self.W / 2, self.H / 2), (10, 200, 90))

    def test_emptyOverlayPaintsBlack(self):
        self.overlay.clearImage()
        image = self.render()
        self.assertEqual(self.quadrant(image, self.W / 2, self.H / 2), 'black')


if __name__ == '__main__':
    unittest.main()
