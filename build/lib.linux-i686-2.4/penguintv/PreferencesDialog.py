# Written by Owen Williams
# see LICENSE for license information
import penguintv
import gconf
import gtk



class PreferencesDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self._app = app
		self._window = xml.get_widget("window_preferences")
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
		
		self.auto_download_widget = self.xml.get_widget("auto_download")
		self.auto_download_limiter_widget = self.xml.get_widget("auto_download_limiter")
		self.auto_download_limit_widget = self.xml.get_widget("auto_download_limit")
		self.limiter_hbox_widget = self.xml.get_widget("limiter_hbox")
		
		#gconf setup		
		self.conf =  gconf.client_get_default()
		self.conf.add_dir('/apps/penguintv',gconf.CLIENT_PRELOAD_NONE)
				
	def show(self):
		self._window.show_all()
		
	def hide(self):
		self._window.hide()	
		
	def on_window_preferences_delete_event(self, widget, event):
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
		
	def set_auto_download(self, auto_download):
		self.auto_download_widget.set_active(auto_download)
		self.limiter_hbox_widget.set_sensitive(auto_download)
	
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
				self.conf.set_string('/apps/penguintv/feed_refresh_method','auto')
			else:
				self.conf.set_string('/apps/penguintv/feed_refresh_method','specified')
		except AttributeError:
			pass #this fails on startup, which is good because we haven't loaded the proper value in the app yet
	
	def on_feed_refresh_changed(self,event):
		try:
			val = int(self.feed_refresh_widget.get_text())
		except ValueError:
			return
		self.conf.set_int('/apps/penguintv/feed_refresh_frequency',val)
		
	def on_auto_resume_toggled(self,event):
		self.conf.set_bool('/apps/penguintv/auto_resume',self.autoresume.get_active())
		
	def on_auto_download_toggled(self, event):
		self.conf.set_bool('/apps/penguintv/auto_download',self.auto_download_widget.get_active())
		
	def on_auto_download_limiter_toggled(self,event):
		self.conf.set_bool('/apps/penguintv/auto_download_limiter',self.auto_download_limiter_widget.get_active())
		
	def on_auto_download_limit_focus_out_event(self, thing, event):
		try:
			limit = int(self.auto_download_limit_widget.get_text())*1024
#			print "from prefs, setting gconf to, "+str(limit)
		except ValueError:
			return
		self.conf.set_int('/apps/penguintv/auto_download_limit',limit)
		
	def on_min_port_entry_changed(self,event):
		try:
			minport = int(self.min_port_widget.get_text())
		except ValueError:
			return
		self.conf.set_int('/apps/penguintv/bt_min_port',minport)
		
	def on_max_port_entry_changed(self,event):
		try:
			maxport = int(self.max_port_widget.get_text())
		except ValueError:
			return
		self.conf.set_int('/apps/penguintv/bt_max_port',maxport)
		
	def on_upload_limit_entry_changed(self,event):
		try:
			val = int(self.ul_limit_widget.get_text())
		except ValueError:
			return
		self.conf.set_int('/apps/penguintv/bt_ul_limit',val)
	
