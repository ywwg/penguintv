# Written by Owen Williams
# see LICENSE for license information

import penguintv
import gtk
from ptvDB import FeedAlreadyExists

class FeedFilterPropertiesDialog:
	def __init__(self,xml,app):
		self._xml = xml
		self._app = app
		self._window = xml.get_widget("window_filter_properties")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self._xml.signal_connect(key, getattr(self,key))
		self._filter_name_entry = self._xml.get_widget("filter_name_entry")
		self._query_entry = self._xml.get_widget("query_entry")
		self._pointed_feed_label = self._xml.get_widget("pointed_feed_label")
		self._pointed_feed_id = -1
		self._feed_id = 0
		
		self._old_name = ""
		self._old_query = ""
		
	def on_save_values_activate(self, event):
		title = self._filter_name_entry.get_text()
		query = self._query_entry.get_text()
		if title != self._old_name or query != self._old_query:
			try:
				self._app.set_feed_filter(self._feed_id, title, query)
				self._old_query = query
				self._old_name = title
			except FeedAlreadyExists:
				dialog = gtk.Dialog(title=_("Filter Already Exists"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
				label = gtk.Label(_("A filter already exists for that feed and query.  Please choose a different query."))
				dialog.vbox.pack_start(label, True, True, 0)
				label.show()
				response = dialog.run()
				dialog.hide()
				del dialog
				self._query_entry.grab_focus()
				return False
		return True
				
	def show(self):
		self._filter_name_entry.grab_focus()
		self._window.show()
		
	def on_window_feed_filter_delete_event(self, widget, event):
		return self._window.hide_on_delete()
		
	def hide(self):
		self._filter_name_entry.set_text("")
		self._query_entry.set_text("")
		self._pointed_feed_label.set_text("")
		self._window.hide()
		
	def set_pointed_feed_id(self, feed_id):
		self._pointed_feed_id = feed_id
	
	def set_feed_id(self, feed_id):
		self._feed_id = feed_id
		
	def set_query(self, query):
		self._query_entry.set_text(query)
		self._old_query = query
	
	def set_filter_name(self, name):
		self._filter_name_entry.set_text(name)
		self._old_name = name
			
	def on_close_button_clicked(self,event):
		if self.on_save_values_activate(None):
			self.hide()

	def on_revert_button_clicked(self, event):
		self.set_filter_name(self._old_name)
		self.set_query(self._old_query)
