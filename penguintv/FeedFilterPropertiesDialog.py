# Written by Owen Williams
# see LICENSE for license information

import penguintv
import gtk
from ptvDB import FeedAlreadyExists

class FeedFilterPropertiesDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self._app = app
		self._window = xml.get_widget("window_filter_properties")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
		self.filter_name_entry = self.xml.get_widget("filter_name_entry")
		self.query_entry = self.xml.get_widget("query_entry")
		self.pointed_feed_label = self.xml.get_widget("pointed_feed_label")
		self.pointed_feed_id = -1
		self.feed_id = 0
		
		self.old_name = ""
		self.old_query = ""
		
	def on_save_values_activate(self, event):
		title = self.filter_name_entry.get_text()
		query = self.query_entry.get_text()
		if title != self.old_name or query != self.old_query:
			try:
				self._app.set_feed_filter(self.feed_id, title, query)
				self.old_query = query
				self.old_name = title
			except FeedAlreadyExists:
				dialog = gtk.Dialog(title=_("Filter Already Exists"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
				label = gtk.Label(_("A filter already exists for that feed and query.  Please choose a different query."))
				dialog.vbox.pack_start(label, True, True, 0)
				label.show()
				response = dialog.run()
				dialog.hide()
				del dialog
				self.query_entry.grab_focus()
				return False
		return True
				
	def show(self):
		self.filter_name_entry.grab_focus()
		self._window.show()
		
	def on_window_feed_filter_delete_event(self, widget, event):
		return self._window.hide_on_delete()
		
	def hide(self):
		self.filter_name_entry.set_text("")
		self.query_entry.set_text("")
		self.pointed_feed_label.set_text("")
		self._window.hide()
		
	def set_pointed_feed_id(self, feed_id):
		self.pointed_feed_id = feed_id
	
	def set_feed_id(self, feed_id):
		self.feed_id = feed_id
		
	def set_query(self, query):
		self.query_entry.set_text(query)
		self.old_query = query
	
	def set_filter_name(self, name):
		self.filter_name_entry.set_text(name)
		self.old_name = name
			
	def on_close_button_clicked(self,event):
		if self.on_save_values_activate(None):
			self.hide()

	def on_revert_button_clicked(self, event):
		self.set_filter_name(self.old_name)
		self.set_query(self.old_query)
