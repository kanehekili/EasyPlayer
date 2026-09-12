"""What the window title shows.

It follows mpv's media-title, which falls back to the file name when a track has
no title metadata. Network streams are excluded on purpose: their ICY metadata
changes on every song and would rewrite the title (and the taskbar entry) each
time. Those updates still go to ui_NowPlaying.
"""
import unittest
import support

from EasyPlayer import MainFrame, AppName


class StubMpv:
    def __init__(self, path):
        self.path = path


class StubPlayer:
    def __init__(self, path):
        self.mpv = StubMpv(path)


class Harness:
    updateWindowTitle = MainFrame.updateWindowTitle
    setWindowLabel = MainFrame.setWindowLabel
    _onTitleChanged = MainFrame._onTitleChanged

    def __init__(self, path):
        self.player = StubPlayer(path)
        self.title = None

    def setWindowTitle(self, text):
        self.title = text


class WindowTitleTest(unittest.TestCase):

    def setUp(self):
        support.app()

    def test_openingAFileUsesItsName(self):
        harness = Harness('/media/holiday/img_042.jpg')
        harness.updateWindowTitle('/media/holiday/img_042.jpg')
        self.assertEqual(harness.title, AppName + ' - img_042.jpg')

    def test_mediaTitleWins(self):
        """a tagged video shows its title, not its file name"""
        harness = Harness('/media/films/titled.mkv')
        harness._onTitleChanged('Der Untergang')
        self.assertEqual(harness.title, AppName + ' - Der Untergang')

    def test_untaggedTrackFallsBackToTheFileName(self):
        """mpv reports the file name as media-title when there is no metadata"""
        harness = Harness('/media/holiday/b.png')
        harness._onTitleChanged('b.png')
        self.assertEqual(harness.title, AppName + ' - b.png')

    def test_titleFollowsTrackChanges(self):
        harness = Harness('/media/holiday/a.png')
        harness._onTitleChanged('a.png')
        harness.player.mpv.path = '/media/holiday/b.png'
        harness._onTitleChanged('b.png')
        self.assertEqual(harness.title, AppName + ' - b.png',
                         'title must not go stale after next/prev')

    def test_streamsDoNotRewriteTheTitle(self):
        harness = Harness('http://stream.example/radio')
        harness.setWindowLabel('radio')
        harness._onTitleChanged('Some Band - Some Song')
        self.assertEqual(harness.title, AppName + ' - radio',
                         'ICY metadata must not churn the window title')

    def test_emptyTitleIsIgnored(self):
        harness = Harness('/media/holiday/a.png')
        harness.setWindowLabel('a.png')
        harness._onTitleChanged('')
        self.assertEqual(harness.title, AppName + ' - a.png')

    def test_noPathIsIgnored(self):
        harness = Harness(None)
        harness.setWindowLabel('idle')
        harness._onTitleChanged('anything')
        self.assertEqual(harness.title, AppName + ' - idle')

    def test_titleWithASlashIsNotTruncated(self):
        """media titles are not paths - they must not be basenamed"""
        harness = Harness('/media/films/x.mkv')
        harness._onTitleChanged('AC/DC - Live')
        self.assertEqual(harness.title, AppName + ' - AC/DC - Live')


if __name__ == '__main__':
    unittest.main()
