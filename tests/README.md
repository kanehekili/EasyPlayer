# EasyPlayer tests

Regression tests for the parts that were painful to get right: zoom geometry,
the play/pause state machine, the folder scan, and the mpv load order.

## Running them

From the repository root:

```
python3 -m unittest discover -s tests
```

Verbose, or a single file:

```
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s tests -p test_playback.py
```

A single test:

```
cd tests && python3 -m unittest test_playback.PlaybackStateTest.test_pauseThenPrevKeepsItPaused
```

Takes about 45 seconds, or 20 without the gui test. Most of that is the
slideshow timers and the gui test, which both have to run in real time, plus
generating the media fixtures once per run.

## Requirements

Nothing beyond what the app already needs: **python3-pyqt6, ffmpeg, libmpv** -
except `test_gui.py`, which also wants `xdotool` and ImageMagick (see below).
No pytest, no test-only packages - it is plain `unittest` from the standard
library.

Qt runs with `QT_QPA_PLATFORM=offscreen`, so no display is needed and no windows
appear. Tests that need `ffmpeg` or `libmpv` skip themselves if those are
missing rather than failing.

**`test_gui.py` is the exception** - it launches the real app on the real
display, so a window pops up for a few seconds. It needs `xdotool` and
ImageMagick's `import`, and skips itself when either is missing or there is no
`DISPLAY`. **It also closes any EasyPlayer that is already running** - the
window search matches by title, and a second instance (yours, or a zombie from
an aborted run) would otherwise be picked up and driven by the tests. To skip
the gui test deliberately:

```
EASYPLAYER_SKIP_GUI=1 python3 -m unittest discover -s tests
```

## Layout

| file | what it covers |
|------|----------------|
| `support.py` | shared bootstrap: offscreen Qt, `src/` on the path, generated media fixtures, and the stub player used by the playback tests |
| `test_zoom.py` | Ctrl+wheel zoom geometry, drag-pan, the hand cursor, and `ImageOverlay` rendering checked pixel by pixel |
| `test_playback.py` | browse vs show: navigation lands per-type (video plays once, still holds), play runs the list, follow governs advancing |
| `test_media.py` | extension sets, file dialog filter, folder scan, ffmpeg still fallback, and every `icomap.json` entry resolving to a loadable icon |
| `test_loader.py` | `Player.startPlayingList` and the next/prev wrap-around against a **real** libmpv |
| `test_playvideo.py` | which branch `MainFrame.playVideo` takes, and that a panel double-click is navigation while the play button dictates a run |
| `test_title.py` | what the window title shows, and why streams are excluded |
| `test_gui.py` | the **real app on a real display**: window opens, toolbar icons are drawn, ctrl+Right/Left walk the folder and retitle the window |

## Fixtures

`support.mediaDir()` builds a throwaway tree once per run and deletes it on
exit:

```
a.png  b.png  movie.mkv  notes.txt
sub/c.png
sub/deeper/d.png
.hidden/skip.png
```

The pictures come from Qt, the video from ffmpeg. `notes.txt` and `.hidden/`
are there to prove the scan skips them. `support.makeAvif()` adds an avif on
demand for the fallback test. Nothing is committed - use
`support.media('a.png')` to reach a fixture.

## Notes

**`support.app()` pins `LC_NUMERIC` to `C`.** Creating a `QApplication` adopts
the system locale, and libmpv refuses to run without C numerics - it aborts the
process. `EasyPlayer.main()` does the same thing after creating the app. Any
test that touches mpv must call `support.app()` first.

**`test_loader.py` uses a real mpv on purpose.** The bug it guards - opening a
file from the file manager played the first file in the folder before jumping to
the selected one - cannot be reproduced against a stub, because it is caused by
mpv auto-starting playlist entry 0 while entries are being appended. A stub was
what let a wrong fix look correct.

**Icons are checked from two sides.** `IconMapTest` in `test_media.py` asserts
every `icomap.json` entry resolves to a file that loads as a `QIcon`, and that no
icon file is orphaned - a wrong path is otherwise silent, since `QIcon()` on a
missing file just yields a blank button. `test_gui.py` then counts coloured
icons in a screenshot of the real toolbar. The unit test is the precise one; the
screenshot only proves the toolbar reaches the screen at all.

**The playback tests use the real controllers.** `PlaybackController` and
`SlideshowController` are the genuine classes; only `Player` and mpv are stubbed
(`support.StubPlayer`). The invariant *a paused still never has an armed timer*
is asserted on every state check in `test_playback.py` - that is the property
whose violation caused the slideshow to run behind a "Play" icon.

## Things that are not covered

- The spectrum analyser, and `Player.paintGL` in any detail - `test_gui.py`
  proves the render context comes up and draws, nothing finer than that.
- Drag and drop into the playlist panel, and the file dialogs themselves.
- Window layout and geometry - the toolbar is only checked for icons being
  drawn, not for arrangement.
