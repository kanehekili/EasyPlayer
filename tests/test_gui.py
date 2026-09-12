"""End to end smoke test: the real app, on a real X display.

Everything else in this suite runs offscreen against stubs. This one launches
src/EasyPlayer.py, looks at the pixels, and drives it with the keyboard - it is
the only check that the toolbar icons actually reach the screen and that
stepping through a folder updates the window title.

It opens a window for a few seconds. Skipped automatically when there is no
DISPLAY, or when xdotool / ImageMagick's import are missing. Set
EASYPLAYER_SKIP_GUI=1 to skip it deliberately.
"""
import os
import time
import tempfile
import unittest
import subprocess
import support

from PyQt6 import QtGui

TOOLBAR_HEIGHT = 34


@unittest.skipUnless(support.canDriveGui(),
                     'needs an X display plus xdotool and ImageMagick import')
class GuiSmokeTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        support.app()
        # the window search matches by title, so an already open EasyPlayer -
        # the user's own, or a zombie from an aborted run - would be picked up
        # and driven by the tests. Clear the stage first.
        # anchored so only a real app process matches - never a shell or IDE
        # whose command line merely mentions the script
        subprocess.run(['pkill', '-f', r'^python[^ ]* [^ ]*EasyPlayer\.py'],
                       capture_output=True)
        time.sleep(0.5)
        cls.shots = tempfile.mkdtemp(prefix='easyplayer-gui-')
        cls.opened = support.media('a.png')

    def shot(self, name):
        return os.path.join(self.shots, name + '.png')

    def toolbarStrip(self, path):
        image = QtGui.QImage(path)
        self.assertFalse(image.isNull(), 'screenshot did not load: ' + path)
        return image.copy(0, 0, image.width(), TOOLBAR_HEIGHT)

    def test_windowOpens(self):
        with support.AppWindow(self.opened) as window:
            self.assertTrue(window.title().startswith('EasyPlayer - '),
                            'unexpected title: ' + window.title())
            path = window.capture(self.shot('open'))
            image = QtGui.QImage(path)
            self.assertGreater(image.width(), 200, 'window far too small')
            self.assertGreater(image.height(), 200)

    def test_toolbarIconsAreDrawn(self):
        """a broken icomap entry renders an empty button - count the icons

        The toolbar chrome is grey, the icons are colourful, so counting runs of
        columns that contain saturated pixels counts the icons. Each icon that
        fails to load removes one run.
        """
        with support.AppWindow(self.opened) as window:
            shot = window.capture(self.shot('toolbar'))
            strip = self.toolbarStrip(shot)

        saturated = []
        for x in range(strip.width()):
            hit = False
            for y in range(2, strip.height() - 2):
                colour = strip.pixelColor(x, y)
                channels = (colour.red(), colour.green(), colour.blue())
                if max(channels) - min(channels) > 40:
                    hit = True
                    break
            saturated.append(hit)

        icons = 0
        previous = False
        for hit in saturated:
            if hit and not previous:
                icons += 1
            previous = hit

        self.assertGreaterEqual(
            icons, 6,
            'only %d coloured icons in the toolbar - one may have failed to '
            'load; look at %s' % (icons, shot))
        self.assertGreater(
            sum(saturated), 40,
            'toolbar is nearly monochrome - icons missing, see %s' % shot)

    def test_nextStepsThroughTheFolderAndRetitles(self):
        """opening one file queues its folder; ctrl+Right walks it in the
        known fixture order: a.png, b.png, movie.mkv"""
        with support.AppWindow(self.opened) as window:
            self.assertEqual(window.title(), 'EasyPlayer - a.png')
            self.assertTrue(
                window.keyExpectTitle('ctrl+Right', 'EasyPlayer - b.png'),
                'first step never reached b.png (title: %s)' % window.title())
            self.assertTrue(
                window.keyExpectTitle('ctrl+Right', 'EasyPlayer - movie.mkv'),
                'second step never reached movie.mkv (title: %s)' % window.title())
            window.capture(self.shot('third'))

    def test_prevReturnsToThePreviousFile(self):
        with support.AppWindow(self.opened) as window:
            self.assertTrue(
                window.keyExpectTitle('ctrl+Right', 'EasyPlayer - b.png'),
                'step to b.png failed (title: %s)' % window.title())
            self.assertTrue(
                window.keyExpectTitle('ctrl+Left', 'EasyPlayer - a.png'),
                'prev did not come back to a.png (title: %s)' % window.title())

    def test_noErrorsOnTheWayOut(self):
        with support.AppWindow(self.opened) as window:
            window.key('ctrl+Right')
        output = window.output()
        for marker in ('Traceback', 'Segmentation fault'):
            self.assertNotIn(marker, output, output[-2000:])


if __name__ == '__main__':
    unittest.main()
