/* Shelly settings */
		MbItemOptions {
			id: shellyPhase
			show: productId2.value == 0xFFE0
			description: qsTr("Phase")
			VBusItem {
				id: instance
				bind: Utils.path(root.bindPrefix, "/DeviceInstance")
			}
			VBusItem {
				id: productId2
				bind: Utils.path(root.bindPrefix, "/ProductId")
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
			show: productId2.value == 0xFFE0 && shellyMeterCount.value > 1 && shellyPhase.value < 4
			description: qsTr("Meter index")
			item {
				bind: Utils.path(root.bindPrefix, "/MeterIndex")
				decimals: 0
				step: 1
				max: 3
				min: 0
			}
		}

		MbEditBoxIp {
			show: productId2.value == 0xFFE0
			description: qsTr("IP address")
			item: VBusItem {
				id: shellyIpaddress
				isSetting: true
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/Url")
			}  
		}
		
		MbEditBox {
			show: productId2.value == 0xFFE0
			description: qsTr("User name")
			maximumLength: 35
			item: VBusItem {
				id: shellyUserName
				isSetting: true
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/Username")
			} 
		}
		
		MbEditBox {
			show: productId2.value == 0xFFE0
			description: qsTr("Password")
			maximumLength: 35
			item: VBusItem {
				id: shellyPassword
				isSetting: true
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/Password")
			} 
		}

		MbSpinBox {
			id: pollInterval
			show: productId2.value == 0xFFE0 
			description: qsTr("Polling interval")
			item {
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/PollInterval")
				unit: "s"
				step: 0.5
				decimals: 1
				max: 60
				min: 0.5
			}
		}

		MbSpinBox {
			id: evChargeThreshold
			show: productId2.value == 0xFFE0 && role.value === "evcharger"
			description: qsTr("Charging threshold")
			item {
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/EvChargeThreshold")
				unit: "W"
				step: 1
				decimals: 0
				max: 100
				min: 1
			}
		}
		
		MbSpinBox {
			id: evDisconnectThreshold
			show: productId2.value == 0xFFE0 && role.value === "evcharger"
			description: qsTr("Disconnect threshold")
			item {
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/EvDisconnectThreshold")
				unit: "W"
				step: 0.1
				decimals: 1
				max: 10
				min: 0
			}
		}

		MbSpinBox {
			id: shellyEvAutoMinSOC
			show: productId2.value == 0xFFE0 && role.value === "evcharger"
			description: qsTr("Auto mode minimum SOC")
			item {
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/EvAutoMinSOC")
				unit: "%"
				step: 1
				decimals: 0
				max: 100
				min: 1
			}
		}

		MbSpinBox {
			id: shellyEvAutoMinExcess
			show: productId2.value == 0xFFE0 && role.value === "evcharger"
			description: qsTr("Auto mode start on minimum excess")
			item {
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/EvAutoMinExcess")
				unit: "W"
				step: 10
				decimals: 0
				max: 2000
				min: 50
			}
		}

		MbSwitch {
			id: shellyEvAutoMpptThrottling
			show: productId2.value == 0xFFE0 && role.value === "evcharger"
			bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/EvAutoMpptThrottling") 
			name: qsTr("Auto mode start with MPPT throttling")
		}

		MbSpinBox {
			id: shellyEvAutoMinChargeTime
			show: productId2.value == 0xFFE0 && role.value === "evcharger"
			description: qsTr("Auto mode minimum charging time")
			item {
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/EvAutoMinChargeTime")
				unit: "min"
				step: 5
				decimals: 0
				max: 300
				min: 0
			}
		}

		MbSpinBox {
			id: shellyEvAutoOnTimeout
			show: productId2.value == 0xFFE0 && role.value === "evcharger"
			description: qsTr("Auto mode On timeout")
			item {
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/EvAutoOnTimeout")
				unit: "min"
				step: 0.5
				decimals: 1
				max: 15
				min: 0.5
			}
		}

		MbSpinBox {
			id: shellyEvAutoOffTimeout
			show: productId2.value == 0xFFE0 && role.value === "evcharger"
			description: qsTr("Auto mode Off timeout")
			item {
				bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/EvAutoOffTimeout")
				unit: "min"
				step: 0.5
				decimals: 1
				max: 15
				min: 0.5
			}
		}

		MbSwitch {
			id: shellyTemperatureSensor
			show: productId2.value == 0xFFE0
			bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/TemperatureSensor") 
			name: qsTr("Show temperature")
		}

		MbSwitch {
			id: shellyReverse
			VBusItem {
				id: shellyRetEnergy
				bind: Utils.path(root.bindPrefix, "/Ac/Energy/Reverse")
			}
			show: productId2.value == 0xFFE0 && shellyRetEnergy.value != null 
			bind: Utils.path("com.victronenergy.settings/Settings/Shelly/", instance.value, "/Reverse") 
			name: qsTr("Reverse flow")
		}
/* Shelly settings end */
