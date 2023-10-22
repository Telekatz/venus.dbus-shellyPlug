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
      self =  VeDbusService("{}.{}".format(base, type), dbusconnection())
    else:
      self =  VeDbusService("{}.{}.{}_id{:02d}".format(base, type, physical,  id), dbusconnection())
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
  def __init__(self, deviceinstance, interval, loop):

    self.settings = None
    self._connected = False
    self._loop = loop
    self._dbus = dbusconnection()
    self._deviceinstance = deviceinstance
    self._shellyGen = 0

    self._init_device_settings(deviceinstance)
    base = 'com.victronenergy'
    self._dbusservice = {}

    # Create power meter
    self._dbusservice['shelly'] = new_service(base, self.settings['/Role'], 'http', 'http', deviceinstance, deviceinstance)

    # Init the power meter
    self._initPowerMeter()

    #Check if settings for Shelly are valid
    self._checkShelly()

    # add _shellyLoop function 'timer'
    gobject.timeout_add(interval, self._shellyUpdate)
 
    # add _checkConnection function 'timer'
    gobject.timeout_add(60000, self._checkConnection)
    

  def _initPowerMeter(self):
    
    # add path values to dbus
    self._dbusservice['shelly'].add_path('/CustomName', self.get_customname(), writeable=True, onchangecallback=self.customname_changed)
    self._dbusservice['shelly'].add_path('/MeterIndex', self.settings['/MeterIndex'], onchangecallback=self._handleChangedValue, writeable=True)

    self._dbusservice['shelly'].add_path('/AllowedRoles', ['grid', 'pvinverter', 'genset', 'acload'])
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

    # add path values to dbus
    for path, settings in paths.items():
      self._dbusservice['shelly'].add_path(
        path, settings['initial'], gettextcallback=settings['textformat'], onchangecallback=self._handleChangedValue, writeable=True)

    # Position for pvinverter
    if  self.settings['/Role'] == 'pvinverter':
      self._dbusservice['shelly'].add_path('/Position', self.settings['/Position'], onchangecallback=self._handleChangedValue, writeable=True)

    self._dbusservice['shelly']['/ProductId'] = 0xFFE0
    self._dbusservice['shelly']['/ProductName'] = 'Shelly'


  def _roleChanged(self, path, value):
    if value not in ['grid', 'pvinverter', 'genset', 'acload']:
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
    }

    self.settings = SettingsDevice(self._dbus, SETTINGS, self._setting_changed)


  def _setting_changed(self, setting, oldvalue, newvalue):
    logging.info("Setting changed, setting: %s, old: %s, new: %s" % (setting, oldvalue, newvalue))

    if setting == '/Customname':
      self._dbusservice['shelly']['/CustomName'] = newvalue
      return

    if setting in ['/Url', '/User', '/Pwd']:
      self._checkShelly()

    if setting == '/Role':
      self.destroy()


  def get_customname(self):
    return self.settings['/Customname']


  def customname_changed(self, path, val):
    self.settings['/Customname'] = val
    return True


  def _shellyUpdate(self):
    try:
      
      shellyData = None

      if self._connected == True:
        if self._shellyGen == 2:
          shellyData = self._getShellyJson('rpc/Shelly.GetStatus')
        else:
          shellyData = self._getShellyJson('status')

        if shellyData == None:
          logging.info("Shelly_ID%i connection lost",self._deviceinstance)
          self._dbusservice['shelly']['/Connected'] = 0
          self._connected = False
          self._shellyGen = 0

        sumPowerAC = sumCurrentAC = sumEnergy = sumEnergyReverse = 0

        #send data to DBus
        for phase in [1,2,3]:
          pre = '/Ac/L%s' % phase

          if phase == self.settings['/Phase']:
            meterIndex = min(self._dbusservice['shelly']['/MeterCount']-1,self._dbusservice['shelly']['/MeterIndex'])
            powerAC, volatageAC, currentAC, energy, energyReverse = self._getMeterDate(shellyData,meterIndex)
          elif self.settings['/Phase'] > 3:
            powerAC, volatageAC, currentAC, energy, energyReverse = self._getMeterDate(shellyData,(phase - self.settings['/Phase']) % 3)
          else:
            powerAC = volatageAC = currentAC = energy = energyReverse = None if shellyData == None else 0
            
          self._dbusservice['shelly'][pre + '/Voltage'] = volatageAC
          self._dbusservice['shelly'][pre + '/Current'] = currentAC
          self._dbusservice['shelly'][pre + '/Power'] = powerAC
          self._dbusservice['shelly'][pre + '/Energy/Forward'] = energy
          self._dbusservice['shelly'][pre + '/Energy/Reverse'] = energyReverse
          sumPowerAC += powerAC or 0
          sumCurrentAC += currentAC or 0
          sumEnergy += energy or 0
          sumEnergyReverse += energyReverse or 0

        self._dbusservice['shelly']['/Ac/Power'] = None if shellyData == None else sumPowerAC
        self._dbusservice['shelly']['/Ac/Current'] = None if shellyData == None else sumCurrentAC
        self._dbusservice['shelly']['/Ac/Energy/Forward'] = None if shellyData == None else sumEnergy
        self._dbusservice['shelly']['/Ac/Energy/Reverse'] = None if shellyData == None else sumEnergyReverse

    except Exception as e:
      logging.critical('Error at %s', '_update', exc_info=e)

    return True


  def _getMeterDate(self,shellyData,meterIndex):
    powerAC = None
    volatageAC = None
    currentAC = None
    energy = None
    energyReverse = None
    
    try:
      if shellyData == None:
        return powerAC, volatageAC, currentAC, energy, energyReverse

      if self._shellyGen == 2:
        if 'switch:0' in shellyData:
          channel = 'switch:%s' % meterIndex
          if channel in shellyData:
            powerAC = shellyData[channel]['apower']
            volatageAC = shellyData[channel]['voltage']
            currentAC = shellyData[channel]['current']
            energy = shellyData[channel]['aenergy']['total']/1000
            energyReverse = 0
      
      else:
        if 'meters' in shellyData:
          if meterIndex < len(shellyData['meters']):
            powerAC = shellyData['meters'][meterIndex]['power']
            volatageAC = 230
            currentAC = powerAC / 230
            if 'total' in shellyData['meters'][meterIndex]:
              energy = shellyData['meters'][meterIndex]['total']/60000
            else:
              energy =  0
            energyReverse = 0
        elif 'emeters' in shellyData:
          if meterIndex < len(shellyData['emeters']):
            powerAC = shellyData['emeters'][meterIndex]['power']
            volatageAC = shellyData['emeters'][meterIndex]['voltage']
            if volatageAC > 1:
              currentAC = powerAC / volatageAC
            else:
              currentAC = 0
            energy = shellyData['emeters'][meterIndex]['total']/1000
            energyReverse = shellyData['emeters'][meterIndex]['total_returned']/1000

      return powerAC, volatageAC, currentAC, energy, energyReverse

    except Exception as e:
      return None, None, None, None, None


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
      if self._shellyGen == 2:
        URL = "http://%s/" % (self.settings['/Url']) + path
        meter_r = requests.get(url = URL, timeout=3, auth=HTTPDigestAuth(self.settings['/User'], self.settings['/Pwd']))
      else:
        URL = "http://%s:%s@%s/" % (self.settings['/User'], self.settings['/Pwd'], self.settings['/Url']) + path
        URL = URL.replace(":@", "")
        meter_r = requests.get(url = URL, timeout=3)

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
      
      if shellyInfo != None:
        if 'gen' in shellyInfo:
          self._shellyGen = shellyInfo['gen']
        else:
          self._shellyGen = 1
        
        if self._shellyGen == 1:
          shellySettings = self._getShellyJson('settings')
          if shellySettings == None:
            return
          self._dbusservice['shelly']['/DeviceName'] = shellySettings['name']
          self._dbusservice['shelly']['/FirmwareVersion'] = shellySettings['fw']
          self._dbusservice['shelly']['/ProductName'] = shellySettings['device']['type']
          shellyStatus = self._getShellyJson('status')
          if shellyStatus == None:
            return
          elif 'meters' in shellyStatus: 
            meterCount = len(shellyStatus['meters'])
          elif 'emeters' in shellyStatus:
            meterCount = len(shellyStatus['emeters'])
          else:
            meterCount = 0
            
        elif self._shellyGen == 2:
          shellySettings = self._getShellyJson('rpc/Shelly.GetDeviceInfo')
          if shellySettings == None:
            return
          self._dbusservice['shelly']['/DeviceName'] = shellySettings['name']
          self._dbusservice['shelly']['/FirmwareVersion'] = shellySettings['ver']
          self._dbusservice['shelly']['/ProductName'] = shellySettings['model']
          shellyStatus = self._getShellyJson('rpc/Shelly.GetStatus')
          if shellyStatus == None:
            return
          elif 'switch:0' in shellyStatus:
            if not 'apower' in shellyStatus['switch:0']:
              return
            elif 'switch:4' in shellyStatus:
              meterCount = 4
            elif 'switch:3' in shellyStatus:
              meterCount = 3
            elif 'switch:2' in shellyStatus:
              meterCount = 2
            else:
              meterCount = 1
          else:
            meterCount = 0
        
        self._dbusservice['shelly']['/MeterCount'] = meterCount
        if meterCount == 0:
          return

        self._dbusservice['shelly']['/MeterIndex'] = min(meterCount-1,self.settings['/MeterIndex'])

        self._dbusservice['shelly']['/Serial'] = shellyInfo['mac']
        self._dbusservice['shelly']['/HardwareVersion'] = self._shellyGen

        self._dbusservice['shelly']['/Connected'] = 1
        self._connected = True
        logging.info("Shelly_ID%i connected, %s ",self._deviceinstance, self._dbusservice['shelly']['/Serial'])

      return

    except Exception as e:
      logging.critical('Error at %s', '_checkShelly', exc_info=e)
      return


def main():
  #configure logging
  logging.basicConfig(      format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            level=logging.INFO,
                            handlers=[
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
          if config.has_option(section, 'Interval') == True:
            interval = int(config[section]['Interval'])
          else:
            interval = 1000

          DbusShellyService(int(config[section]['Deviceinstance']), interval, mainloop)

      mainloop.run()

  except Exception as e:
    logging.critical('Error at %s', 'main', exc_info=e)


if __name__ == "__main__":
  main()
