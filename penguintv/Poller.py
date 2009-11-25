#!/usr/bin/env python
#Out-of-process poller for PenguinTV
#returns data over dbus

import os
import sys
import logging
import traceback

try:
	import hildon
	RUNNING_HILDON = True
except:
	RUNNING_HILDON = False

import socket
if RUNNING_HILDON:
	socket.setdefaulttimeout(30.0)
else:
	socket.setdefaulttimeout(10.0)

#logging.basicConfig(level=logging.DEBUG)

#try:
#	import tempfile
#	logfile = tempfile.mkstemp(prefix='poller-',suffix='.log')[1]
#	logging.basicConfig(filename=logfile, filemode="a", level=logging.DEBUG)
#except:
#	pass

import dbus
import dbus.service
import dbus.mainloop.glib
import gobject

import ptvDB

dbus.mainloop.glib.threads_init()
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

class Poller(dbus.service.Object):
	def __init__(self, remote_app, mainloop, bus, object_path="/PtvPoller"):
		dbus.service.Object.__init__(self, bus, object_path)
		logging.debug("poller startup")
		self._remote_app = remote_app
		
		self._db = ptvDB.ptvDB(self._polling_cb)
		self._poll_trigger = False
		self._quitting = False
		self._mainloop = mainloop
		
		gobject.timeout_add(15000, self._app_ping)
		
	def _app_ping(self):
		try:
			#logging.debug("ping")
			if not self._remote_app.Ping():
				logging.debug("Poller exit, ping was false (app exiting)")
				self.exit()
		except Exception, e:
			logging.debug("ping exception %s" % str(e))
			self.exit()
		return True
		
	def _polling_cb(self, args, cancelled=False):
		logging.debug("Poller calling back, %s" % (str(self._quitting)))
		#def go(args, cancelled):
		try:
			#logging.debug("tick1")
			if not self._remote_app.PollingCallback(str(args), cancelled):
				##logging.debug("tick2")
				logging.debug("Poller exit, negative callback (exiting)")
				self.exit()
			return False
		except Exception, e:
			logging.debug("Poller exit, exception in callback: %s" % str(e))
			self.exit()
			return False
		#gobject.timeout_add(100, go, args, cancelled)

	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def poll_multiple(self, arguments, feeds, finished_cb):
		logging.debug("Poller starting poll mult")
		def go(arguments, feeds):
			total = self._db.poll_multiple(arguments, feeds)
			f = getattr(self._remote_app, finished_cb)
			f(total)
			return False
		gobject.idle_add(go, arguments, feeds)
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def poll_all(self, arguments, finished_cb):
		logging.debug("Poller starting poll all")
		def go(arguments):
			total = self._db.poll_multiple(arguments)
			f = getattr(self._remote_app, finished_cb)
			f(total)
			return False
		gobject.idle_add(go, arguments)
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def is_quitting(self):
		#logging.debug("is quitting?")
		return self._quitting
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def exit(self):
		logging.debug("exiting")
		self._quitting = True
		self._db.finish(False, False)
		self._mainloop.quit()
		return False
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def get_pid(self):
		return os.getpid()
		
	@dbus.service.method("com.ywwg.PenguinTVPoller.PollInterface")
	def ping(self):
		logging.debug("responding to ping")
		return True
		
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
		os.nice(15)
	logging.debug("mainloop")
	loop.run()
	logging.debug("quit")

