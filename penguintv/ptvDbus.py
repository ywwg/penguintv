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
			self._app.window_add_feed.show()
		self._app.window_add_feed.set_location(url)
			

	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def ImportOpml(self, filename):
		try:
			f = open(filename)
			self._app.import_subscriptions(f)
		except e:
			print "Error importing subscriptions:", e
		return
