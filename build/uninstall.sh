#!/bin/bash
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./uninstall.sh"
    exit 1
fi

rm -rf /opt/easyplayer
rm -f  /usr/bin/easyplayer
rm -f  /usr/share/applications/EasyPlayer.desktop

echo "EasyPlayer uninstalled."
