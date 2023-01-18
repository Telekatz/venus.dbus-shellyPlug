#!/bin/bash
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
SERVICE_NAME=$(basename $SCRIPT_DIR)

# set permissions for script files
chmod a+x $SCRIPT_DIR/restart.sh
chmod 744 $SCRIPT_DIR/restart.sh

chmod a+x $SCRIPT_DIR/uninstall.sh
chmod 744 $SCRIPT_DIR/uninstall.sh

chmod a+x $SCRIPT_DIR/service/run
chmod 755 $SCRIPT_DIR/service/run

# create sym-link to run script in deamon
ln -s $SCRIPT_DIR/service /service/$SERVICE_NAME

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

# update GUI
if ! [ -e /opt/victronenergy/gui/qml/PageAcInSetup._qml ]
then
    cp /opt/victronenergy/gui/qml/PageAcInSetup.qml /opt/victronenergy/gui/qml/PageAcInSetup._qml 
fi

if ! patch -p0 <$SCRIPT_DIR/qml/PageAcInSetup.diff > /dev/null 2> /dev/null;
then
    if [ -e /opt/victronenergy/gui/qml/PageAcInSetup._qml ]
    then
        echo "Restore PageAcInSetup.qml"
        cp /opt/victronenergy/gui/qml/PageAcInSetup._qml /opt/victronenergy/gui/qml/PageAcInSetup.qml
        patch -p0 <$SCRIPT_DIR/qml/PageAcInSetup.diff 
    fi
fi

svc -t /service/gui