/* Shelly function */
	MbSwitch {
		name: qsTr("Output")
		bind: service.path("/SwitchableOutput/0/State")
		show: item.valid
	}
/* Shelly function end */	