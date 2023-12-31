#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SERVICE_NAME=$(basename $SCRIPT_DIR)
GUI_DIR=/opt/victronenergy/gui/qml

if [ -e $GUI_DIR/PageAcInSetup._qml ]
  then
      echo "Restore PageAcInSetup.qml"
      cp $GUI_DIR/PageAcInSetup._qml $GUI_DIR/PageAcInSetup.qml
      svc -t /service/gui
  fi
