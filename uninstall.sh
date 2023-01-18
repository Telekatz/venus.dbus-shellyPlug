#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SERVICE_NAME=$(basename $SCRIPT_DIR)

rm /service/$SERVICE_NAME
kill $(pgrep -f 'shellyPlug.py')
chmod a-x $SCRIPT_DIR/service/run
kill $(pgrep -f 'shellyPlug.py')  /dev/null 2> /dev/null

if ! patch -p0 -R <$SCRIPT_DIR/qml/PageAcInSetup.diff > /dev/null 2> /dev/null;
then
    if [ -e /opt/victronenergy/gui/qml/PageAcInSetup._qml ]
    then
        echo "Restore PageAcInSetup.qml"
        cp /opt/victronenergy/gui/qml/PageAcInSetup._qml /opt/victronenergy/gui/qml/PageAcInSetup.qml
    fi
fi

svc -t /service/gui

