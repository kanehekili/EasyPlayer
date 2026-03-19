# DOC.md

This file provides technical insights for developers

## Running the Application

Run from the `src/` directory (required — icons and config paths are relative to it):

```bash
cd src
python3 EasyPlayer.py [OPTIONS] [FILE]
```

CLI options:
- `-c` / `--console` — log to stdout instead of `~/.config/EasyPlayer/`
- `-d` / `--debug` — set log level to DEBUG
- `-v` / `--virtual` — use GPU dumb mode (for virtual machines / no hardware acceleration)

## Dependencies

- Python 3, PyQt6, ffmpeg/ffprobe (must be on PATH)
- `src/lib/mpv.py` — bundled Python binding for libmpv (must have libmpv installed system-wide)

## Architecture

All source lives in `src/`. There are no tests.

### Key modules

**`EasyPlayer.py`** — entry point and all UI classes:
- `Player` (`QOpenGLWidget`): embeds libmpv via `MpvRenderContext` + OpenGL FBO. Owns the `MPV` instance and all seek/play logic. Uses a `Condition` lock to synchronize async seek completion (`_waitSeekDone`). Detects transport streams and interlaced video via `FFStreamProbe` and tweaks mpv parameters accordingly. Auto-switches to `nvdec` hardware decoding when `/proc/driver/nvidia/version` exists.
- `MainFrame` (`QMainWindow`): main window with toolbar, slider, and info label. Connects `Player` signals to UI updates. Slider is scaled to `SLIDER_RESOLUTION = 1_000_000` to maintain float precision.
- `Worker` (`QThread`): runs `player.startPlaying()` off the main thread to avoid blocking the UI.
- `SettingsModel`: holds runtime settings (subtitles, EQ, icon theme), persisted to `~/.config/EasyPlayer/ep.ini` via `ConfigAccessor`.
- `IconMapper`: maps logical icon names (e.g. `"playStart"`) to file paths using `icons/icomap.json`, supports multiple themes.

**`FFMPEGTools.py`** — utilities with no Qt dependency:
- `FFStreamProbe`: runs `ffprobe` to parse container/stream metadata. Returns `VideoStream`, `AudioStream`, and `FormatInfo` objects.
- `OSTools`: filesystem helpers (`joinPathes`, `getLocalPath`, desktop detection, etc.).
- `ConfigAccessor`: `configparser`-based INI reader/writer. Config file is stored at `~/.config/<AppName>/<name>`.
- Logging: `setupRotatingLogger` sets up a 5 MB rotating log at `~/.config/EasyPlayer/EasyPlayer.log`.

**`QtTools.py`** — Qt threading helpers:
- `SliderThread`: debounces rapid slider drag events; only forwards the latest seek position to avoid mpv seek queue buildup.

### Signal flow

```
Slider drag → SliderThread → player.seek() (absolute)
mpv time-pos event → Player._onTimePos → triggerUpdate signal → MainFrame._onSyncSlider → Slider + InfoLabel
mpv eof-reached → Player.toggleVideoPlay → syncPlayStatus → MainFrame._onSyncPlayerControls
```

### Config & state

- App config: `~/.config/EasyPlayer/ep.ini`
- Log files: `~/.config/EasyPlayer/EasyPlayer.log` (rotated, gzip-compressed)
- Working directory must be `src/` at startup so relative icon paths resolve correctly (`OSTools.setMainWorkDir` is called with `__file__`'s directory)

## Packaging

`build.gradle` + `settings.gradle` handle distribution packaging for Arch and Ubuntu (`.desktop` files, DEB templates). Not needed for local development.
