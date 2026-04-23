import subprocess
from threading import Thread
from PyQt6 import QtWidgets, QtCore, QtGui
import FFMPEGTools

Log = FFMPEGTools.Log

try:
    import numpy as np
    HAS_SPECTRUM = True
except ImportError:
    HAS_SPECTRUM = False

SPECTRUM_SAMPLE_RATE = 44100
SPECTRUM_BLOCK_SIZE = 4096


class ParecStream:
    def __init__(self, device, samplerate, blocksize, callback):
        self._proc = subprocess.Popen(
            ['parec', f'--device={device}', '--format=float32le',
             '--channels=1', f'--rate={samplerate}', '--latency-msec=20'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
        self._blocksize = blocksize
        self._callback = callback
        self._stopped = False
        self._thread = Thread(target=self._loop, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stopped = True
        self._proc.terminate()

    def close(self):
        try:
            self._proc.wait(timeout=1)
        except Exception:
            pass
        self._thread.join(timeout=1)

    def _loop(self):
        bytes_per_block = self._blocksize * 4
        while not self._stopped:
            data = self._proc.stdout.read(bytes_per_block)
            if not data or len(data) < bytes_per_block:
                break
            if not self._stopped:
                arr = np.frombuffer(data, dtype='float32').reshape(-1, 1)
                self._callback(arr, self._blocksize, None, None)


class SpectrumOverlay(QtWidgets.QWidget):
    BAND_EDGES = [50, 100, 200, 400, 800, 1600, 3200, 6400, 12800, 14000, 14500, 15000, 16000]
    BANDS = len(BAND_EDGES) - 1
    BAR_COLORS = ["heat", "rainbow", "blue", "green", "magenta", "red"]

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        from threading import Lock
        self._mags = [0.0] * self.BANDS
        self._lock = Lock()
        self.mode = "heat"

    def setMags(self, mags):
        with self._lock:
            self._mags = mags[:]
        self.update()

    def clearMags(self):
        with self._lock:
            self._mags = [0.0] * self.BANDS
        self.update()

    def paintEvent(self, __event):
        with self._lock:
            mags = self._mags[:]
        mode = self.mode
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor(15, 15, 15))
        w, h = self.width(), self.height()
        bar_w = w // self.BANDS
        gap = max(2, bar_w // 8)
        for i, level in enumerate(mags):
            bar_h = max(2, int(level * 0.9 * (h - 4)))
            x = i * bar_w + gap
            y = h - bar_h - 2
            if mode == "red":
                r = min(255, int(level * 2 * 255))
                g = min(255, int((1.0 - level) * 2 * 255))
                b = 0
                color = QtGui.QColor(r, g, b)
            elif mode == "magenta":
                r = min(255, int(level * 2 * 255))
                g = min(255, int((1.0 - level) * 2 * 255))
                b = min(255, max(0, int((level * 2 - 1) * 255)))
                color = QtGui.QColor(r, g, b)
            elif mode == "blue":
                r = 0
                g = min(255, int((1.0 - level) * 2 * 255))
                b = min(255, int(level * 2 * 255))
                color = QtGui.QColor(r, g, b)
            elif mode == "rainbow":
                hue = int(i / SpectrumOverlay.BANDS * 300)
                color = QtGui.QColor.fromHsv(hue, 220, max(30, int(level * 255)))
            elif mode == "heat":
                hue = int((1.0 - level) * 240)
                color = QtGui.QColor.fromHsv(hue, 255, max(80, int(level * 255)))
            else:  # green
                r = int((1.0 - level) * 255)
                g = int((1.0 - level * 0.6) * 255)
                b = 0
                color = QtGui.QColor(r, g, b)
            painter.fillRect(x, y, bar_w - gap * 2, bar_h, color)
        painter.end()


class SpectrumController(QtCore.QObject):
    def __init__(self, player):
        super().__init__()
        self._player = player
        self._specStream = None
        self._overlay = SpectrumOverlay(player)
        self._overlay.hide()

    @property
    def overlay(self):
        return self._overlay

    def setGeometry(self, x, y, w, h):
        self._overlay.setGeometry(x, y, w, h)

    def setMode(self, mode):
        self._overlay.mode = mode

    def getMode(self):
        return self._overlay.mode

    def startCapture(self):
        if not HAS_SPECTRUM or self._specStream is not None:
            return
        try:
            device = self._findMonitorDevice()
            if not device:
                Log.warning("Spectrum capture failed - no monitor device found")
                return
            self._specStream = ParecStream(
                device,
                SPECTRUM_SAMPLE_RATE,
                SPECTRUM_BLOCK_SIZE,
                self._audioCallback
            )
            self._specStream.start()
            self._overlay.show()
        except Exception:
            Log.warning("Spectrum capture failed - no valid device found")

    def stopCapture(self):
        if self._specStream:
            try:
                self._specStream.stop()
                self._specStream.close()
            except Exception:
                pass
            self._specStream = None
        self._overlay.hide()
        self._overlay.clearMags()

    def _findMonitorDevice(self):
        try:
            result = subprocess.run(['pactl', 'get-default-sink'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                monitor = result.stdout.strip() + '.monitor'
                Log.info("Spectrum: using parec with monitor source %s", monitor)
                return monitor
        except Exception:
            pass
        Log.info("Spectrum: no monitor device found")
        return None

    def _audioCallback(self, indata, __frames, __time, __status):
        data = indata[:, 0]
        windowed = data * np.hanning(len(data))
        fft_data = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(len(data), 1.0 / SPECTRUM_SAMPLE_RATE)
        DB_FLOOR = -100.0
        reference = SPECTRUM_BLOCK_SIZE / 15.0
        new_mags = []
        for i in range(SpectrumOverlay.BANDS):
            mask = (freqs >= SpectrumOverlay.BAND_EDGES[i]) & (freqs < SpectrumOverlay.BAND_EDGES[i + 1])
            if mask.any():
                val = float(np.max(fft_data[mask])) / reference
                db = 20.0 * np.log10(val) if val > 0 else DB_FLOOR
                if i >= SpectrumOverlay.BANDS - 4:
                    db += 6.0
                new_mags.append(max(0.0, min(1.0, (db - DB_FLOOR) / -DB_FLOOR)))
            else:
                new_mags.append(0.0)
        with self._overlay._lock:
            riseFactor = 0.5
            decayFactor = 0.9
            for i in range(SpectrumOverlay.BANDS):
                if new_mags[i] > self._overlay._mags[i]:
                    self._overlay._mags[i] += riseFactor * (new_mags[i] - self._overlay._mags[i])
                else:
                    self._overlay._mags[i] *= decayFactor
        self._overlay.update()
