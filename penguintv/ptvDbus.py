import dbus
import dbus.service
import dbus.glib
import gobject

import utils

class ptvDbus(dbus.service.Object):
	def __init__(self, app, bus, object_path="/PtvApp"):
		self._app = app
		dbus.service.Object.__init__(self, bus, object_path)
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def GetDatabaseName(self):
		return self._app.get_database_name()

	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def AddFeed(self, url):
		if utils.RUNNING_SUGAR:
			self.sugar_add_button.popup()
		else:
			self._app.main_window.show_window_add_feed(False)
		self._app.main_window.set_window_add_feed_location(url)

	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def ImportOpml(self, filename):
		try:
			f = open(filename)
			self._app.import_subscriptions(f)
		except e:
			print "Error importing subscriptions:", e
		return
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def PollingCallback(self, pyobject_str, cancelled=False):
		#print "args we got to callback: %s" % pyobject_str
		args = eval(pyobject_str)
		self._app.polling_callback(args, cancelled)
		if self._app.is_exiting():
			return False
		return True
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def FinishedCallback(self, total):
		self._app.poll_finished_cb(total)
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def Ping(self):
		return self._app.poller_ping_cb()
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def Play(self):
		if self._app.is_exiting():
			return False
		self._app.player.control_internal("play")
		return True
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def Pause(self):
		if self._app.is_exiting():
			return False
		self._app.player.control_internal("pause")
		return True
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def Next(self):
		if self._app.is_exiting():
			return False
		self._app.player.control_internal("next")
		return True
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def Prev(self):
		if self._app.is_exiting():
			return False
		self._app.player.control_internal("prev")
		return True
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def PlayPause(self):
		if self._app.is_exiting():
			return False
		self._app.player.control_internal("playpause")
		return True
