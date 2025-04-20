#!/usr/bin/env python

# import normal packages
import platform
import logging
import sys
import os
import sys
if sys.version_info.major == 2:
    import gobject
else:
    from gi.repository import GLib as gobject
import sys
import json
import time
import configparser # for config/ini file
import paho.mqtt.client as mqtt
import requests # for http GET
from requests.auth import HTTPDigestAuth
import datetime

try:
  import thread   # for daemon = True  / Python 2.x
except:
  import _thread as thread   # for daemon = True  / Python 3.x
import dbus

# our own packages from victron
sys.path.insert(1, os.path.join(os.path.dirname(__file__), '/opt/victronenergy/dbus-systemcalc-py/ext/velib_python'))
from vedbus import VeDbusService
from settingsdevice import SettingsDevice
from dbusmonitor import DbusMonitor


#formatting
_kwh = lambda p, v: (str(round(v, 2)) + 'KWh')
_a = lambda p, v: (str(round(v, 1)) + 'A')
_w = lambda p, v: (str(round(v, 1)) + 'W')
_v = lambda p, v: (str(round(v, 1)) + 'V')
_hz = lambda p, v: (str(round(v, 1)) + 'Hz')
_pct = lambda p, v: (str(round(v, 1)) + '%')
_c = lambda p, v: (str(round(v, 1)) + '°C')


class SystemBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SYSTEM)


class SessionBus(dbus.bus.BusConnection):
    def __new__(cls):
        return dbus.bus.BusConnection.__new__(cls, dbus.bus.BusConnection.TYPE_SESSION)


def dbusconnection():
    return SessionBus() if 'DBUS_SESSION_BUS_ADDRESS' in os.environ else SystemBus()


def new_service(base, type, physical, logical, id, instance):
    if instance == 0:
      self = VeDbusService("{}.{}".format(base, type), dbusconnection(), register=False)
    else:
      self = VeDbusService("{}.{}.{}_id{:02d}".format(base, type, physical, id), dbusconnection(), register=False)
    # physical is the physical connection
    # logical is the logical connection to align with the numbering of the console display
    # Create the management objects, as specified in the ccgx dbus-api document
    self.add_path('/Mgmt/ProcessName', __file__)
    self.add_path('/Mgmt/ProcessVersion', 'Unkown version, and running on Python ' + platform.python_version())
    self.add_path('/Mgmt/Connection', logical)

    # Create the mandatory objects, note these may need to be customised after object creation
    self.add_path('/DeviceInstance', instance)
    self.add_path('/ProductId', 0)
    self.add_path('/ProductName', '')
    self.add_path('/FirmwareVersion', '')
    self.add_path('/HardwareVersion', '')
    self.add_path('/Connected', 0)  # Mark devices as disconnected until they are confirmed
    self.add_path('/Serial', '0')

    return self


def getConfig():
    config = configparser.ConfigParser()
    config.read("%s/config.ini" % (os.path.dirname(os.path.realpath(__file__))))
    return config;


class DbusShellyService:
  def __init__(self, deviceinstance, loop):

    self.settings = None
    self._connected = False
    self._loop = loop
    self._dbus = dbusconnection()
    self._deviceinstance = deviceinstance
    self._shellyGen = 0
    self._stateCounterA = 0
    self._chargeStartTime = 0
    self._chargeStartEnergy = 0
    self._init_device_settings(deviceinstance)
    base = 'com.victronenergy'
    self._dbusservice = {}
    self._shellyLoopTimer = None

    # Create power meter
    self._dbusservice['shelly'] = new_service(base, self.settings['/Role'], 'http', 'http', deviceinstance, deviceinstance)
    if self.settings['/TemperatureSensor'] == 1:
      self._dbusservice['shellyTemperature'] = new_service(base, 'temperature', 'http', 'http', deviceinstance, deviceinstance)
      self._initTemperature()
    else: 
       self._dbusservice['shellyTemperature'] = None

    # Init the power meter
    self._initPowerMeter()
    
    #Check if settings for Shelly are valid
    self._checkShelly()

    # add _shellyLoop function 'timer'
    self._shellyLoopTimer = gobject.timeout_add(self.settings['/PollInterval'] * 1000, self._shellyLoop)
 
    # add _checkConnection function 'timer'
    gobject.timeout_add(60000, self._checkConnection)
    

  def _initPowerMeter(self):
    
    # add path values to dbus
    self._dbusservice['shelly'].add_path('/CustomName', self.get_customname(), writeable=True, onchangecallback=self.customname_changed)
    self._dbusservice['shelly'].add_path('/MeterIndex', self.settings['/MeterIndex'], onchangecallback=self._handleChangedValue, writeable=True)

    self._dbusservice['shelly'].add_path('/AllowedRoles', ['grid', 'pvinverter', 'genset', 'acload', 'evcharger'])
    self._dbusservice['shelly'].add_path('/Role', self.settings['/Role'], onchangecallback=self._roleChanged,  writeable=True)

    paths = {
      '/Ac/Energy/Forward':                 {'initial': None,     'textformat': _kwh},
      '/Ac/Energy/Reverse':                 {'initial': None,     'textformat': _kwh},
      '/Ac/Power':                          {'initial': 0,        'textformat': _w},
      '/Ac/Current':                        {'initial': 0,        'textformat': _a},

      '/Ac/L1/Current':                     {'initial': 0,        'textformat': _a},
      '/Ac/L1/Energy/Forward':              {'initial': None,     'textformat': _kwh},
      '/Ac/L1/Energy/Reverse':              {'initial': None,     'textformat': _kwh},
      '/Ac/L1/Power':                       {'initial': 0,        'textformat': _w},
      '/Ac/L1/Voltage':                     {'initial': 0,        'textformat': _v},
      
      '/Ac/L2/Current':                     {'initial': 0,        'textformat': _a},
      '/Ac/L2/Energy/Forward':              {'initial': None,     'textformat': _kwh},
      '/Ac/L2/Energy/Reverse':              {'initial': None,     'textformat': _kwh},
      '/Ac/L2/Power':                       {'initial': 0,        'textformat': _w},
      '/Ac/L2/Voltage':                     {'initial': 0,        'textformat': _v},

      '/Ac/L3/Current':                     {'initial': 0,        'textformat': _a},
      '/Ac/L3/Energy/Forward':              {'initial': None,     'textformat': _kwh},
      '/Ac/L3/Energy/Reverse':              {'initial': None,     'textformat': _kwh},
      '/Ac/L3/Power':                       {'initial': 0,        'textformat': _w},
      '/Ac/L3/Voltage':                     {'initial': 0,        'textformat': _v},
      
      '/DeviceType':                        {'initial': 0,        'textformat': None},
      '/ErrorCode':                         {'initial': 0,        'textformat': None},
      '/DeviceName':                        {'initial': '',       'textformat': None},
      '/MeterCount':                        {'initial': 0,        'textformat': None},
      
    }

    pathsEvCharger = {
      '/Model':                             {'initial': '',       'textformat': None},
      '/MaxCurrent':                        {'initial': 0,        'textformat': _a},
      '/Mode':                              {'initial': 0,        'textformat': None},
      '/ChargingTime':                      {'initial': 0,        'textformat': None},
      '/Current':                           {'initial': 0,        'textformat': _a},
      '/Status':                            {'initial': 0,        'textformat': None},
      '/SetCurrent':                        {'initial': 0,        'textformat': _a},
      '/StartStop':                         {'initial': 0,        'textformat': None},
      '/AutoStart':                         {'initial': 0,        'textformat': None},
      '/Ac/Energy/ForwardTotal':            {'initial': None,     'textformat': _kwh},
      '/Relay':                             {'initial': 0,        'textformat': None},
    }

    # add path values to dbus
    for path, settings in paths.items():
      self._dbusservice['shelly'].add_path(
        path, settings['initial'], gettextcallback=settings['textformat'], onchangecallback=self._handleChangedValue, writeable=True)

    # add path values to dbus
    if self.settings['/Role'] in ['evcharger']:
      for path, settings in pathsEvCharger.items():
        self._dbusservice['shelly'].add_path(
          path, settings['initial'], gettextcallback=settings['textformat'], onchangecallback=self._handleChangedValue, writeable=True)
      
    # Position for pvinverter
    if self.settings['/Role'] in ['pvinverter', 'evcharger']:
      self._dbusservice['shelly'].add_path('/Position', self.settings['/Position'], onchangecallback=self._handleChangedValue, writeable=True)

    self._dbusservice['shelly']['/ProductId'] = 0xFFE0
    self._dbusservice['shelly']['/ProductName'] = 'Shelly'

    self._dbusservice['shelly'].register()


  def _initPowerMeterSwitchableOutput(self):

    pathsSwitchableOutput = {
      
      '/SwitchableOutput/0/State':                    {'initial':0,         'textformat': None},
      '/SwitchableOutput/0/Name':                     {'initial':'Relay',   'textformat': None},
      '/SwitchableOutput/0/Status':                   {'initial':0,         'textformat': None},
      '/SwitchableOutput/0/Temperature':              {'initial':0,         'textformat': None},
      #'/SwitchableOutput/0/Voltage':                  {'initial':0,         'textformat': None},
      #'/SwitchableOutput/0/Current':                  {'initial':0,         'textformat': None},

      '/SwitchableOutput/0/Settings/Group':           {'initial':None,      'textformat': None},
      '/SwitchableOutput/0/Settings/CustomName':      {'initial':'Relay',   'textformat': None},
      '/SwitchableOutput/0/Settings/ShowUIControl':   {'initial':1,         'textformat': None},
      '/SwitchableOutput/0/Settings/Type':            {'initial':1,         'textformat': None},
      '/SwitchableOutput/0/Settings/ValidTypes':      {'initial':2,         'textformat': None},
      '/SwitchableOutput/0/Settings/Function':        {'initial':2,         'textformat': None},
      '/SwitchableOutput/0/Settings/ValidFunctions':  {'initial':4,         'textformat': None},

    }

    # add path values to dbus
    for path, settings in pathsSwitchableOutput.items():
      self._dbusservice['shelly'].add_path(
        path, settings['initial'], gettextcallback=settings['textformat'], onchangecallback=self._handleChangedValue, writeable=True)
      

  def _initTemperature(self):
    
    # add path values to dbus
    self._dbusservice['shellyTemperature'].add_path('/CustomName', self.get_customname(), writeable=True, onchangecallback=self.customname_changed)
    
    paths = {
      '/Temperature':                       {'initial': None,     'textformat': _c},
      '/Humidity':                          {'initial': None,     'textformat': _pct},
      '/TemperatureType':                   {'initial': 2,        'textformat': None},
    }

    # add path values to dbus
    for path, settings in paths.items():
      self._dbusservice['shellyTemperature'].add_path(
        path, settings['initial'], gettextcallback=settings['textformat'], onchangecallback=self._handleChangedValue, writeable=True)

    self._dbusservice['shellyTemperature']['/ProductId'] = 0xFFE0
    self._dbusservice['shellyTemperature']['/ProductName'] = 'Shelly Temperature'

    self._dbusservice['shellyTemperature'].register()
    

  def _roleChanged(self, path, value):
    if value not in ['grid', 'pvinverter', 'genset', 'acload', 'evcharger']:
      return False

    self.settings['/Role'] = value

    self.destroy()

    return True # accept the change


  def _handleChangedValue(self, path, value):
    if path == '/Position':
      self.settings['/Position'] = value
      return True # accept the change
    
    if path == '/MeterIndex':
      if value < self._dbusservice['shelly']['/MeterCount']:
        self.settings['/MeterIndex'] = value
        return True # accept the change
      else:
        return False
    
    if path in ('/Mode', '/AutoStart', '/SetCurrent', '/MaxCurrent' ):
      return False
    
    if path == '/SwitchableOutput/0/State':
      if not '/SwitchableOutput/0/State' in self._dbusservice['shelly']:
        return False
      else:
        self._setShellySwitch(value, self._dbusservice['shelly']['/MeterIndex'])
        return True
      
    return True # accept the change


  def destroy(self):
    self._dbusservice['shelly'].__del__()
    self._loop.quit()


  def _init_device_settings(self, deviceinstance):
    if self.settings:
        return

    path = '/Settings/Shelly/{}'.format(deviceinstance)

    SETTINGS = {
        '/Customname':                    [path + '/CustomName', 'Shelly', 0, 0],
        '/Phase':                         [path + '/Phase', 1, 1, 6],
        '/Url':                           [path + '/Url', '192.168.1.1', 0, 0],
        '/User':                          [path + '/Username', '', 0, 0],
        '/Pwd':                           [path + '/Password', '', 0, 0],
        '/Role':                          [path + '/Role', 'acload', 0, 0],
        '/Position':                      [path + '/Position', 0, 0, 2],
        '/MeterIndex':                    [path + '/MeterIndex', 0, 0, 3],
        '/TemperatureSensor':             [path + '/TemperatureSensor', 0, 0, 1],
        '/Reverse':                       [path + '/Reverse', 0, 0, 1],
        '/EvChargeThreshold':             [path + '/EvChargeThreshold', 5, 1, 100],
        '/EvDisconnectThreshold':         [path + '/EvDisconnectThreshold', 0.5, 0, 10],
        '/PollInterval':                  [path + '/PollInterval', 1.0, 0.5, 60],
    }

    self.settings = SettingsDevice(self._dbus, SETTINGS, self._setting_changed)


  def _setting_changed(self, setting, oldvalue, newvalue):
    logging.info("Setting changed, setting: %s, old: %s, new: %s" % (setting, oldvalue, newvalue))

    if setting == '/Customname':
      self._dbusservice['shelly']['/CustomName'] = newvalue
      self._dbusservice['shellyTemperature']['/CustomName'] = newvalue
      return

    if setting in ['/Url', '/User', '/Pwd']:
      self._checkShelly()

    if setting == '/Role':
      self.destroy()

    if setting == '/TemperatureSensor':
      if self.settings['/TemperatureSensor'] == 1:
        self._dbusservice['shellyTemperature'] = new_service('com.victronenergy', 'temperature', 'http', 'http', self._deviceinstance, self._deviceinstance)
        self._initTemperature()
      else: 
       self.destroy()
    if setting == '/PollInterval' and newvalue >= 0.5:
      gobject.source_remove(self._shellyLoopTimer)
      self._shellyLoopTimer = gobject.timeout_add(newvalue * 1000, self._shellyLoop)

  def get_customname(self):
    return self.settings['/Customname']


  def customname_changed(self, path, val):
    self.settings['/Customname'] = val
    return True


  def _shellyLoop(self):
    self._shellyUpdate()

    if self.settings['/Role'] == 'evcharger':
      self._evUpdate()

    return True


  def _shellyUpdate(self):
    try:
      
      shellyData = None

      if self._connected == True:
        if self._shellyGen >= 2:
          shellyData = self._getShellyJson('rpc/Shelly.GetStatus')
        else:
          shellyData = self._getShellyJson('status')

        if shellyData is None:
          logging.info("Shelly_ID%i connection lost", self._deviceinstance)
          self._dbusservice['shelly']['/Connected'] = 0
          if self._dbusservice['shellyTemperature'] is not None:
            self._dbusservice['shellyTemperature']['/Connected'] = 0
            self._dbusservice['shellyTemperature']['/Temperature'] = None
          self._connected = False
          self._shellyGen = 0

        sumPowerAC = sumCurrentAC = sumEnergy = 0
        sumEnergyReverse = None
        temperature = None
        humidity = None
        relay = None

        #send data to DBus
        for phase in [1, 2, 3]:
          pre = '/Ac/L%s' % phase

          if phase == self.settings['/Phase']:
            meterIndex = min(self._dbusservice['shelly']['/MeterCount'] - 1, self._dbusservice['shelly']['/MeterIndex'])
            powerAC, voltageAC, currentAC, energy, energyReverse, temperature_, humidity_, relay_ = self._getMeterData(shellyData, meterIndex)
          elif self.settings['/Phase'] > 3:
            powerAC, voltageAC, currentAC, energy, energyReverse, temperature_, humidity_, relay_ = self._getMeterData(shellyData, (phase - self.settings['/Phase']) % 3)
          else:
            temperature_ = None
            humidity_ = None
            energyReverse = None
            relay_ = None
            powerAC = voltageAC = currentAC = energy = None if shellyData is None else 0

          if temperature_ is not None:
            temperature = temperature_

          if humidity_ is not None:
            humidity = humidity_

          if relay_ is not None:
            relay = relay_

          self._dbusservice['shelly'][pre + '/Voltage'] = voltageAC
          self._dbusservice['shelly'][pre + '/Current'] = currentAC
          self._dbusservice['shelly'][pre + '/Power'] = powerAC
          self._dbusservice['shelly'][pre + '/Energy/Forward'] = energy
          self._dbusservice['shelly'][pre + '/Energy/Reverse'] = energyReverse
          sumPowerAC += powerAC or 0
          sumCurrentAC += currentAC or 0
          sumEnergy += energy or 0
          if energyReverse is not None:
            if sumEnergyReverse is None:
              sumEnergyReverse = energyReverse
            else:
              sumEnergyReverse += energyReverse

        if self.settings['/Role'] == 'evcharger':
          self._dbusservice['shelly']['/Ac/Energy/ForwardTotal'] = None if shellyData is None else sumEnergy
          self._dbusservice['shelly']['/Current'] = None if shellyData is None else sumCurrentAC
        else:
          self._dbusservice['shelly']['/Ac/Energy/Forward'] = None if shellyData is None else sumEnergy

        self._dbusservice['shelly']['/Ac/Power'] = None if shellyData is None else sumPowerAC
        self._dbusservice['shelly']['/Ac/Current'] = None if shellyData is None else sumCurrentAC
        self._dbusservice['shelly']['/Ac/Energy/Reverse'] = None if shellyData is None else sumEnergyReverse
        if '/SwitchableOutput/0/State' in self._dbusservice['shelly']:
          self._dbusservice['shelly']['/SwitchableOutput/0/State'] = relay
          self._dbusservice['shelly']['/SwitchableOutput/0/Status'] = relay * 0x09
          self._dbusservice['shelly']['/SwitchableOutput/0/Temperature'] = temperature

        if '/Relay' in self._dbusservice['shelly']:
          self._dbusservice['shelly']['/Relay'] = relay
        if self._dbusservice['shellyTemperature'] is not None:
          self._dbusservice['shellyTemperature']['/Temperature'] = temperature
          self._dbusservice['shellyTemperature']['/Humidity'] = humidity

    except Exception as e:
      logging.critical('Error at %s', '_shellyUpdate', exc_info=e)

    return True


  def _evUpdate(self):
    try:

      if self._connected == True:

        # Disconnected
        if self._dbusservice['shelly']['/Status'] == 0:
          
          # Disconnected -> Connected
          if self._dbusservice['shelly']['/StartStop'] == 1 or self._dbusservice['shelly']['/Relay'] == 1:
            self._setShellySwitch(1, self._dbusservice['shelly']['/MeterIndex'])
            self._dbusservice['shelly']['/Status'] = 1
            self._dbusservice['shelly']['/StartStop'] = 1
            self._stateCounterA = 0

        # Connected
        elif self._dbusservice['shelly']['/Status'] == 1:
          self._stateCounterA += 1 if self._dbusservice['shelly']['/Ac/Power'] > self.settings['/EvChargeThreshold'] else 0

          # Connected -> Charging
          if self._stateCounterA > 5:
            self._chargeStartTime = datetime.datetime.now()
            self._chargeStartEnergy = self._dbusservice['shelly']['/Ac/Energy/ForwardTotal']
            self._dbusservice['shelly']['/Status'] = 2
            self._stateCounterA = 0

          # Connected -> Disconnected
          if self._dbusservice['shelly']['/StartStop'] == 0 or self._dbusservice['shelly']['/Relay'] == 0:
            self._dbusservice['shelly']['/StartStop'] = 0
            self._setShellySwitch(0, self._dbusservice['shelly']['/MeterIndex'])
            self._dbusservice['shelly']['/Status'] = 0

        # Charging
        elif self._dbusservice['shelly']['/Status'] == 2:
          self._stateCounterA += 1 if self._dbusservice['shelly']['/Ac/Power'] < self.settings['/EvChargeThreshold'] else 0
          self._dbusservice['shelly']['/ChargingTime'] = (datetime.datetime.now() - self._chargeStartTime).seconds
          self._dbusservice['shelly']['/Ac/Energy/Forward'] = self._dbusservice['shelly']['/Ac/Energy/ForwardTotal'] - self._chargeStartEnergy

          # Charging -> Charged
          if self._stateCounterA > 10:
            self._dbusservice['shelly']['/Status'] = 3
            self._stateCounterA = 0

          # Charging -> Disconnected
          if self._dbusservice['shelly']['/StartStop'] == 0 or self._dbusservice['shelly']['/Relay'] == 0:
            self._dbusservice['shelly']['/StartStop'] = 0
            self._setShellySwitch(0, self._dbusservice['shelly']['/MeterIndex'])
            self._dbusservice['shelly']['/Status'] = 0

        # Charged
        elif self._dbusservice['shelly']['/Status'] == 3:
          self._stateCounterA += 1 if self._dbusservice['shelly']['/Ac/Power'] <= self.settings['/EvDisconnectThreshold'] else  0

          # Charged -> Disconected
          if self._stateCounterA > 10 or self._dbusservice['shelly']['/StartStop'] == 0 or self._dbusservice['shelly']['/Relay'] == 0:
            self._dbusservice['shelly']['/StartStop'] = 0
            self._setShellySwitch(0, self._dbusservice['shelly']['/MeterIndex'])
            self._dbusservice['shelly']['/Status'] = 0
            self._dbusservice['shelly']['/StartStop'] = 0

    except Exception as e:
      logging.critical('Error at %s', '_evUpdate', exc_info=e)


  def _getMeterData(self, shellyData, meterIndex):
    powerAC = None
    voltageAC = None
    currentAC = None
    energy = None
    energyReverse = None
    temperature = None
    humidity = None
    relay = None

    try:
      if shellyData is None:
        return powerAC, voltageAC, currentAC, energy, energyReverse, temperature, humidity, relay

      if self._shellyGen >= 2:
        if 'em1:0' in shellyData and 'em1data:0' in shellyData:
          channel = 'em1:%s' % meterIndex
          channelData = 'em1data:%s' % meterIndex
          if channel in shellyData and channelData in shellyData:
            powerAC = shellyData[channel]['act_power']
            voltageAC = shellyData[channel]['voltage']
            currentAC = shellyData[channel]['current']
            energy = shellyData[channelData]['total_act_energy']/1000
            energyReverse = shellyData[channelData]['total_act_ret_energy']/1000
          if 'switch:0' in shellyData:
            if 'temperature' in shellyData['switch:0']:
              temperature = shellyData['switch:0']['temperature']['tC']
        elif 'switch:0' in shellyData:
          channel = 'switch:%s' % meterIndex
          if channel in shellyData:
            powerAC = shellyData[channel]['apower']
            voltageAC = shellyData[channel]['voltage']
            currentAC = shellyData[channel]['current']
            energy = shellyData[channel]['aenergy']['total'] / 1000
            relay = 1 if shellyData[channel]['output'] == True else 0
            if 'ret_aenergy' in shellyData[channel]:
              energyReverse = shellyData[channel]['ret_aenergy']['total'] / 1000
            if 'temperature' in shellyData[channel]:
              temperature = shellyData[channel]['temperature']['tC']
        elif 'pm1:0' in shellyData:
          powerAC = shellyData['pm1:0']['apower']
          voltageAC = shellyData['pm1:0']['voltage']
          currentAC = shellyData['pm1:0']['current']
          energy = shellyData['pm1:0']['aenergy']['total'] / 1000
          energyReverse = shellyData['pm1:0']['ret_aenergy']['total'] / 1000
        elif 'em:0' in shellyData and 'emdata:0' in shellyData:
          channel = '%s_' % chr(ord('a') + meterIndex)
          powerAC = shellyData['em:0'][channel + 'act_power']
          voltageAC = shellyData['em:0'][channel + 'voltage']
          currentAC = shellyData['em:0'][channel + 'current']
          energy = shellyData['emdata:0'][channel + 'total_act_energy'] / 1000
          energyReverse = shellyData['emdata:0'][channel + 'total_act_ret_energy'] / 1000
        
        if 'temperature:100' in shellyData:
          temperature = shellyData['temperature:100']['tC']

        if 'humidity:100' in shellyData:
          humidity = shellyData['humidity:100']['rh']

      else:
        if 'meters' in shellyData:
          if meterIndex < len(shellyData['meters']):
            powerAC = shellyData['meters'][meterIndex]['power']
            voltageAC = 230
            currentAC = powerAC / 230
            if 'total' in shellyData['meters'][meterIndex]:
              energy = shellyData['meters'][meterIndex]['total'] / 60000
            else:
              energy = 0
            energyReverse = None
            if 'temperature' in shellyData:
              temperature = shellyData['temperature']
        elif 'emeters' in shellyData:
          if meterIndex < len(shellyData['emeters']):
            powerAC = shellyData['emeters'][meterIndex]['power']
            voltageAC = shellyData['emeters'][meterIndex]['voltage']
            if voltageAC > 1:
              currentAC = powerAC / voltageAC
            else:
              currentAC = 0
            energy = shellyData['emeters'][meterIndex]['total'] / 1000
            energyReverse = shellyData['emeters'][meterIndex]['total_returned'] / 1000
        if 'relays' in shellyData:
          if meterIndex < len(shellyData['relays']):
            relay = 1 if shellyData['relays'][meterIndex]['ison'] == True else 0

      if energyReverse is not None and self.settings['/Reverse'] == 1:
        energy, energyReverse, powerAC = energyReverse, energy, -powerAC

      return powerAC, voltageAC, currentAC, energy, energyReverse, temperature, humidity, relay

    except Exception as e:
      return None, None, None, None, None, None, None, None


  def _checkConnection(self):
    try:
      if self._connected == False:
        #Try to reconnect
        self._checkShelly()

    except Exception as e:
      logging.critical('Error at %s', '_checkConnection', exc_info=e)

    return True  


  def _getShellyJson(self, path):
    try:
      if self._shellyGen >= 2:
        URL = "http://%s/" % (self.settings['/Url']) + path
        meter_r = requests.get(url=URL, timeout=3, auth=HTTPDigestAuth(self.settings['/User'], self.settings['/Pwd']))
      else:
        URL = "http://%s:%s@%s/" % (self.settings['/User'], self.settings['/Pwd'], self.settings['/Url']) + path
        URL = URL.replace(":@", "")
        meter_r = requests.get(url=URL, timeout=3)

    except Exception as e:
      return None

    # check for response
    if not meter_r:
        return None

    if meter_r.status_code != 200:
      return None
        
    meter_data = meter_r.json()

    # check for Json
    if not meter_data:
        logging.info("Converting response to JSON failed")
        return None

    return meter_data


  def _checkShelly(self):
    try:
      shellyInfo = self._getShellyJson('shelly')
      
      if shellyInfo is not None:
        if 'gen' in shellyInfo:
          self._shellyGen = shellyInfo['gen']
        else:
          self._shellyGen = 1
        
        if self._shellyGen == 1:
          shellySettings = self._getShellyJson('settings')
          if shellySettings is None:
            return
          self._dbusservice['shelly']['/DeviceName'] = shellySettings['name']
          self._dbusservice['shelly']['/FirmwareVersion'] = shellySettings['fw']
          self._dbusservice['shelly']['/ProductName'] = shellySettings['device']['type']
          shellyStatus = self._getShellyJson('status')
          if shellyStatus is None:
            return
          elif 'meters' in shellyStatus: 
            meterCount = len(shellyStatus['meters'])
          elif 'emeters' in shellyStatus:
            meterCount = len(shellyStatus['emeters'])
          else:
            meterCount = 0
            
        elif self._shellyGen >= 2:
          shellySettings = self._getShellyJson('rpc/Shelly.GetDeviceInfo')
          if shellySettings is None:
            return
          self._dbusservice['shelly']['/DeviceName'] = shellySettings['name']
          self._dbusservice['shelly']['/FirmwareVersion'] = shellySettings['ver']
          self._dbusservice['shelly']['/ProductName'] = shellySettings['model']
          shellyStatus = self._getShellyJson('rpc/Shelly.GetStatus')
          if shellyStatus is None:
            return
          elif 'em1:0' in shellyStatus and 'em1data:0' in shellyStatus:
            if 'em1:1' in shellyStatus:
              meterCount = 2
            else:
              meterCount = 1
          elif 'switch:0' in shellyStatus:
            if not 'apower' in shellyStatus['switch:0']:
              return
            elif 'switch:3' in shellyStatus:
              meterCount = 4
            elif 'switch:2' in shellyStatus:
              meterCount = 3
            elif 'switch:1' in shellyStatus:
              meterCount = 2
            else:
              meterCount = 1
            if self.settings['/Role'] != 'evcharger':
              if not '/SwitchableOutput/0/State' in self._dbusservice['shelly']:
                self._initPowerMeterSwitchableOutput()
              self._dbusservice['shelly']['/SwitchableOutput/0/Name'] = shellySettings['name']
              self._dbusservice['shelly']['/SwitchableOutput/0/Settings/CustomName'] = shellySettings['name']
          elif 'pm1:0' in shellyStatus:
            meterCount = 1
          elif 'em:0' in shellyStatus and 'emdata:0' in shellyStatus:
            meterCount = 3
          else:
            meterCount = 0
        
        self._dbusservice['shelly']['/MeterCount'] = meterCount
        if meterCount == 0:
          return

        self._dbusservice['shelly']['/MeterIndex'] = min(meterCount - 1, self.settings['/MeterIndex'])

        self._dbusservice['shelly']['/Serial'] = shellyInfo['mac']
        self._dbusservice['shelly']['/HardwareVersion'] = self._shellyGen

        self._dbusservice['shelly']['/Connected'] = 1
        if self._dbusservice['shellyTemperature'] is not None:
            self._dbusservice['shellyTemperature']['/Connected'] = 1
        self._connected = True
        logging.info("Shelly_ID%i connected, %s ", self._deviceinstance, self._dbusservice['shelly']['/Serial'])

      return

    except Exception as e:
      logging.critical('Error at %s', '_checkShelly', exc_info=e)
      return

  def _setShellySwitch(self, state, meterIndex):
    try:
      if self._shellyGen >= 2:
        URL = "http://%s/rpc/Switch.Set?id=%s&on=%s" % (self.settings['/Url'], meterIndex, 'true' if state == 1 else 'false')
        meter_r = requests.get(url=URL, timeout=3, auth=HTTPDigestAuth(self.settings['/User'], self.settings['/Pwd']))
      else:
        URL = "http://%s:%s@%s/relay/%s?turn=%s" % (self.settings['/User'], self.settings['/Pwd'], self.settings['/Url'], meterIndex, 'on' if state == 1 else 'off')
        URL = URL.replace(":@", "")
        meter_r = requests.get(url=URL, timeout=3)

    except Exception as e:
      return None

    # check for response
    if not meter_r:
        return None

    if meter_r.status_code != 200:
      return None
        
    meter_data = meter_r.json()

    # check for Json
    if not meter_data:
        logging.info("Converting response to JSON failed")
        return None

    return meter_data
  

def main():
  #configure logging
  logging.basicConfig(      format = '%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                            datefmt = '%Y-%m-%d %H:%M:%S',
                            level = logging.INFO,
                            handlers = [
                                logging.FileHandler("%s/current.log" % (os.path.dirname(os.path.realpath(__file__)))),
                                logging.StreamHandler()
                            ])
  thread.daemon = True # allow the program to quit

  try:
      logging.info("Start")

      from dbus.mainloop.glib import DBusGMainLoop
      # Have a mainloop, so we can send/receive asynchronous calls to and from dbus
      DBusGMainLoop(set_as_default=True)

      

      logging.info('Connected to dbus, and switching over to gobject.MainLoop() (= event based)')
      mainloop = gobject.MainLoop()
      #start our main-service

      config = getConfig()

      for section in config.sections():
        if config.has_option(section, 'Deviceinstance') == True:
          DbusShellyService(int(config[section]['Deviceinstance']), mainloop)

      mainloop.run()

  except Exception as e:
    logging.critical('Error at %s', 'main', exc_info=e)


if __name__ == "__main__":
  main()
