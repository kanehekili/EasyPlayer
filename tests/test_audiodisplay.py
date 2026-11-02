"""What the player shows for audio: spectrum, cover, or neither.

The README lists the spectrum analyser as uncovered. These are the invariants
that broke in practice:

- capture failing must not leave a blank player. startCapture reports success
  so the caller can fall back to the cover instead of hiding the image and
  showing nothing (pip installs have numpy but no parec).
- pausing must not black out. stopCapture hides the overlay, so the pause path
  has to put the cover back.
- a still is never audio. isAudioOnly stays true from the previous track while
  a picture is displayed, which drew the spectrum over a photo.
- a missing pactl must be remembered, or every play press runs a blocking
  subprocess on the GUI thread.

The controllers are the real classes; only the player, mpv and the capture
stream are stubbed.
"""
import unittest
from unittest import mock
import support

support.initPlaylistModule()
app = support.app()

from PyQt6 import QtWidgets               # noqa: E402
import AudioPlay                          # noqa: E402
from AudioPlay import SpectrumController  # noqa: E402
from EasyPlayer import AudioDisplayController, MediaKind  # noqa: E402

FALLBACK = '/icons/CosmicRock.jpg'


class StubSpectrum:
    def __init__(self, canStart=True):
        self.canStart = canStart
        self.started = 0
        self.stopped = 0

    def startCapture(self):
        self.started += 1
        return self.canStart

    def stopCapture(self):
        self.stopped += 1


class StubPlayer:
    def __init__(self, kind=MediaKind.AUDIO, hasVideo=False, canStart=True):
        self.kind = kind
        self.isAudioOnly = kind is MediaKind.AUDIO
        self._hasVideo = hasVideo
        self.spectrumCtrl = StubSpectrum(canStart)
        self.shown = None
        self.hidden = 0

    def hasVideoTrack(self):
        return self._hasVideo

    def showImage(self, path):
        self.shown = path

    def hideImage(self):
        self.hidden += 1
        self.shown = None


class StubSettings:
    def __init__(self, eq):
        self.eq = eq

    def hasEQ(self):
        return self.eq


def controller(eq=True, **kw):
    p = StubPlayer(**kw)
    return p, AudioDisplayController(p, StubSettings(eq), FALLBACK)


class AudioDisplayTest(unittest.TestCase):

    def test_eqOnAndCaptureUp_showsSpectrumNotCover(self):
        p, ctrl = controller(eq=True)
        ctrl.update()
        self.assertEqual(p.spectrumCtrl.started, 1)
        self.assertIsNone(p.shown, "the overlay is the spectrum, not an image")
        self.assertEqual(p.hidden, 1)

    def test_eqOnButCaptureFails_fallsBackToCover(self):
        """the blank-player regression: the image was hidden before capture was
        known to work, so a missing parec left nothing on screen at all"""
        p, ctrl = controller(eq=True, canStart=False)
        ctrl.update()
        self.assertEqual(p.spectrumCtrl.started, 1)
        self.assertEqual(p.shown, FALLBACK)

    def test_eqOff_showsCover(self):
        p, ctrl = controller(eq=False)
        ctrl.update()
        self.assertEqual(p.spectrumCtrl.started, 0)
        self.assertEqual(p.shown, FALLBACK)

    def test_embeddedCoverIsLeftToMpv(self):
        """mpv already draws art when it has a video track - do not cover it"""
        p, ctrl = controller(eq=False, hasVideo=True)
        ctrl.update()
        self.assertIsNone(p.shown)

    def test_videoNeverStartsCapture(self):
        p, ctrl = controller(eq=True, kind=MediaKind.VIDEO)
        ctrl.update()
        self.assertEqual(p.spectrumCtrl.started, 0)
        self.assertEqual(p.spectrumCtrl.stopped, 1)
        self.assertIsNone(p.shown)

    def test_stillNeverStartsCapture(self):
        """isAudioOnly stayed true from the previous track while a picture was
        shown - the spectrum was drawn over the photo"""
        p, ctrl = controller(eq=True, kind=MediaKind.STILL)
        ctrl.update()
        self.assertEqual(p.spectrumCtrl.started, 0)
        self.assertIsNone(p.shown)

    def test_suspendStopsCaptureAndRestoresCover(self):
        """pausing with the EQ on used to black out the player"""
        p, ctrl = controller(eq=True)
        ctrl.update()
        ctrl.suspend()
        self.assertEqual(p.spectrumCtrl.stopped, 1)
        self.assertEqual(p.shown, FALLBACK)

    def test_suspendOnVideoShowsNoCover(self):
        p, ctrl = controller(eq=True, kind=MediaKind.VIDEO)
        ctrl.suspend()
        self.assertEqual(p.spectrumCtrl.stopped, 1)
        self.assertIsNone(p.shown)

    def test_updateIsIdempotent(self):
        """it runs on load and again on every play transition"""
        p, ctrl = controller(eq=True)
        ctrl.update()
        ctrl.update()
        self.assertEqual(p.spectrumCtrl.started, 2, "startCapture is a no-op when live")
        self.assertIsNone(p.shown)


class SpectrumCaptureTest(unittest.TestCase):
    """SpectrumController needs a QWidget parent for its overlay, nothing more"""

    def controller(self):
        return SpectrumController(QtWidgets.QWidget())

    def test_reportsFailureWhenNumpyMissing(self):
        ctrl = self.controller()
        with mock.patch.object(AudioPlay, 'HAS_SPECTRUM', False):
            self.assertFalse(ctrl.startCapture())

    def test_reportsFailureWhenNoMonitorDevice(self):
        ctrl = self.controller()
        with mock.patch.object(AudioPlay, 'HAS_SPECTRUM', True), \
             mock.patch.object(ctrl, '_findMonitorDevice', return_value=None):
            self.assertFalse(ctrl.startCapture())

    def test_reportsFailureWhenParecIsMissing(self):
        """pip can install numpy but never pulseaudio-utils"""
        ctrl = self.controller()
        with mock.patch.object(AudioPlay, 'HAS_SPECTRUM', True), \
             mock.patch.object(ctrl, '_findMonitorDevice', return_value='sink.monitor'), \
             mock.patch.object(AudioPlay, 'ParecStream', side_effect=FileNotFoundError('parec')):
            self.assertFalse(ctrl.startCapture())

    def test_monitorDeviceIsResolvedFromTheDefaultSink(self):
        ctrl = self.controller()
        result = mock.Mock(returncode=0, stdout="alsa_output.pci-0000_29_00.0.hdmi-stereo\n")
        with mock.patch('AudioPlay.subprocess.run', return_value=result) as run:
            self.assertEqual(ctrl._findMonitorDevice(),
                             "alsa_output.pci-0000_29_00.0.hdmi-stereo.monitor")
            self.assertEqual(run.call_count, 1)

    def test_aChangedDefaultSinkIsPickedUp(self):
        """the sink moves when a card is swapped - caching it for the process
        lifetime kept capturing from a device that no longer existed"""
        ctrl = self.controller()
        first = mock.Mock(returncode=0, stdout="sinkA\n")
        second = mock.Mock(returncode=0, stdout="sinkB\n")
        with mock.patch('AudioPlay.subprocess.run', side_effect=[first, second]):
            self.assertEqual(ctrl._findMonitorDevice(), "sinkA.monitor")
            self.assertEqual(ctrl._findMonitorDevice(), "sinkB.monitor")

    def test_missingPactlIsRememberedNotRetried(self):
        """every play press would otherwise run a blocking subprocess with a
        2 second timeout on the GUI thread"""
        ctrl = self.controller()
        with mock.patch('AudioPlay.subprocess.run', side_effect=OSError("no pactl")) as run:
            self.assertIsNone(ctrl._findMonitorDevice())
            self.assertIsNone(ctrl._findMonitorDevice())
            self.assertIsNone(ctrl._findMonitorDevice())
            self.assertEqual(run.call_count, 1, "the failure is cached")


if __name__ == '__main__':
    unittest.main()
