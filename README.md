# EasyPlayer
Version 1.1.0

![Download](https://github.com/kanehekili/EasyPlayer/releases/download/1.1.0/easyplayer1.1.0.tar)

A simple video and audio player based on mpv and QT6 . It is a spin off of my VideoCut app. It handles pictures, plays videos and audio files.

![Screenshot](https://github.com/kanehekili/EasyPlayer/blob/main/easyplayer.png)

### Prerequisites
* Arch: python3, python-pillow and mpv
* Debian/Mint/Ubuntu: python3 python3-pil libmpv2 (or libmpv1) (no-recommends) 
* Ubuntu 26.04 needs additionally qt6-svg-plugins
  #not working for Ubuntu 18.4: libmpv - use python3-opencv instead
* Fedora: python3-pillow-qt and mpv-libs.x86_64
* ffmpeg > 3.X to 8.X
* python3-pyqt6

#### Set GTK Theme for this QT application
If you are running a DE with GTK/Gnome (as opposed to LXQT or KDE)  you might set QT_QPA_PLATFORMTHEME:
* Depending on the distro and version this variable may be defined with one of:
* gtk2, qt6ct, fusion, gtk3
* VideoCut will enforce "QT_QPA_PLATFORM=xcb" on Wayland for SSD decorations.
* On Ubuntu 26.04 you need to install qt6-gtk-platformtheme. This will get your GTK theme into any QT6 app. 
* On Ubuntu(with libadwaita) use /etc/environment to add GTK_THEME=yourTheme to enforce a third party theme. (Hack)

### Features
* Easyplayer supports wayland and orientation recognition (which mplayer does not). 
* Has been tested with interlaced video and 4K 
* Subtitles can be shown (settings)
* Flat and non flat icon set
* Language can be selected
* Supports an EQ-display for audio files - Some distros need to install python3-sounddevice via pip. (Not mandatory) 

### Virtualenv or conda 
The fast remux binary doesn't run in a virtual environment, since the ffmpeg libraries used are not available. The ffmpeg blob could be used, if it would be on the /usr/bin path on the host system. Cross OS binary calls tend be a lot slower that in the native environment - so this software is limited to Linux (native or virtualized)

### Support for Qemu:
-v will use a virtual GL driver for rendering. (easyplayer -v)


##Install

#### Install via ppa on Linux Mint or Ubuntu (Mint 22.2, Ubuntu 22.04 and newer versions)
```
sudo add-apt-repository ppa:jentiger-moratai/mediatools
sudo apt update
sudo apt install --no-install-recommends easyplayer
```
(--no-install-recommends will install only what is required)
Select video and open it with "Open with ->EasyPlayer", oder via terminal "easyplayer"

Remove with:
`sudo apt remove videocut`

#### Install VideoCut via AUR (Arch Linux /Manjaro only)
* Use pamac or other GUI tools, search for "easyplayer" in AUR, click install
* Manually :
    * Download [PKGBUILD ](https://aur.archlinux.org/cgit/aur.git/snapshot/easyplayer.tar.gz)
    * unpack it and go into the "easyplayer" folder
    * execute `makepkg -s`
    * excute `sudo pacman -U easyplayer-1.x.x.x-1-x86_64.pkg.tar.zst` 
    * uninstall via `sudo pacman -Rs easyplayer`

Select video and open it with "Open with ->EasyPlayer", oder via terminal "easyplayer"


#### Install dependencies manually on Linux Mint or Ubuntu (tested from 20.04 to 22.04)
```
sudo apt –no-install-recommends install python3-pyqt6 ffmpeg python3-pil libmpv2
```

#### Install dependencies on Fedora
```
sudo dnf python3-qt6 ffmpeg python3-pillow-qt mpv-libs.x86_64
```

### How to install with a terminal
* Install dependencies (see prerequisites)
* Download the easyplayer*.tar from the download link (see above)
* Extract it to a location that suits you.
* Open a terminal to execute the install.sh file inside the folder with sudo like `sudo ./install.sh`
* (if you are in the download directory - just an example)
* The app will be installed in /opt/easyplayer with a link to /usr/bin. 
* The app should be appear in a menu or "Actvities"
* Can be openend by selecting a video file & Open with...
* In the terminal can be started via `easyplayer`
* python qt6, mpv and ffmpeg are required
* you may now remove that download directory.
* logs can be found in the user home ".config/EasyPlayer" folder

### How to remove
* Open a terminal
* execute `sudo /opt/easyplayer/uninstall.sh`

### Changes 
12.03.2026
* Graphic EQ display for audio files 

09.03.2026
* Support for playlists and streams

05.03.2026
* Hardened interlacing recognition, fixed interprocess communication

26..12.2025
* Initial start

