#!/bin/bash
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./install.sh"
    exit 1
fi

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

install -d /opt/easyplayer
cp -r "$DIR"/*.py    /opt/easyplayer/
cp -r "$DIR"/icons   /opt/easyplayer/
cp -r "$DIR"/lib     /opt/easyplayer/
chmod 755 /opt/easyplayer/EasyPlayer.py

cp "$DIR"/EasyPlayer.desktop /usr/share/applications/

ln -sf /opt/easyplayer/EasyPlayer.py /usr/bin/easyplayer

echo "EasyPlayer installed."
echo "Required packages: python3-pyqt6 libmpv2 ffmpeg"
