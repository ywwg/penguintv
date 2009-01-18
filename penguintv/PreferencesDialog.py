# Written by Owen Williams
# see LICENSE for license information
import gtk
import gobject
import logging

import penguintv
import ptvDB
import utils

if utils.RUNNING_HILDON:
	import hildon

class PreferencesDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self._app = app
		self._article_sync = None
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
		self.radio_refresh_never = self.xml.get_widget("refresh_never")
		self.radio_refresh_never.connect("toggled", self.select_refresh, penguintv.REFRESH_NEVER)
		
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
		
		self.cache_images_widget = self.xml.get_widget("cache_images")
		
		if utils.RUNNING_HILDON:
			self._hildon_chooser_button = gtk.Button("")
			self._hildon_chooser_button.connect('clicked', self.hildon_choose_folder)
			container = self.xml.get_widget("media_storage_container")
			old_chooser = self.xml.get_widget("media_storage_chooser")
			container.remove(old_chooser)
			container.add(self._hildon_chooser_button)
			del old_chooser
			
		model = gtk.ListStore(str)
		combo = self.xml.get_widget("sync_protocol_combo")
		combo.set_model(model)
		renderer = gtk.CellRendererText()
		combo.pack_start(renderer)
		combo.add_attribute(renderer, 'text', 0)

	def show(self):
		if utils.RUNNING_HILDON:
			self._window.resize(650,300)
			self._window.show_all()
		elif utils.RUNNING_SUGAR:
			self.auto_download_limiter_widget.hide()
			self.auto_download_limit_widget.hide()
			self.limiter_hbox_widget.hide()
			self.show_notification_always.hide()
			self.xml.get_widget("button_close").hide()
		elif self._window:
			self._window.show_all()
		if not utils.HAS_STATUS_ICON:
			self.show_notification_always.hide()
		if not utils.ENABLE_ARTICLESYNC:
			self.xml.get_widget("sync_contents").hide()
			self.xml.get_widget("notebook3").set_show_tabs(False)
		        
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
		
	def hildon_choose_folder(self, widget):
		new_chooser = hildon.FileChooserDialog(self._app.main_window.window, action=gtk.FILE_CHOOSER_ACTION_SELECT_FOLDER)
		new_chooser.set_default_response(gtk.RESPONSE_OK)
		new_chooser.set_current_folder(self._hildon_chooser_button.get_label())		
		response = new_chooser.run()
		if response == gtk.RESPONSE_OK:
			try:
				logging.debug("look it changed hildon")
				val = new_chooser.get_filename()
				self._app.db.set_setting(ptvDB.STRING, '/apps/penguintv/media_storage_location', val)
				if not utils.HAS_GCONF:
					logging.debug("telling the app about the new setting")
					self._app.set_media_storage_location(val)
			except:
				pass
		elif response == gtk.RESPONSE_CANCEL:
			#print 'Closed, no files selected'
			pass
		new_chooser.destroy()
				
	def hide(self):
		if self._window:
			self._window.hide()
			
	def set_article_sync(self, article_sync):
		self._article_sync = article_sync
		combo = self.xml.get_widget("sync_protocol_combo")
		model = combo.get_model()
		model.clear()
		for name in self._article_sync.get_plugins().keys():
			model.append([name])
		
	def on_window_preferences_delete_event(self, widget, event):
		if self._window:
			return self._window.hide_on_delete()
			
	def set_feed_refresh_method(self, method):
		if method == penguintv.REFRESH_AUTO:
			self.radio_refresh_auto.set_active(True)
		elif method == penguintv.REFRESH_SPECIFIED:
			self.radio_refresh_spec.set_active(True)
		else:
			self.radio_refresh_never.set_active(True)

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
		
	def set_cache_images(self, cache):
		self.cache_images_widget.set_active(cache)
		
	def set_auto_download(self, auto_download):
		self.auto_download_widget.set_active(auto_download)
			
	def set_auto_download_limiter(self, limiter):
		self.auto_download_limiter_widget.set_active(limiter)
		
	def set_auto_download_limit(self, limit):
		self.auto_download_limit_widget.set_text(str(limit/1024))
#		print "set text to: "+str(limit/1024)

	def set_media_storage_location(self, location):
		if utils.RUNNING_HILDON:
			self._hildon_chooser_button.set_label(location)
		else:
			self.xml.get_widget("media_storage_chooser").set_current_folder(location)
			
	def set_use_article_sync(self, enabled):
		self.xml.get_widget("sync_enabled_checkbox").set_active(enabled)
		self.xml.get_widget("sync_settings_frame").set_sensitive(enabled)
		self.xml.get_widget("sync_status_box").set_sensitive(enabled)
		
	def set_article_sync_plugin(self, plugin):
		combo = self.xml.get_widget("sync_protocol_combo")
		for row in combo.get_model():
			if row[0] == plugin:
				combo.set_active_iter(row.iter)
				self._add_sync_ui(plugin)
				return
				
	def set_article_sync_readonly(self, readonly):
		self.xml.get_widget("sync_readonly_check").set_active(readonly)

	def get_media_storage_location(self):
		if utils.RUNNING_HILDON:
			return self._hildon_chooser_button.get_label()
		else:
			widget = self.xml.get_widget("media_storage_chooser")
			return widget.get_filename()

	def get_use_article_sync(self):
		return self.xml.get_widget("sync_enabled_checkbox").get_active()
		
	def get_article_sync_readonly(self):
		return self.xml.get_widget("sync_readonly_check").get_active()
			
	def set_sync_status(self, status):
		self.xml.get_widget("sync_status_label").set_text(status)
					
	def on_button_close_clicked(self,event):
		self.hide()
		
	#we just update the gconf keys here, and then the app is signalled and it updates itself
	
	def select_refresh(self, radiobutton, new_val):
		try:
			if new_val == penguintv.REFRESH_AUTO:
				self._app.db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method', 'auto')
				if not utils.HAS_GCONF:
					self._app.set_feed_refresh_method('auto')
			elif new_val == penguintv.REFRESH_SPECIFIED:
				self._app.db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method', 'specified')
				if not utils.HAS_GCONF:
					self._app.set_feed_refresh_method('specified')
			else:
				self._app.db.set_setting(ptvDB.STRING, '/apps/penguintv/feed_refresh_method', 'never')
				if not utils.HAS_GCONF:
					self._app.set_feed_refresh_method('never')
		except AttributeError:
			pass #this fails on startup, which is good because we haven't loaded the proper value in the app yet
	
	def on_feed_refresh_changed(self,event):
		try:
			val = int(self.feed_refresh_widget.get_text())
		except ValueError:
			return
		self._app.db.set_setting(ptvDB.INT, '/apps/penguintv/feed_refresh_frequency',val)
		if not utils.HAS_GCONF:
			self._app.set_polling_frequency(val)
		
	def on_auto_resume_toggled(self,event):
		self._app.db.set_setting(ptvDB.BOOL, '/apps/penguintv/auto_resume',self.autoresume.get_active())
		if not utils.HAS_GCONF:
			self._app.set_auto_resume(self.autoresume.get_active())
			
	def on_show_notification_always(self, event):
		self._app.db.set_setting(ptvDB.BOOL, '/apps/penguintv/show_notification_always',self.show_notification_always.get_active())
		if not utils.HAS_GCONF:
			self._app.set_show_notification_always(self.show_notification_always.get_active())
		
	def on_poll_on_startup_toggled(self,event):
		self._app.db.set_setting(ptvDB.BOOL, '/apps/penguintv/poll_on_startup',self.poll_on_startup.get_active())
		if not utils.HAS_GCONF:
			self._app.set_poll_on_startup(self.poll_on_startup.get_active())
			
	def on_cache_images_toggled(self, event):
		cache_images = self.cache_images_widget.get_active()
		self._app.db.set_setting(ptvDB.BOOL, '/apps/penguintv/cache_images_locally', cache_images)
		if not utils.HAS_GCONF:
			self._app.set_cache_images(cache_images)
			
	def on_auto_download_toggled(self, event):
		auto_download = self.auto_download_widget.get_active()
		self._app.db.set_setting(ptvDB.BOOL, '/apps/penguintv/auto_download', auto_download)
		self.limiter_hbox_widget.set_sensitive(auto_download)
		if not utils.HAS_GCONF:
			self._app.set_auto_download(auto_download)
		
	def on_auto_download_limiter_toggled(self,event):
		self._app.db.set_setting(ptvDB.BOOL, '/apps/penguintv/auto_download_limiter',self.auto_download_limiter_widget.get_active())
		if not utils.HAS_GCONF:
			self._app.set_auto_download_limiter(self.auto_download_limiter_widget.get_active())
		
	def on_auto_download_limit_focus_out_event(self, thing, event):
		try:
			limit = int(self.auto_download_limit_widget.get_text())*1024
#			print "from prefs, setting gconf to, "+str(limit)
		except ValueError:
			return
		self._app.db.set_setting(ptvDB.INT, '/apps/penguintv/auto_download_limit',limit)
		if not utils.HAS_GCONF:
			self._app.set_auto_download_limit(limit)
		
	def on_min_port_entry_changed(self,event):
		try:
			minport = int(self.min_port_widget.get_text())
		except ValueError:
			return
		self._app.db.set_setting(ptvDB.INT, '/apps/penguintv/bt_min_port',minport)
		if not utils.HAS_GCONF:
			self._app.set_bt_minport(minport)
		
	def on_max_port_entry_changed(self,event):
		try:
			maxport = int(self.max_port_widget.get_text())
		except ValueError:
			return
		self._app.db.set_setting(ptvDB.INT, '/apps/penguintv/bt_max_port',maxport)
		if not utils.HAS_GCONF:
			self._app.set_bt_maxport(maxport)
		
	def on_upload_limit_entry_changed(self,event):
		try:
			val = int(self.ul_limit_widget.get_text())
		except ValueError:
			return
		self._app.db.set_setting(ptvDB.INT, '/apps/penguintv/bt_ul_limit',val)
		if not utils.HAS_GCONF:
			self._app.set_bt_ullimit(val)
			
	def on_media_storage_chooser_file_set(self, widget):
		logging.debug("look it changed")
		val = widget.get_filename()
		self._app.db.set_setting(ptvDB.STRING, '/apps/penguintv/media_storage_location', val)
		if not utils.HAS_GCONF:
			logging.debug("telling the app about the new setting")
			self._app.set_media_storage_location(val)
			
	def on_sync_enabled_checkbox_toggled(self, widget):
		enabled = widget.get_active()
		self._app.db.set_setting(ptvDB.BOOL, '/apps/penguintv/use_article_sync', 
			enabled)
		if not utils.HAS_GCONF:
			self._app.set_use_article_sync(enabled)
	
		self.xml.get_widget("sync_settings_frame").set_sensitive(enabled)
		self.xml.get_widget("sync_status_box").set_sensitive(enabled)
		self.xml.get_widget("sync_readonly_check").set_sensitive(enabled)
		
	def on_sync_protocol_combo_changed(self, widget):
		current_plugin = self._article_sync.get_current_plugin()
		model = widget.get_model()
		it = widget.get_active_iter()
		plugin = model[it][0]
		if plugin == current_plugin:
			#logging.debug("same plugin")
			return
			
		#logging.debug("COMBO CHANGED")
		if self._article_sync.is_enabled():	
			self._app.sync_authenticate(newplugin=plugin)
			
		def _do_switch_ui():
			if not self._article_sync.is_loaded():
				logging.debug("prefs window: plugin not loaded yet")
				return True
				
			self._remove_sync_ui()
			self._add_sync_ui(plugin)
			
			#logging.debug("setting sync plugin to %s" % plugin)
			self._app.db.set_setting(ptvDB.STRING, '/apps/penguintv/article_sync_plugin', 
				plugin)
			return False
				
		gobject.timeout_add(500, _do_switch_ui)
		
	def _remove_sync_ui(self):
		def infanticide(child):
			#logging.debug("destroying %s" % str(child))
			child.destroy()
			
		container = self.xml.get_widget("sync_settings_vbox")
		container.foreach(infanticide)
		
	def _add_sync_ui(self, plugin):
		container = self.xml.get_widget("sync_settings_vbox")
		new_ui = self._article_sync.get_parameter_ui(plugin)
		container.add(new_ui)
		container.show_all()	
		
	def on_sync_login_button_clicked(self, widget):
		self._app.sync_authenticate()
		
	def on_sync_readonly_check_toggled(self, widget):
		enabled = widget.get_active()
		self._app.db.set_setting(ptvDB.BOOL, '/apps/penguintv/sync_readonly',
			enabled)
		if not utils.HAS_GCONF:
			self._app.set_article_sync_readonly(enabled)
		
