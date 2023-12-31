/* Shelly settings */
		MbItemOptions {
			id: shellyPhase
			show: productId == 0xFFE0
			description: qsTr("Phase")
			VBusItem {
				id: instance
				bind: Utils.path(root.bindPrefix, "/DeviceInstance")
			}
			VBusItem {
				id: shellyMeterCount
				bind: Utils.path(root.bindPrefix, "/MeterCount")
				onValueChanged: {
					var options = [];
					for (var i = 1; i < 4; i++) {
						var params = {
							"description": "L" + i,
							"value": i,
						}
						options.push(mbOptionFactory.createObject(root, params));
					}
					
					for (var i = 4; (i < 7) && value === 3; i++) {
						var params = {
							"description": "L" + ((i-1) % 3 + 1) + "/L" + ((i) % 3 + 1) +"/L" + ((i+1) % 3 + 1),
							"value": i,
						}
						options.push(mbOptionFactory.createObject(root, params));
					}
					if (value > 0) {shellyMeterIndex.item.max = value-1}
					shellyPhase.possibleValues = options;
				}
			}
			bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/Phase")
			readonly: false
			editable: true
		}

		MbSpinBox {
			id: shellyMeterIndex
			show: productId == 0xFFE0 && shellyMeterCount.value > 1 && shellyPhase.value < 4
			description: qsTr("Meter Index")
			item {
				bind: Utils.path(root.bindPrefix, "/MeterIndex")
				decimals: 0
				step: 1
				max: 3
				min: 0
			}
		}

		MbEditBoxIp {
			show: productId == 0xFFE0
			description: qsTr("IP Address")
			item: VBusItem {
				id: shellyIpaddress
				isSetting: true
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/Url")
			}  
		}
		
		MbEditBox {
			show: productId == 0xFFE0
			description: qsTr("User Name")
			maximumLength: 35
			item: VBusItem {
				id: shellyUserName
				isSetting: true
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/Username")
			} 
		}
		
		MbEditBox {
			show: productId == 0xFFE0
			description: qsTr("Password")
			maximumLength: 35
			item: VBusItem {
				id: shellyPassword
				isSetting: true
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/Password")
			} 
		}

		MbSwitch {
			id: shellyTemperatureSensor
			show: productId == 0xFFE0
			bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/TemperatureSensor") 
			name: qsTr("Show Temperature")
		}
/* Shelly settings end */
