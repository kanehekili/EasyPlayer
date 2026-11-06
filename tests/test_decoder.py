"""Item classification and the per-GPU decoder choice.

MediaKind answers "what is this item" from the filename alone, so it cannot go
stale the way isAudioOnly does - pictures are never probed, and the old flag
kept whatever the last audio file said. hasVideoTrack exists because mpv.vid
reads the string 'auto' until a track is resolved, which is truthy and silently
suppressed the audio cover right after a track change.

The decoder choice is Intel-only: inside the GL FBO vaapi-copy is the one
hardware path that engages, and it costs over a second on a single large still
because the overlay cannot paint until mpv is done with the same file. Stills
therefore decode in software - identical pixels - while video keeps the
hardware path.

Methods are called unbound against small stubs: a real Player builds an mpv
instance and a GL context, neither of which this logic needs.
"""
import unittest
from unittest import mock
import support

support.initPlaylistModule()

from FFMPEGTools import GPUTools       # noqa: E402
import EasyPlayer                      # noqa: E402
from EasyPlayer import MediaKind       # noqa: E402


class Stub:
    """attribute bag - stands in for Player or mpv"""
    pass


def player(vid=False, videoParams=None, intel=True, probed=None, audioOnly=False,
           hwdec='vaapi-copy,no'):
    p = Stub()
    p.mpv = Stub()
    p.mpv.vid = vid
    p.mpv.video_params = videoParams
    p.mpv.hwdec = hwdec.split(',')
    p._gpuHwdec = hwdec   # GPUTools decided this once, before mpv was built
    p.isIntelGpu = intel
    p.kind = MediaKind.NONE
    p._probedPath = probed
    p.isAudioOnly = audioOnly
    return p


class MediaKindTest(unittest.TestCase):

    def test_picturesAreStillFromTheExtensionAlone(self):
        for name in ('a.jpg', 'A.JPG', '/tmp/x/b.png', 'c.jpeg', 'd.webp', 'e.tif'):
            self.assertIs(MediaKind.of(name), MediaKind.STILL, name)

    def test_nonPicturesDefaultToVideoNotAudio(self):
        """conservative: the audio-only behaviours all gate on AUDIO, so a
        not-yet-probed item must not look like audio"""
        for name in ('a.mp4', 'b.mkv', 'c.mp3', 'd.flac'):
            self.assertIs(MediaKind.of(name), MediaKind.VIDEO, name)

    def test_emptyPathIsNone(self):
        self.assertIs(MediaKind.of(''), MediaKind.NONE)
        self.assertIs(MediaKind.of(None), MediaKind.NONE)

    def test_stillAndAudioAreMutuallyExclusive(self):
        """the compound 'isAudioOnly and not isShowingStill' existed because the
        two old sources could both be true at once - these cannot"""
        self.assertIsNot(MediaKind.of('a.jpg'), MediaKind.AUDIO)


class HasVideoTrackTest(unittest.TestCase):
    """mpv.vid is a list-ish option, not a boolean"""

    def check(self, vid, params):
        p = player(vid=vid, videoParams=params)
        return EasyPlayer.Player.hasVideoTrack(p)

    def test_explicitNoVideo(self):
        for vid in (False, None, 'no'):
            self.assertFalse(self.check(vid, None), vid)

    def test_autoWithoutResolvedParamsIsNotVideo(self):
        """the regression: 'auto' is truthy, so `not mpv.vid` was False and the
        audio cover never appeared right after a track change"""
        self.assertFalse(self.check('auto', None))
        self.assertFalse(self.check('auto', {}))

    def test_autoWithResolvedParamsIsVideo(self):
        self.assertTrue(self.check('auto', {'w': 1920, 'h': 1080}))

    def test_explicitTrackId(self):
        self.assertTrue(self.check(1, None))
        self.assertTrue(self.check(2, {'w': 1}))


class IntelGpuDetectionTest(unittest.TestCase):
    """lspci mentions Intel all over an Intel board - only the display
    controller line may count, or every Intel-CPU machine matches"""

    def detect(self, lspciOutput):
        result = mock.Mock(stdout=lspciOutput, returncode=0)
        with mock.patch('FFMPEGTools.subprocess.run', return_value=result):
            return GPUTools.is_intel_gpu_active()

    def test_discreteArc(self):
        self.assertTrue(self.detect(
            "00:1f.3 Audio device: Intel Corporation Alder Lake\n"
            "28:00.0 VGA compatible controller: Intel Corporation DG2 [Arc A380] (rev 05)"))

    def test_integratedIntel(self):
        self.assertTrue(self.detect(
            "00:02.0 VGA compatible controller: Intel Corporation TigerLake-LP GT2 [Iris Xe Graphics]"))

    def test_amdCardInIntelBox(self):
        self.assertFalse(self.detect(
            "00:1f.3 Audio device: Intel Corporation Alder Lake\n"
            "00:14.3 Network controller: Intel Corporation Wi-Fi 6 AX200\n"
            "03:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Navi 23"))

    def test_nvidiaCardInIntelBox(self):
        self.assertFalse(self.detect(
            "00:1f.3 Audio device: Intel Corporation Alder Lake\n"
            "01:00.0 VGA compatible controller: NVIDIA Corporation GA106 [RTX 3060]"))

    def test_noIntelAtAll(self):
        self.assertFalse(self.detect(
            "03:00.0 VGA compatible controller: Advanced Micro Devices, Inc. [AMD/ATI] Navi 23"))

    def test_lspciMissingIsNotIntel(self):
        with mock.patch('FFMPEGTools.subprocess.run', side_effect=OSError("no lspci")):
            self.assertFalse(GPUTools.is_intel_gpu_active())


class HwdecChoiceTest(unittest.TestCase):
    """_prepareTrackPath sets the kind and, on Intel, the decoder"""

    def prepare(self, path, **kw):
        p = player(**kw)
        hw = {'value': p._gpuHwdec.split(','), 'writes': 0}

        class Mpv:
            @property
            def hwdec(self):
                return hw['value']

            @hwdec.setter
            def hwdec(self, v):
                hw['value'] = v.split(',')   # mpv splits a candidate list
                hw['writes'] += 1
        p.mpv = Mpv()
        p.mpv_hw = hw
        EasyPlayer.Player._prepareTrackPath(p, path)
        return p, hw

    def test_stillSelectsSoftwareDecoding(self):
        p, hw = self.prepare('/x/photo.jpg')
        self.assertIs(p.kind, MediaKind.STILL)
        self.assertEqual(hw['value'], ['no'])

    def test_videoKeepsHardwareDecoding(self):
        p, hw = self.prepare('/x/clip.mp4')
        self.assertIs(p.kind, MediaKind.VIDEO)
        self.assertEqual(hw['value'], ['vaapi-copy', 'no'])

    def test_noWriteWhenTheDecoderAlreadyMatches(self):
        """mpv reports hwdec as a list; comparing it to a string always differed,
        so every navigation re-initialised the decoder for nothing"""
        p, hw = self.prepare('/x/clip.mp4')
        self.assertEqual(hw['writes'], 0)

    def test_alreadyProbedAudioIsNotDemotedToVideo(self):
        """returning to a played track never probes again, so the conservative
        VIDEO default would stick and the spectrum would stay off"""
        p, _ = self.prepare('/x/song.mp3', probed='/x/song.mp3', audioOnly=True)
        self.assertIs(p.kind, MediaKind.AUDIO)

    def test_nonIntelNeverTouchesTheDecoder(self):
        p, hw = self.prepare('/x/photo.jpg', intel=False)
        self.assertIs(p.kind, MediaKind.STILL, "kind is resolved on every GPU")
        self.assertEqual(hw['writes'], 0, "but only Intel changes hwdec")
        self.assertEqual(hw['value'], ['vaapi-copy', 'no'])


class MpvFallbackTest(unittest.TestCase):
    """A machine whose GL stack cannot serve us must not take the app down.
    vo stays libmpv either way - MpvRenderContext only receives frames from that
    VO - so the retry switches the GL mode, not the VO."""

    def rig(self):
        p = Stub()
        p.asked = []

        def getArgs(isVirtual):
            p.asked.append(isVirtual)
            return {'virtual': isVirtual}
        p._getMPVArgs = getArgs
        return p

    def test_normalStartUsesTheRequestedMode(self):
        p = self.rig()
        with mock.patch('EasyPlayer.MPV', return_value='mpv') as MPV:
            self.assertEqual(EasyPlayer.Player._createMpv(p, False), 'mpv')
        self.assertEqual(p.asked, [False])
        MPV.assert_called_once_with(virtual=False)

    def test_failureRetriesInSoftwareMode(self):
        p = self.rig()
        with mock.patch('EasyPlayer.MPV', side_effect=[Exception('no GL'), 'mpv']):
            self.assertEqual(EasyPlayer.Player._createMpv(p, False), 'mpv')
        self.assertEqual(p.asked, [False, True], "second attempt must be the virtual config")

    def test_failureInSoftwareModeIsNotSwallowed(self):
        """there is nothing safer left to try - do not pretend it worked"""
        p = self.rig()
        with mock.patch('EasyPlayer.MPV', side_effect=Exception('hopeless')):
            with self.assertRaises(Exception):
                EasyPlayer.Player._createMpv(p, True)
        self.assertEqual(p.asked, [True], "no pointless retry of the same config")


if __name__ == '__main__':
    unittest.main()
