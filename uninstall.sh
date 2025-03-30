#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SERVICE_NAME=$(basename $SCRIPT_DIR)

if  [ -e /service/$SERVICE_NAME ]
then
    rm /service/$SERVICE_NAME
    kill $(pgrep -f 'shellyPlug.py')
    chmod a-x $SCRIPT_DIR/service/run
    kill $(pgrep -f 'shellyPlug.py')  /dev/null 2> /dev/null
fi

# Clean the GUI
sed -i '/\/\* Shelly settings \*\//,/\/\* Shelly settings end \*\//d' /opt/victronenergy/gui/qml/PageAcInSetup.qml
sed -i '/\/\* Shelly function \*\//,/\/\* Shelly function end \*\//d' /opt/victronenergy/gui/qml/PageAcInModel.qml
svc -t /service/gui

# Remove install-script
grep -v "$SCRIPT_DIR/install.sh" /data/rc.local >> /data/temp.local
mv /data/temp.local /data/rc.local
chmod 755 /data/rc.local


