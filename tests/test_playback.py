"""The playing/not-playing concept.

transport ("playing") is what the play button shows and toggles.
follow is "when this item ends, go to the next one".
Everything below is an assertion about those two and nothing else.
"""
import unittest
import support


class PlaybackStateTest(unittest.TestCase):

    def setUp(self):
        support.app()
        self.pics = [support.media('a.png'), support.media('b.png'),
                     support.media('sub/c.png')]
        self.mixed = [support.media('a.png'), support.media('movie.mkv'),
                      support.media('b.png')]

    def assertState(self, rig, playing, msg=''):
        self.assertEqual(rig.playback.isPlaying(), playing, 'playing ' + msg)
        self.assertEqual(rig.icon, 'Pause' if playing else 'Play', 'icon ' + msg)
        # a paused still must never have an armed timer; a playing one always must
        if rig.showingStill:
            self.assertEqual(rig.timerArmed, playing, 'slide timer ' + msg)

    # ---------------------------------------------------------- opening

    def test_openedPictureHolds(self):
        rig = support.PlaybackRig(self.pics)
        rig.open(playing=False, follow=False)
        self.assertState(rig, False, 'right after open')
        support.spin(1400)
        self.assertState(rig, False, 'after more than one slide duration')
        self.assertEqual(rig.pos, 0, 'must not have advanced on its own')

    def test_openedVideoPlaysThenStops(self):
        rig = support.PlaybackRig([support.media('movie.mkv')])
        rig.open(playing=True, follow=False)
        self.assertState(rig, True, 'video opened')
        self.assertFalse(rig.player.mpv.pause, 'mpv must be unpaused')
        rig.playback.onItemEnded()
        self.assertState(rig, False, 'video ended')

    def test_loadErrorStops(self):
        rig = support.PlaybackRig(self.pics)
        rig.playback.setInitial(playing=True, follow=True)
        rig.player.lastError = 'boom'
        rig.playback.onItemLoaded()
        self.assertState(rig, False, 'after a failed load')

    # ------------------------------------------------------------- toggle

    def test_playThenPause(self):
        rig = support.PlaybackRig(self.pics)
        rig.open(playing=False, follow=False)
        rig.playback.toggle()
        self.assertState(rig, True, 'after play')
        self.assertTrue(rig.playback.follows(), 'play must turn follow on')
        rig.playback.toggle()
        self.assertState(rig, False, 'after pause')

    def test_pauseThenPrevKeepsItPaused(self):
        """the reported bug: prev restarted the slideshow behind a Play icon"""
        rig = support.PlaybackRig(self.pics)
        rig.open(playing=False, follow=False)
        rig.playback.toggle()          # play
        rig.playback.toggle()          # pause
        rig.player.mpv.playlist_pos = 2
        rig.load()
        rig.player.prevTrack()
        rig.player.prevTrack()
        self.assertState(rig, False, 'after prev x3')
        self.assertFalse(rig.timerArmed, 'prev must not restart the slide timer')
        # and one press must be enough to get going again
        rig.playback.toggle()
        self.assertState(rig, True, 'one press resumes')
        rig.playback.toggle()
        self.assertState(rig, False, 'one press stops')

    # ------------------------------------------------------- next / prev

    def test_navigationDuringARunningShowKeepsItRunning(self):
        rig = support.PlaybackRig(self.mixed)
        rig.open(playing=True, follow=True)
        for step in ('next', 'next', 'prev', 'prev'):
            getattr(rig.player, step + 'Track')()
            self.assertState(rig, True, 'after ' + step)
            self.assertTrue(rig.playback.follows(), 'show must survive ' + step)

    def test_browsingIsPerType(self):
        """the item decides: stepping onto a video plays it, onto a still holds"""
        rig = support.PlaybackRig(self.mixed)      # image, video, image
        rig.open(playing=False, follow=False)
        rig.player.nextTrack()                     # -> movie.mkv
        self.assertFalse(rig.showingStill, 'should be on the video now')
        self.assertState(rig, True, 'video plays automatically')
        self.assertFalse(rig.playback.follows(), 'browsing must not start a run')
        rig.player.nextTrack()                     # -> image again
        self.assertState(rig, False, 'still holds')
        rig.player.prevTrack()                     # back to the video
        self.assertState(rig, True, 'video plays again')

    def test_browsedVideoStopsAtItsEnd(self):
        rig = support.PlaybackRig(self.mixed)
        rig.open(playing=False, follow=False)
        rig.player.nextTrack()                     # -> movie.mkv, plays
        rig.playback.onItemEnded()
        self.assertState(rig, False, 'must not roll on while browsing')

    def test_pausedShowIsDroppedByNavigation(self):
        """pause the show, step somewhere else - browsing, not a hidden show"""
        rig = support.PlaybackRig(self.mixed)
        rig.open(playing=False, follow=False)
        rig.playback.toggle()                      # show runs (image -> follow)
        rig.playback.toggle()                      # suspended, follow kept
        self.assertTrue(rig.playback.follows())
        rig.player.nextTrack()                     # -> video: plays, per-type
        self.assertState(rig, True, 'video plays')
        self.assertFalse(rig.playback.follows(), 'the suspended show is gone')
        rig.playback.onItemEnded()
        self.assertState(rig, False, 'and it stops at the end')

    def test_resumingABrowsedVideoDoesNotStartARun(self):
        rig = support.PlaybackRig(self.mixed)
        rig.open(playing=False, follow=False)
        rig.player.nextTrack()                     # -> video, plays
        rig.playback.toggle()                      # pause it
        self.assertState(rig, False, 'paused')
        rig.playback.toggle()                      # resume it
        self.assertState(rig, True, 'resumed')
        self.assertFalse(rig.playback.follows(), 'resume must not enable follow')

    def test_suspendedShowResumesOnAVideo(self):
        """pause mid-video during a run, play again - the run continues"""
        rig = support.PlaybackRig(self.mixed)
        rig.open(playing=True, follow=True)
        rig.player.nextTrack()                     # show reaches the video
        rig.playback.toggle()                      # suspend
        rig.playback.toggle()                      # resume
        self.assertState(rig, True, 'resumed')
        self.assertTrue(rig.playback.follows(), 'the run must continue')

    def test_manualNavigationWrapsAround(self):
        """<< at the first item lands on the last, >> at the last on the first -
        still per-type, so wrapping onto a video plays it"""
        rig = support.PlaybackRig(self.mixed)      # image, video, image
        rig.open(playing=False, follow=False)
        rig.player.prevTrack()                     # wrap: first -> last (image)
        self.assertEqual(rig.pos, len(self.mixed) - 1)
        self.assertState(rig, False, 'wrapped onto the last still')
        rig.player.nextTrack()                     # wrap: last -> first (image)
        self.assertEqual(rig.pos, 0)
        self.assertState(rig, False, 'wrapped back to the first still')
        rig.player.mpv.playlist_pos = len(self.mixed) - 1
        rig.load()
        rig.player.prevTrack()                     # last -> video
        self.assertState(rig, True, 'per-type still applies after stepping')

    def test_theShowStillEndsDespiteWrapping(self):
        """only manual navigation wraps - the show stops at the last item"""
        rig = support.PlaybackRig(self.pics)
        rig.open(playing=True, follow=True)
        rig.player.mpv.playlist_pos = len(self.pics) - 1
        rig.load()
        rig.playback.onItemEnded()                 # last slide ran out
        self.assertEqual(rig.pos, len(self.pics) - 1, 'must not wrap to the first')
        self.assertState(rig, False, 'show ended')

    # ------------------------------------------------------ running out

    def test_slideshowRunsToTheEndThenStops(self):
        rig = support.PlaybackRig(self.pics)
        rig.open(playing=False, follow=False)
        rig.playback.toggle()
        support.spin(3600)
        self.assertEqual(rig.pos, len(self.pics) - 1, 'should reach the last slide')
        self.assertState(rig, False, 'after the last slide')
        self.assertTrue(rig.playback.atEnd(), 'atEnd should report the end')

    def test_playlistFollowsFromTheStart(self):
        """an .m3u is loaded with follow already on and rolls without a play press"""
        rig = support.PlaybackRig(self.pics)
        rig.open(playing=True, follow=True)
        self.assertState(rig, True, 'playlist loaded')
        support.spin(3600)
        self.assertEqual(rig.pos, len(self.pics) - 1)
        self.assertState(rig, False, 'playlist finished')


if __name__ == '__main__':
    unittest.main()
