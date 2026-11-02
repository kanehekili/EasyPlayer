"""What the slider and the info field show while a still is on screen.

A picture has no duration, so the field used to fake a clock by multiplying the
playlist index and the entry count by the slide interval. That read exactly like
a media time while meaning something else: opening the second picture of a
folder showed "00:00:02" before anything had happened, the total was the whole
folder at one interval each - videos included, which do not take a slide
interval at all - and the slider used (pos + 1) / count, so it could never sit
at zero.

It now counts slides, and the slider shows position. Audio and video are
untouched: their real time and duration are written by MainFrame._onSyncSlider,
which bails out while a slide is active.
"""
import unittest
import support

support.initPlaylistModule()
support.app()

from Slideshow import SlideshowController  # noqa: E402


class StubMpv:
    def __init__(self, count, pos):
        self.playlist = [{'filename': 'p%d.jpg' % i} for i in range(count)]
        self.playlist_pos = pos


class StubPlayer:
    def __init__(self, count, pos):
        self.mpv = StubMpv(count, pos)

    def showImage(self, path):
        pass

    def hideImage(self):
        pass


def progressAt(pos, count, slideSeconds=2):
    frame = support.StubFrame(support.StubSettings(slideSeconds))
    # StubFrame builds a bare QSlider (range 0..99); MainFrame sets 0..RESOLUTION
    frame.ui_Slider.setMinimum(0)
    frame.ui_Slider.setMaximum(frame.SLIDER_RESOLUTION)
    ctrl = SlideshowController(StubPlayer(count, pos), frame)
    ctrl._updateSlideProgress()
    return frame.ui_InfoLabel.text(), frame.ui_Slider.sliderPosition(), frame.SLIDER_RESOLUTION


class SlideProgressTest(unittest.TestCase):

    def test_labelCountsSlidesNotSeconds(self):
        text, _, _ = progressAt(pos=1, count=161)
        self.assertEqual(text, "2 / 161")

    def test_firstSlideIsOneOfN(self):
        text, _, _ = progressAt(pos=0, count=161)
        self.assertEqual(text, "1 / 161")

    def test_labelIsNotAClock(self):
        """the regression: '00:00:02  u25C6  00:05:22' for slide 2 of 161"""
        text, _, _ = progressAt(pos=1, count=161)
        self.assertNotIn(':', text)
        self.assertNotIn('◆', text)

    def test_labelIgnoresTheSlideInterval(self):
        """the total used to change when the interval setting changed"""
        a, _, _ = progressAt(pos=3, count=20, slideSeconds=2)
        b, _, _ = progressAt(pos=3, count=20, slideSeconds=30)
        self.assertEqual(a, b)

    def test_sliderStartsAtZero(self):
        _, slider, _ = progressAt(pos=0, count=161)
        self.assertEqual(slider, 0, "(pos + 1) / count could never reach zero")

    def test_sliderEndsAtFull(self):
        _, slider, resolution = progressAt(pos=160, count=161)
        self.assertEqual(slider, resolution)

    def test_sliderIsProportionalToPosition(self):
        _, slider, resolution = progressAt(pos=5, count=11)
        self.assertEqual(slider, resolution // 2)

    def test_singleItemDoesNotDivideByZero(self):
        text, slider, _ = progressAt(pos=0, count=1)
        self.assertEqual(text, "1 / 1")
        self.assertEqual(slider, 0)

    def test_noPlaylistLeavesEverythingAlone(self):
        frame = support.StubFrame(support.StubSettings(2))
        frame.ui_InfoLabel.setText("untouched")
        ctrl = SlideshowController(StubPlayer(0, 0), frame)
        ctrl._updateSlideProgress()
        self.assertEqual(frame.ui_InfoLabel.text(), "untouched")


if __name__ == '__main__':
    unittest.main()
