import dbus
import dbus.service
import dbus.glib
import gobject

class ptvDbus(dbus.service.Object):
	def __init__(self, app, bus, object_path="/PtvApp"):
		self._app = app
		dbus.service.Object.__init__(self, bus, object_path)
		
	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def GetDatabaseName(self):
		return self._app.get_database_name()

	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def AddFeed(self, url):
		return self._app.add_feed(url, url)

	@dbus.service.method("com.ywwg.PenguinTV.AppInterface")
	def ImportOpml(self, filename):
		try:
			f = open(filename)
			self._app.import_subscriptions(f)
		except e:
			print "Error importing subscriptions:", e
		return
