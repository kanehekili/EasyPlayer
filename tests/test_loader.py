"""Player.startPlayingList against a real libmpv.

This is the one test that talks to mpv. It exists because a stubbed mpv cannot
show the bug it guards: opening a file from the file manager used to play the
first file in the folder before jumping to the one that was actually selected.
"""
import os
import time
import types
import unittest
import support

try:
    from lib.mpv import MPV
    HAS_MPV = True
except Exception:
    HAS_MPV = False

from EasyPlayer import Player  # noqa: E402


class LoaderRig:
    """the slice of Player that startPlayingList uses, over a real mpv"""
    startPlayingList = Player.startPlayingList
    nextTrack = Player.nextTrack
    prevTrack = Player.prevTrack
    _getReady = Player._getReady
    _onReadyWait = Player._onReadyWait
    _onDuration = Player._onDuration

    def __init__(self, mpv):
        self.mpv = mpv
        self.closePending = False
        self.lastError = None
        self.duration = 0
        self.durString = ""
        self.isPlaylist = False
        self.filePath = None
        self.streamData = None
        self.isAudioOnly = False
        self._probedPath = None
        self.probed = []
        self.loadedEmits = 0

    @property
    def fileLoaded(self):
        return types.SimpleNamespace(emit=self._countLoaded)

    def _countLoaded(self):
        self.loadedEmits += 1

    def _probeCurrentTrack(self):
        self.probed.append(self.mpv.path)
        self.loadedEmits += 1

    def _on_update(self):
        pass


@unittest.skipUnless(HAS_MPV, 'libmpv not available')
class StartPlayingListTest(unittest.TestCase):

    def setUp(self):
        support.app()   # also pins LC_NUMERIC to C, which libmpv requires
        self.paths = [support.media('a.png'), support.media('b.png'),
                      support.media('movie.mkv'), support.media('sub/c.png')]
        self.opened = []
        self.mpv = MPV(vo='null', keep_open='always', image_display_duration='inf',
                       loglevel='error', audio='no')
        self.mpv.observe_property('path', self._onPath)
        self.rig = LoaderRig(self.mpv)

    def tearDown(self):
        try:
            self.mpv.terminate()
        except Exception:
            pass

    def _onPath(self, _name, value):
        if value:
            self.opened.append(value)

    def settle(self, ms=400):
        time.sleep(ms / 1000.0)

    def test_startsExactlyTheSelectedFile(self):
        for index in range(len(self.paths)):
            with self.subTest(startIdx=index):
                self.setUp()
                self.rig.startPlayingList(self.paths, index)
                self.settle()
                want = self.paths[index]
                self.assertEqual(self.opened, [want],
                                 'mpv must open only the selected file')
                self.assertEqual(self.mpv.playlist_pos, index)
                self.assertEqual(self.rig.probed, [want])
                self.tearDown()

    def test_playlistOrderIsPreserved(self):
        self.rig.startPlayingList(self.paths, 2)
        self.settle()
        entries = [e['filename'] for e in self.mpv.playlist]
        self.assertEqual(entries, self.paths)

    def test_outOfRangeIndexIsClamped(self):
        self.rig.startPlayingList(self.paths, 99)
        self.settle()
        self.assertEqual(self.mpv.playlist_pos, len(self.paths) - 1)

    def test_negativeIndexIsClamped(self):
        self.rig.startPlayingList(self.paths, -5)
        self.settle()
        self.assertEqual(self.mpv.playlist_pos, 0)

    def test_emptyListIsSafe(self):
        self.rig.startPlayingList([], 0)
        self.assertEqual(self.rig.loadedEmits, 1, 'fileLoaded must still fire')
        self.assertEqual(self.rig.probed, [])

    def test_singleFile(self):
        one = [support.media('movie.mkv')]
        self.rig.startPlayingList(one, 0)
        self.settle()
        self.assertEqual(self.opened, one)
        self.assertEqual(len(self.mpv.playlist), 1)

    def test_nextWrapsFromLastToFirst(self):
        self.rig.startPlayingList(self.paths, len(self.paths) - 1)
        self.settle()
        self.rig.nextTrack()
        self.settle()
        self.assertEqual(self.mpv.playlist_pos, 0)
        self.assertEqual(self.mpv.path, self.paths[0])

    def test_prevWrapsFromFirstToLast(self):
        self.rig.startPlayingList(self.paths, 0)
        self.settle()
        self.rig.prevTrack()
        self.settle()
        self.assertEqual(self.mpv.playlist_pos, len(self.paths) - 1)
        self.assertEqual(self.mpv.path, self.paths[-1])

    def test_singleItemDoesNotWrap(self):
        one = [support.media('a.png')]
        self.rig.startPlayingList(one, 0)
        self.settle()
        self.rig.nextTrack()
        self.rig.prevTrack()
        self.settle()
        self.assertEqual(self.mpv.playlist_pos, 0, 'single entry must stay put')

    def test_reloadReplacesThePreviousList(self):
        self.rig.startPlayingList(self.paths, 0)
        self.settle()
        shorter = [support.media('b.png'), support.media('a.png')]
        self.rig.startPlayingList(shorter, 1)
        self.settle()
        self.assertEqual(len(self.mpv.playlist), 2, 'old entries must be gone')
        self.assertEqual(self.mpv.playlist_pos, 1)


if __name__ == '__main__':
    unittest.main()
