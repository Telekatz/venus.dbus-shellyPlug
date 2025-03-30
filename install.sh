#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SERVICE_NAME=$(basename $SCRIPT_DIR)
GUI_DIR=/opt/victronenergy/gui/qml

# set permissions for script files
chmod a+x $SCRIPT_DIR/restart.sh
chmod 744 $SCRIPT_DIR/restart.sh

chmod a+x $SCRIPT_DIR/uninstall.sh
chmod 744 $SCRIPT_DIR/uninstall.sh

chmod a+x $SCRIPT_DIR/restoreGUI.sh
chmod 744 $SCRIPT_DIR/restoreGUI.sh

chmod a+x $SCRIPT_DIR/service/run
chmod 755 $SCRIPT_DIR/service/run

# create sym-link to run script in deamon
if ! [ -e /service/$SERVICE_NAME ]
then
    ln -s $SCRIPT_DIR/service /service/$SERVICE_NAME 
fi

# add install-script to rc.local to be ready for firmware update
filename=/data/rc.local
if [ ! -f $filename ]
then
    touch $filename
    chmod 755 $filename
    echo "#!/bin/bash" >> $filename
    echo >> $filename
fi

grep -qxF "$SCRIPT_DIR/install.sh" $filename || echo "$SCRIPT_DIR/install.sh" >> $filename

# Restore GUI from old installation
file=/opt/victronenergy/gui/qml/PageAcInSetup.qml
TAB=`echo -e "\t\t"`
if grep -q "$TAB\/\* Shelly settings \*\/"  $file; then
  if [ -e $GUI_DIR/PageAcInSetup._qml ]
    then
        echo "Restore PageAcInSetup.qml"
        cp $GUI_DIR/PageAcInSetup._qml $GUI_DIR/PageAcInSetup.qml
    fi
fi

# Backup GUI
if ! [ -e $GUI_DIR/PageAcInSetup._qml ]
then
    cp $GUI_DIR/PageAcInSetup.qml $GUI_DIR/PageAcInSetup._qml 
fi
if ! [ -e $GUI_DIR/PageAcInModel._qml ]
then
    cp $GUI_DIR/PageAcInModel.qml $GUI_DIR/PageAcInModel._qml 
fi

# Patch GUI
patch=$SCRIPT_DIR/qml/PageAcInSetup_patch.qml
file=$GUI_DIR/PageAcInSetup.qml
if [ "$(cat $patch)" != "$(sed -n '/\/\* Shelly settings \*\//,/\/\* Shelly settings end \*\//p' $file )" ]; then
    sed -i '/\/\* Shelly settings \*\//,/\/\* Shelly settings end \*\//d'  $file
    line_number=$(grep -n "\/\* EM24 settings \*\/" $file | cut -d ":" -f 1)
    if ! [ -z "$line_number" ]; then
      line_number=$((line_number - 1))r
      echo "patching file $file"
      sed -i "$line_number $patch" $file
      svc -t /service/gui
    else
      echo "Error patching file $file" 
    fi
fi
patch=$SCRIPT_DIR/qml/PageAcInModel_patch.qml
file=$GUI_DIR/PageAcInModel.qml
if [ "$(cat $patch)" != "$(sed -n '/\/\* Shelly function \*\//,/\/\* Shelly function end \*\//p' $file )" ]; then
    sed -i '/\/\* Shelly function \*\//,/\/\* Shelly function end \*\//d'  $file
    line_number=$(grep -n "description: qsTr(\"AC Phase L1\")" $file | cut -d ":" -f 1)
    if ! [ -z "$line_number" ]; then
      line_number=$((line_number - 2))r
      echo "patching file $file"
      sed -i "$line_number $patch" $file
      svc -t /service/gui
    else
      echo "Error patching file $file" 
    fi
fi
