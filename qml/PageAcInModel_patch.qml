/* Shelly function */
	MbSwitch {
		name: qsTr("Output")
		bind: service.path("/Relay")
		show: item.valid
	}
/* Shelly function end */	