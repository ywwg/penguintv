#!/usr/bin/env python2.5
#Out-of-process poller for PenguinTV
#returns data over dbus

import os
import sys
import logging
logging.basicConfig(filename="/tmp/poller", filemode="a", level=logging.DEBUG)

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
import gobject

try:
	import hildon
	RUNNING_HILDON = True
except:
	RUNNING_HILDON = False
	
import ptvDB

logging.debug("poller startup")
DBusGMainLoop(set_as_default=True)

class Poller(dbus.service.Object):
	def __init__(self, remote_app, mainloop, bus, object_path="/PtvPoller"):
		dbus.service.Object.__init__(self, bus, object_path)
		self._remote_app = remote_app
		
		self._db = ptvDB.ptvDB(self._polling_cb)
		self._poll_trigger = False
		self._quitting = False
		self._mainloop = mainloop
		
		gobject.timeout_add(5000, self._app_ping)
		
	def _app_ping(self):
		try:
			if not self._remote_app.Ping():
				self.exit()
		except Exception, e:
			self.exit()
		return True
		
	def _polling_cb(self, args, cancelled=False):
		logging.debug("Poller calling back, %s" % str(self._quitting))
		try:
			if not self._remote_app.PollingCallback(str(args), cancelled):
				self.exit()
		except:
			self.exit()
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def poll_multiple(self, arguments, feeds, finished_cb):
		logging.debug("Poller starting poll mult")
		def go(arguments, feeds):
			self._db.poll_multiple(arguments, feeds)
			f = getattr(self._remote_app, finished_cb)
			f()
			return False
		gobject.idle_add(go, arguments, feeds)
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def poll_all(self, arguments, finished_cb):
		logging.debug("Poller starting poll all")
		def go(arguments):
			self._db.poll_multiple(arguments)
			f = getattr(self._remote_app, finished_cb)
			f()
			return False
		gobject.idle_add(go, arguments)
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def is_quitting(self):
		return self._quitting
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def exit(self):
		self._quitting = True
		self._db.finish(False)
		self._mainloop.quit()
		return False
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def get_pid(self):
		return os.getpid()
		
if __name__ == '__main__': # Here starts the dynamic part of the program
	bus = dbus.SessionBus()
	dubus = bus.get_object('org.freedesktop.DBus', '/org/freedesktop/dbus')
	dubus_methods = dbus.Interface(dubus, 'org.freedesktop.DBus')
	if dubus_methods.NameHasOwner('com.ywwg.PenguinTV'):
		remote_object = bus.get_object("com.ywwg.PenguinTV", "/PtvApp")
		remote_app = dbus.Interface(remote_object, "com.ywwg.PenguinTV.AppInterface")
	else:
		logging.error("No running app found")
		sys.exit(1)
		
	bus = dbus.service.BusName("com.ywwg.PenguinTVPoller", bus=bus)
	loop = gobject.MainLoop()
	poller = Poller(remote_app, loop, bus)
	if RUNNING_HILDON:
		os.nice(5)
	logging.debug("mainloop")
	loop.run()
	logging.debug("quit")

