# Written by Owen Williams
# see LICENSE for license information

import penguintv
import gtk

class FeedFilterDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self._app = app
		self._window = xml.get_widget("window_feed_filter")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
		self.filter_name_entry = self.xml.get_widget("filter_name_entry")
		self.query_entry = self.xml.get_widget("query_entry")
		self.pointed_feed_label = self.xml.get_widget("pointed_feed_label")
		self.pointed_feed_id = -1
				
	def show(self):
		self.filter_name_entry.grab_focus()
		self.filter_name_entry.set_text("")
		self.query_entry.set_text("")
		self.pointed_feed_label.set_text("")
		self._window.show()
		
	def finish(self):
		self._app.add_feed_filter(self.pointed_feed_id, 
								  self.filter_name_entry.get_text(),
								  self.query_entry.get_text())
		self.hide()
		
	def on_window_feed_filter_delete_event(self, widget, event):
		return self._window.hide_on_delete()
		
	def hide(self):
		self.filter_name_entry.set_text("")
		self.query_entry.set_text("")
		self.pointed_feed_label.set_text("")
		self._window.hide()
		
	def set_pointed_feed(self, feed_id, name):
		self.pointed_feed_label.set_text(name)
		self.pointed_feed_id = feed_id
	
	def set_filter_name(self, name):
		self.filter_name_entry.set_text(name)
	
	def on_add_button_clicked(self,event):
		self.finish()		
		
	def on_filter_name_entry_activate(self, event):
		self.query_entry.grab_focus()
		self.hide()
	
	def on_query_entry_activate(self, event):
		self.finish()
	
	def on_cancel_button_clicked(self,event):
		self.hide()
