"""Formats, the folder scan and the file dialog filter."""
import os
import json
import unittest
import support

support.initPlaylistModule()

from PyQt6 import QtGui                                        # noqa: E402
from FFMPEGTools import OSTools                                # noqa: E402
from Slideshow import PICTURE_EXTENSIONS, ImageOverlay         # noqa: E402
from Playlist import (MEDIA_EXTENSIONS, PLAYLIST_EXTENSIONS,   # noqa: E402
                      PlaylistManager, PlaylistPanel, PlaylistParser)


class ExtensionTest(unittest.TestCase):

    def test_commonFormatsArePresent(self):
        for ext in ('.mp4', '.mkv', '.mp3', '.wav', '.flac', '.mts', '.m2ts'):
            self.assertIn(ext, MEDIA_EXTENSIONS, ext)
        for ext in ('.png', '.jpg', '.webp', '.tiff', '.avif', '.heic', '.heif'):
            self.assertIn(ext, PICTURE_EXTENSIONS, ext)

    def test_setsDoNotOverlap(self):
        self.assertEqual(MEDIA_EXTENSIONS & PICTURE_EXTENSIONS, set())
        self.assertEqual(MEDIA_EXTENSIONS & PLAYLIST_EXTENSIONS, set())
        self.assertEqual(PICTURE_EXTENSIONS & PLAYLIST_EXTENSIONS, set())


class FileDialogFilterTest(unittest.TestCase):
    """the default entry must list pictures too - they were missing once"""

    def setUp(self):
        support.app()
        self.patterns = PlaylistManager().formatExts(
            MEDIA_EXTENSIONS | PICTURE_EXTENSIONS | PLAYLIST_EXTENSIONS).split()

    def test_picturesAreInTheDefaultFilter(self):
        for ext in ('.png', '.jpg', '.webp', '.tiff', '.avif', '.heic'):
            self.assertIn('*' + ext, self.patterns, ext)

    def test_videoAudioAndPlaylistsAreInTheDefaultFilter(self):
        for ext in ('.mkv', '.mts', '.m2ts', '.mp3', '.wav', '.flac', '.m3u'):
            self.assertIn('*' + ext, self.patterns, ext)

    def test_bothCasesAreOffered(self):
        for ext in ('.jpg', '.mkv'):
            self.assertIn('*' + ext, self.patterns)
            self.assertIn('*' + ext.upper(), self.patterns)

    def test_patternCountMatchesTheSets(self):
        total = len(MEDIA_EXTENSIONS | PICTURE_EXTENSIONS | PLAYLIST_EXTENSIONS)
        self.assertEqual(len(self.patterns), total * 2, 'lower + upper case')


class PlaylistParserTest(unittest.TestCase):
    """m3u/pls/xspf parsing. Relative entries resolve against the playlist's own
    directory, URLs pass through untouched."""

    @classmethod
    def setUpClass(cls):
        import tempfile, shutil, atexit
        cls.root = tempfile.mkdtemp(prefix='easyplayer-lists-')
        atexit.register(shutil.rmtree, cls.root, True)
        support.makePicture(os.path.join(cls.root, 'a.png'), 8, 8, '#000000', 'a')

    def write(self, name, text):
        path = os.path.join(self.root, name)
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        return path

    def test_m3uResolvesRelativeEntries(self):
        path = self.write('list.m3u', 'a.png\nsub/b.png\n')
        self.assertEqual(PlaylistParser().parse(path),
                         [os.path.join(self.root, 'a.png'),
                          os.path.join(self.root, 'sub/b.png')])

    def test_m3uSkipsCommentsAndBlankLines(self):
        path = self.write('comments.m3u', '#EXTM3U\n\na.png\n#EXTINF:1,x\nb.png\n')
        self.assertEqual([os.path.basename(p) for p in PlaylistParser().parse(path)],
                         ['a.png', 'b.png'])

    def test_absoluteEntriesAreKept(self):
        path = self.write('abs.m3u', '/media/films/x.mkv\n')
        self.assertEqual(PlaylistParser().parse(path), ['/media/films/x.mkv'])

    def test_urlsPassThrough(self):
        path = self.write('radio.m3u', 'http://stream.example/radio\na.png\n')
        entries = PlaylistParser().parse(path)
        self.assertEqual(entries[0], 'http://stream.example/radio')
        self.assertEqual(entries[1], os.path.join(self.root, 'a.png'))

    def test_pls(self):
        path = self.write('list.pls',
                          '[playlist]\nNumberOfEntries=2\n'
                          'File1=a.png\nTitle1=first\n'
                          'File2=http://stream.example/x\n')
        self.assertEqual(PlaylistParser().parse(path),
                         [os.path.join(self.root, 'a.png'),
                          'http://stream.example/x'])

    def test_xspf(self):
        path = self.write('list.xspf',
                          '<?xml version="1.0" encoding="UTF-8"?>\n'
                          '<playlist version="1" xmlns="http://xspf.org/ns/0/">\n'
                          '  <trackList>\n'
                          '    <track><location>a.png</location></track>\n'
                          '    <track><location>http://stream.example/y</location></track>\n'
                          '  </trackList>\n</playlist>\n')
        self.assertEqual(PlaylistParser().parse(path),
                         [os.path.join(self.root, 'a.png'),
                          'http://stream.example/y'])

    def test_extensionMatchIsCaseInsensitive(self):
        path = self.write('upper.M3U', 'a.png\n')
        self.assertEqual(len(PlaylistParser().parse(path)), 1)

    def test_missingFileReturnsEmptyList(self):
        self.assertEqual(PlaylistParser().parse(os.path.join(self.root, 'nope.m3u')), [])

    def test_brokenXmlReturnsEmptyList(self):
        path = self.write('broken.xspf', 'this is not xml')
        self.assertEqual(PlaylistParser().parse(path), [])

    def test_unknownExtensionReturnsEmptyList(self):
        path = self.write('notalist.txt', 'a.png\n')
        self.assertEqual(PlaylistParser().parse(path), [])

    def test_managerDelegatesToTheParser(self):
        path = self.write('viamanager.m3u', 'a.png\n')
        self.assertEqual(PlaylistManager().parse(path),
                         [os.path.join(self.root, 'a.png')])


class IconMapTest(unittest.TestCase):
    """every icomap entry must point at a file that exists and actually loads

    A wrong path is silent at runtime: QIcon() on a missing file yields an empty
    icon and the button just looks blank. That is how "playlistPanel" pointed at
    ./icons/splitVertical (no extension) for a long time.
    """

    def setUp(self):
        support.app()
        self.icondir = os.path.join(support.SRC, 'icons')
        with open(os.path.join(self.icondir, 'icomap.json')) as handle:
            self.icomap = json.load(handle)

    def entries(self):
        for section, mapping in self.icomap.items():
            for key, value in mapping.items():
                yield section, key, value

    def resolve(self, value):
        return os.path.join(support.SRC, value.replace('./', '', 1))

    def test_thereAreEntries(self):
        self.assertGreater(len(list(self.entries())), 20, 'icomap looks empty')

    def test_everyEntryPointsAtAFile(self):
        missing = ['[%s] %s -> %s' % (s, k, v)
                   for s, k, v in self.entries()
                   if not os.path.isfile(self.resolve(v))]
        self.assertEqual(missing, [], 'icomap entries with no file:\n  ' +
                         '\n  '.join(missing))

    def test_everyEntryLoadsAsAnIcon(self):
        empty = []
        for section, key, value in self.entries():
            path = self.resolve(value)
            if not os.path.isfile(path):
                continue                       # reported by the test above
            if QtGui.QIcon(path).isNull():
                empty.append('[%s] %s -> %s' % (section, key, value))
        self.assertEqual(empty, [], 'icomap entries that render nothing:\n  ' +
                         '\n  '.join(empty))

    def test_defaultSectionCoversEveryKey(self):
        """ico() falls back to the default section, so it must be complete"""
        default = set(self.icomap['default'])
        for section, mapping in self.icomap.items():
            self.assertEqual(set(mapping) - default, set(),
                             '%s has keys the default section lacks' % section)

    def test_noOrphanedIconFiles(self):
        """files nothing points at - they still ship in every release tarball"""
        referenced = {os.path.normpath(self.resolve(v)) for _, _, v in self.entries()}
        # these are used from code or packaging rather than from icomap
        for name in ('CosmicRock.jpg', 'easyPlay.png', 'easyPlay.svg',
                     'icomap.json', 'license.txt'):
            referenced.add(os.path.join(self.icondir, name))
        orphans = []
        for dirpath, _dirnames, filenames in os.walk(self.icondir):
            for name in filenames:
                full = os.path.normpath(os.path.join(dirpath, name))
                if full not in referenced:
                    orphans.append(os.path.relpath(full, self.icondir))
        self.assertEqual(sorted(orphans), [], 'unused icon files: %s' % sorted(orphans))


class FolderScanTest(unittest.TestCase):

    def setUp(self):
        support.app()
        self.root = support.mediaDir()
        self.names = [os.path.basename(p)
                      for p in PlaylistManager().scanTree(support.media('a.png'))]

    def test_findsMediaAcrossSubfolders(self):
        for name in ('a.png', 'b.png', 'movie.mkv', 'c.png', 'd.png'):
            self.assertIn(name, self.names, name)

    def test_skipsNonMediaAndHiddenFolders(self):
        self.assertNotIn('notes.txt', self.names)
        self.assertNotIn('skip.png', self.names)

    def test_topLevelBeforeSubfolders(self):
        self.assertLess(self.names.index('b.png'), self.names.index('c.png'))

    def test_sortedWithinAFolder(self):
        self.assertLess(self.names.index('a.png'), self.names.index('b.png'))

    def test_openedFileIsInTheList(self):
        paths = PlaylistManager().scanTree(support.media('sub/c.png'))
        self.assertIn(support.media('sub/c.png'), paths)


class SortOrderTest(unittest.TestCase):
    """the panel must list files the way the file manager does: case-insensitive,
    numbers as numbers, digits before letters - not codepoint order, which put
    'Sony...' above 'appleFrank...' and made the folder look wrongly ordered"""

    @classmethod
    def setUpClass(cls):
        import tempfile, shutil, atexit
        cls.root = tempfile.mkdtemp(prefix='easyplayer-sort-')
        atexit.register(shutil.rmtree, cls.root, True)
        for name in ('00006.png', 'Sony Demo.png', 'appleFrank.png',
                     'result.png', 'COSTA RICA.png', 'merge.png',
                     'img2.png', 'img10.png'):
            support.makePicture(os.path.join(cls.root, name), 8, 8, '#000000', 'x')

    def names(self):
        return [os.path.basename(p)
                for p in OSTools().collectFiles(self.root, {'.png'})]

    def test_matchesTheFileManagerOrder(self):
        self.assertEqual(self.names(),
                         ['00006.png', 'appleFrank.png', 'COSTA RICA.png',
                          'img2.png', 'img10.png', 'merge.png',
                          'result.png', 'Sony Demo.png'])

    def test_caseIsIgnored(self):
        names = self.names()
        self.assertLess(names.index('result.png'), names.index('Sony Demo.png'))
        self.assertLess(names.index('appleFrank.png'), names.index('COSTA RICA.png'))

    def test_numbersSortAsNumbers(self):
        names = self.names()
        self.assertLess(names.index('img2.png'), names.index('img10.png'))

    def test_digitsComeBeforeLetters(self):
        self.assertEqual(self.names()[0], '00006.png')


class CollectFilesTest(unittest.TestCase):

    def setUp(self):
        self.root = support.mediaDir()

    def test_capIsHonoured(self):
        found = OSTools().collectFiles(self.root, {'.png', '.mkv'}, maxFiles=2)
        self.assertEqual(len(found), 2)

    def test_emptyExtensionSet(self):
        self.assertEqual(OSTools().collectFiles(self.root, set()), [])

    def test_missingDirectory(self):
        self.assertEqual(OSTools().collectFiles('/nonexistent/xyz', {'.png'}), [])

    def test_extensionMatchIsCaseInsensitive(self):
        found = OSTools().collectFiles(self.root, {'.png'})
        self.assertTrue(all(p.lower().endswith('.png') for p in found))


class PanelAddPathsTest(unittest.TestCase):

    def setUp(self):
        support.app()

    def test_onlyMediaIsAccepted(self):
        panel = PlaylistPanel()
        panel.addPaths([support.media('a.png'), support.media('movie.mkv'),
                        support.media('notes.txt')])
        self.assertEqual(len(panel.getPaths()), 2)

    def test_duplicatesAreIgnored(self):
        panel = PlaylistPanel()
        panel.addPaths([support.media('a.png'), support.media('a.png')])
        self.assertEqual(len(panel.getPaths()), 1)

    def test_currentIndexDefaultsToZero(self):
        panel = PlaylistPanel()
        panel.addPaths([support.media('a.png'), support.media('b.png')])
        self.assertEqual(panel.currentIndex(), 0, 'no selection -> first track')
        panel.trackList.setCurrentRow(1)
        self.assertEqual(panel.currentIndex(), 1)


class PanelLabelTest(unittest.TestCase):
    """entries below the list's root show their relative path, so subfolder
    content reads as such instead of looking like an oddly sorted sibling"""

    def setUp(self):
        support.app()
        self.root = support.mediaDir()

    def labels(self, panel):
        return [panel.trackList.item(i).text()
                for i in range(panel.trackList.count())]

    def test_relativeToTheRoot(self):
        panel = PlaylistPanel()
        panel.setTracks([support.media('a.png'), support.media('sub/c.png'),
                         support.media('sub/deeper/d.png')],
                        rootDir=self.root)
        self.assertEqual(self.labels(panel),
                         ['a.png', 'sub/c.png', 'sub/deeper/d.png'])

    def test_outsideTheRootFallsBackToTheName(self):
        panel = PlaylistPanel()
        panel.setTracks([support.media('a.png'), '/somewhere/else/track.mp3'],
                        rootDir=self.root)
        self.assertEqual(self.labels(panel), ['a.png', 'track.mp3'])

    def test_withoutARootAllNamesAreBare(self):
        panel = PlaylistPanel()
        panel.setTracks([support.media('a.png'), support.media('sub/c.png')])
        self.assertEqual(self.labels(panel), ['a.png', 'c.png'])

    def test_tooltipAlwaysCarriesTheFullPath(self):
        panel = PlaylistPanel()
        panel.setTracks([support.media('sub/c.png')], rootDir=self.root)
        self.assertEqual(panel.trackList.item(0).toolTip(),
                         support.media('sub/c.png'))

    def test_newListClearsTheRoot(self):
        panel = PlaylistPanel()
        panel.setTracks([support.media('sub/c.png')], rootDir=self.root)
        panel._onNew()
        panel.addPaths([support.media('sub/c.png')])
        self.assertEqual(self.labels(panel), ['c.png'])


@unittest.skipUnless(support.has('ffmpeg'), 'needs ffmpeg')
class StillFallbackTest(unittest.TestCase):
    """avif/heic have no Qt plugin here - ImageOverlay must fall back to ffmpeg"""

    def setUp(self):
        support.app()
        self.avif = support.makeAvif(os.path.join(support.mediaDir(), 'still.avif'))
        if not self.avif:
            self.skipTest('ffmpeg could not produce an avif')

    def test_qtAloneCannotReadIt(self):
        readable = [bytes(f).decode() for f in QtGui.QImageReader.supportedImageFormats()]
        if 'avif' in readable:
            self.skipTest('this machine has an avif Qt plugin, no fallback needed')
        self.assertTrue(QtGui.QPixmap(self.avif).isNull())

    def test_overlayLoadsItAnyway(self):
        overlay = ImageOverlay(None)
        overlay.resize(400, 300)
        overlay.setImage(self.avif)
        width, height = overlay.imageSize()
        self.assertTrue(width and height, 'fallback produced no image')
        self.assertEqual((width, height), (1600, 900))

    def test_overlayPaintsIt(self):
        overlay = ImageOverlay(None)
        overlay.resize(400, 300)
        overlay.setImage(self.avif)
        image = QtGui.QImage(400, 300, QtGui.QImage.Format.Format_RGB32)
        overlay.render(image)
        colour = image.pixelColor(200, 150)
        self.assertNotEqual((colour.red(), colour.green(), colour.blue()), (0, 0, 0),
                           'centre pixel is black - nothing was drawn')

    def test_unreadableFileIsHandled(self):
        broken = os.path.join(support.mediaDir(), 'broken.avif')
        with open(broken, 'wb') as handle:
            handle.write(b'not an image')
        overlay = ImageOverlay(None)
        overlay.resize(400, 300)
        overlay.setImage(broken)                 # must not raise
        self.assertEqual(overlay.imageSize(), (None, None))


if __name__ == '__main__':
    unittest.main()
