"""Which branch MainFrame.playVideo takes, and what a panel double-click means.

playVideo decides between starting a list that was never played, replaying one
that has finished, running on after a video ended, and toggling the transport.
_onPlaylistPlay is navigation on double-click (run=False) and "run the list"
for the play button (run=True). The real methods are bound onto small harnesses
so the branching is tested, not a copy of it.
"""
import unittest
import support

support.initPlaylistModule()

import Playlist          # noqa: E402
from EasyPlayer import MainFrame  # noqa: E402


class StubMpv:
    def __init__(self, path):
        self.path = path
        self.playlist_pos = 0


class StubPlayer:
    def __init__(self, path, eof=False, hasNext=False):
        self.mpv = StubMpv(path)
        self._eof = eof
        self._hasNext = hasNext
        self.stepped = 0
        self.jumped = None

    def isEOF(self):
        return self._eof

    def hasNextTrack(self):
        return self._hasNext

    def nextTrack(self):
        self.stepped += 1

    def jumpToTrack(self, idx):
        self.jumped = idx
        self.mpv.playlist_pos = idx


class StubPlayback:
    def __init__(self, atEnd=False, playing=False):
        self._atEnd = atEnd
        self._playing = playing
        self.toggled = False
        self.initial = None
        self.loadedCalls = 0

    def atEnd(self):
        return self._atEnd

    def isPlaying(self):
        return self._playing

    def toggle(self):
        self.toggled = True

    def setInitial(self, playing, follow):
        self.initial = (playing, follow)

    def onItemLoaded(self):
        self.loadedCalls += 1


class PlayVideoHarness:
    playVideo = MainFrame.playVideo
    _isIdleWithPanelTracks = MainFrame._isIdleWithPanelTracks

    def __init__(self, loadedPath=None, tracks=(), atEnd=False,
                 eof=False, hasNext=False, playing=False):
        self.player = StubPlayer(loadedPath, eof=eof, hasNext=hasNext)
        self.playback = StubPlayback(atEnd=atEnd, playing=playing)
        self.playlistPanel = Playlist.PlaylistPanel()
        self.playlistPanel.addPaths(list(tracks))
        self.started = None

    def _onPlaylistPlay(self, index, run=False):
        self.started = (index, run)

    def outcome(self):
        if self.started is not None:
            return 'start(idx=%d, run=%s)' % self.started
        if self.player.stepped:
            return 'runOnFromNext'
        return 'toggle' if self.playback.toggled else 'nothing'


class PlayVideoBranchTest(unittest.TestCase):

    def setUp(self):
        support.app()
        self.tracks = [support.media('a.png'), support.media('b.png')]

    def play(self, **kwargs):
        harness = PlayVideoHarness(**kwargs)
        harness.playVideo()
        return harness

    def test_startsTracksThatWereNeverPlayed(self):
        """dropping files into the panel then pressing play must RUN them"""
        harness = self.play(tracks=self.tracks)
        self.assertEqual(harness.outcome(), 'start(idx=0, run=True)')

    def test_startsAtTheSelectedRow(self):
        harness = PlayVideoHarness(tracks=self.tracks)
        harness.playlistPanel.trackList.setCurrentRow(1)
        harness.playVideo()
        self.assertEqual(harness.outcome(), 'start(idx=1, run=True)')

    def test_togglesWhenSomethingIsLoaded(self):
        harness = self.play(loadedPath=support.media('movie.mkv'), tracks=self.tracks)
        self.assertEqual(harness.outcome(), 'toggle')

    def test_togglesWithAnEmptyPanel(self):
        harness = self.play(tracks=())
        self.assertEqual(harness.outcome(), 'toggle')

    def test_replaysAFinishedListAsARun(self):
        harness = self.play(loadedPath=support.media('b.png'),
                            tracks=self.tracks, atEnd=True)
        self.assertEqual(harness.outcome(), 'start(idx=0, run=True)')

    def test_playAfterAVideoEndedRunsOn(self):
        """unpausing an eof'd file does nothing in mpv - play must advance"""
        harness = self.play(loadedPath=support.media('movie.mkv'),
                            tracks=self.tracks, eof=True, hasNext=True)
        self.assertEqual(harness.outcome(), 'runOnFromNext')
        self.assertEqual(harness.playback.initial, (True, True),
                         'running on must arm follow')

    def test_eofWithNothingAfterItToggles(self):
        harness = self.play(loadedPath=support.media('movie.mkv'),
                            tracks=[self.tracks[0]], eof=True, hasNext=False)
        self.assertEqual(harness.outcome(), 'toggle')

    def test_eofWhilePlayingDoesNotSkip(self):
        """the eof branch is for the stopped state only"""
        harness = self.play(loadedPath=support.media('movie.mkv'),
                            tracks=self.tracks, eof=True, hasNext=True,
                            playing=True)
        self.assertEqual(harness.outcome(), 'toggle')


class DoubleClickHarness:
    """the real _onPlaylistPlay over recording stubs"""
    _onPlaylistPlay = MainFrame._onPlaylistPlay

    def __init__(self, tracks, dirty=False, pos=0):
        self.player = StubPlayer(tracks[pos] if tracks else None)
        self.player.isPlaylist = True
        self.player.filePath = None
        self.player.mpv.playlist_pos = pos
        self.playback = StubPlayback()
        self.playlistPanel = Playlist.PlaylistPanel()
        self.playlistPanel.addPaths(list(tracks))
        self._panelDirty = dirty
        self.asyncStarted = False

    def asyncPlay(self, func=None):
        self.asyncStarted = True


class DoubleClickTest(unittest.TestCase):
    """double-click is navigation: no transport is dictated, the loaded item
    decides. run=True is the play button and dictates a run."""

    def setUp(self):
        support.app()
        self.tracks = [support.media('a.png'), support.media('movie.mkv')]

    def test_doubleClickIsPureNavigation(self):
        harness = DoubleClickHarness(self.tracks)
        harness._onPlaylistPlay(1)
        self.assertIsNone(harness.playback.initial, 'must not dictate transport')
        self.assertEqual(harness.player.jumped, 1)

    def test_playButtonDictatesARun(self):
        harness = DoubleClickHarness(self.tracks)
        harness._onPlaylistPlay(1, run=True)
        self.assertEqual(harness.playback.initial, (True, True))
        self.assertEqual(harness.player.jumped, 1)

    def test_sameIndexAppliesTransportDirectly(self):
        """jumping to the current track fires no track event"""
        harness = DoubleClickHarness(self.tracks, pos=1)
        harness._onPlaylistPlay(1)
        self.assertEqual(harness.playback.loadedCalls, 1)

    def test_dirtyPanelReloadsTheList(self):
        harness = DoubleClickHarness(self.tracks, dirty=True)
        harness._onPlaylistPlay(0)
        self.assertTrue(harness.asyncStarted)
        self.assertIsNone(harness.player.jumped)

    def test_emptyPanelDoesNothing(self):
        harness = DoubleClickHarness([])
        harness._onPlaylistPlay(0)
        self.assertIsNone(harness.player.jumped)
        self.assertFalse(harness.asyncStarted)


if __name__ == '__main__':
    unittest.main()
