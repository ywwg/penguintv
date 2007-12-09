# Written by Owen Williams
# see LICENSE for license information
import penguintv
import ptvDB
import utils
import gtk

class PreferencesDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self._app = app
		self._db = self._app.db
		self._window = xml.get_widget("window_preferences")
		self._window.set_transient_for(self._app.main_window.get_parent())
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
			
		#init values

		self.feed_refresh_widget = self.xml.get_widget("feed_refresh")
			
		self.radio_refresh_spec = self.xml.get_widget("refresh_specified")
		self.radio_refresh_spec.connect("toggled", self.select_refresh, penguintv.REFRESH_SPECIFIED)
		self.radio_refresh_auto = self.xml.get_widget("refresh_auto")
		self.radio_refresh_auto.connect("toggled", self.select_refresh, penguintv.REFRESH_AUTO)
		
		self.min_port_widget = self.xml.get_widget("min_port_entry")
		self.max_port_widget = self.xml.get_widget("max_port_entry")
		self.ul_limit_widget = self.xml.get_widget("upload_limit_entry")
		
		self.autoresume = self.xml.get_widget("auto_resume")
		self.poll_on_startup = self.xml.get_widget("poll_on_startup")
		self.show_notification_always = self.xml.get_widget("show_notification_always")
		
		self.auto_download_widget = self.xml.get_widget("auto_download")
		self.auto_download_limiter_widget = self.xml.get_widget("auto_download_limiter")
		self.auto_download_limit_widget = self.xml.get_widget("auto_download_limit")
		self.limiter_hbox_widget = self.xml.get_widget("limiter_hbox")
				
	def extract_content(self):
		vbox = self.xml.get_widget('prefs_vbox')
		vbox.unparent()
		vbox.show_all()
		self._window = None
		if utils.RUNNING_SUGAR:
			self.auto_download_limiter_widget.hide()
			self.auto_download_limit_widget.hide()
			self.limiter_hbox_widget.hide()
			self.show_notification_always.hide()
			self.xml.get_widget("button_close").hide()
		#if utils.RUNNING_HILDON:
		#	self.show_notification_always.hide()
		return vbox
		
	def show(self):
		if self._window:
			self._window.show_all()
		if utils.RUNNING_SUGAR:
			self.auto_download_limiter_widget.hide()
			self.auto_download_limit_widget.hide()
			self.limiter_hbox_widget.hide()
			self.show_notification_always.hide()
			self.xml.get_widget("button_close").hide()
		#if utils.RUNNING_HILDON:
		#	self.show_notification_always.hide()
		        
	def hide(self):
		if self._window:
			self._window.hide()	
		
	def on_window_preferences_delete_event(self, widget, event):
		if self._window:
			return self._window.hide_on_delete()
			
	def set_feed_refresh_method(self, method):
		if method==penguintv.REFRESH_AUTO:
			self.radio_refresh_auto.set_active(True)
		else:
			self.radio_refresh_spec.set_active(True)

	def set_feed_refresh_frequency(self, freq):
		self.feed_refresh_widget.set_text(str(freq))
		
	def set_bt_settings(self, bt_settings):
		self.min_port_widget.set_text(str(bt_settings['min_port']))
		self.max_port_widget.set_text(str(bt_settings['max_port']))		
		self.ul_limit_widget.set_text(str(bt_settings['ul_limit']))			
	#	self.dl_limit_widget.set_text(str(bt_settings['dl_limit']))			
	
	def set_auto_resume(self, autoresume):
		self.autoresume.set_active(autoresume)
		
	def set_poll_on_startup(self, poll_on_startup):
		self.poll_on_startup.set_active(poll_on_startup)
		
	def set_show_notification_always(self, always):
		self.show_notification_always.set_active(always)
		
	def set_auto_download(self, auto_download):
		self.auto_download_widget.set_active(auto_download)
			
	def set_auto_download_limiter(self, limiter):
		self.auto_download_limiter_widget.set_active(limiter)
		
	def set_auto_download_limit(self, limit):
		self.auto_download_limit_widget.set_text(str(limit/1024))
#		print "set text to: "+str(limit/1024)
					
	def on_button_close_clicked(self,event):
		self.hide()
		
	#we just update the gconf keys here, and then the app is signalled and it updates itself
	
	def select_refresh(self, radiobutton, new_val):
		try:
			if new_val==penguintv.REFRESH_AUTO:
				self._db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method','auto')
				if not utils.HAS_GCONF:
					self._app.set_feed_refresh_method('auto')
			else:
				self._db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method','specified')
				if not utils.HAS_GCONF:
					self._app.set_feed_refresh_method('specified')
		except AttributeError:
			pass #this fails on startup, which is good because we haven't loaded the proper value in the app yet
	
	def on_feed_refresh_changed(self,event):
		try:
			val = int(self.feed_refresh_widget.get_text())
		except ValueError:
			return
		self._db.set_setting(ptvDB.INT, '/apps/penguintv/feed_refresh_frequency',val)
		if not utils.HAS_GCONF:
			self._app.set_polling_frequency(val)
		
	def on_auto_resume_toggled(self,event):
		self._db.set_setting(ptvDB.BOOL, '/apps/penguintv/auto_resume',self.autoresume.get_active())
		if not utils.HAS_GCONF:
			self._app.set_auto_resume(self.autoresume.get_active())
			
	def on_show_notification_always(self, event):
		self._db.set_setting(ptvDB.BOOL, '/apps/penguintv/show_notification_always',self.show_notification_always.get_active())
		if not utils.HAS_GCONF:
			self._app.set_show_notification_always(self.show_notification_always.get_active())
		
	def on_poll_on_startup_toggled(self,event):
		self._db.set_setting(ptvDB.BOOL, '/apps/penguintv/poll_on_startup',self.poll_on_startup.get_active())
		if not utils.HAS_GCONF:
			self._app.set_poll_on_startup(self.poll_on_startup.get_active())
			
	def on_auto_download_toggled(self, event):
		auto_download = self.auto_download_widget.get_active()
		self._db.set_setting(ptvDB.BOOL, '/apps/penguintv/auto_download', auto_download)
		self.limiter_hbox_widget.set_sensitive(auto_download)
		if not utils.HAS_GCONF:
			self._app.set_auto_download(auto_download)
		
	def on_auto_download_limiter_toggled(self,event):
		self._db.set_setting(ptvDB.BOOL, '/apps/penguintv/auto_download_limiter',self.auto_download_limiter_widget.get_active())
		if not utils.HAS_GCONF:
			self._app.set_auto_download_limiter(self.auto_download_limiter_widget.get_active())
		
	def on_auto_download_limit_focus_out_event(self, thing, event):
		try:
			limit = int(self.auto_download_limit_widget.get_text())*1024
#			print "from prefs, setting gconf to, "+str(limit)
		except ValueError:
			return
		self._db.set_setting(ptvDB.INT, '/apps/penguintv/auto_download_limit',limit)
		if not utils.HAS_GCONF:
			self._app.set_auto_download_limit(limit)
		
	def on_min_port_entry_changed(self,event):
		try:
			minport = int(self.min_port_widget.get_text())
		except ValueError:
			return
		self._db.set_setting(ptvDB.INT, '/apps/penguintv/bt_min_port',minport)
		if not utils.HAS_GCONF:
			self._app.set_bt_minport(minport)
		
	def on_max_port_entry_changed(self,event):
		try:
			maxport = int(self.max_port_widget.get_text())
		except ValueError:
			return
		self._db.set_setting(ptvDB.INT, '/apps/penguintv/bt_max_port',maxport)
		if not utils.HAS_GCONF:
			self._app.set_bt_maxport(maxport)
		
	def on_upload_limit_entry_changed(self,event):
		try:
			val = int(self.ul_limit_widget.get_text())
		except ValueError:
			return
		self._db.set_setting(ptvDB.INT, '/apps/penguintv/bt_ul_limit',val)
		if not utils.HAS_GCONF:
			self._app.set_bt_ullimit(val)
	
