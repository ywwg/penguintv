# Written by Owen Williams
# see LICENSE for license information

import penguintv
import gtk

class AddFeedDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self._app = app
		self._window = xml.get_widget("window_add_feed")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
		self.feed_url_widget = self.xml.get_widget("feed_url")
		self.edit_tags_widget = self.xml.get_widget("edit_tags_widget")
				
	def show(self):
		self._window.show()
		self.feed_url_widget.set_text("")
		self.set_location()
		self.edit_tags_widget.set_text("")
	
	#ripped from straw
	def set_location(self):
		def _clipboard_cb(cboard, text, data=None):
			if text:
				if text[0:4] == "http":
					self.feed_url_widget.set_text(text)
				elif text[0:4] == "feed":
					self.feed_url_widget.set_text(text[5:])
					        	
		clipboard = gtk.clipboard_get(selection="CLIPBOARD")
		clipboard.request_text(_clipboard_cb, None)
		
	def on_window_add_feed_delete_event(self, widget, event):
		return self._window.hide_on_delete()
		
	def hide(self):
		self.feed_url_widget.set_text("")
		self._window.hide()
		
	def finish(self):
		tags=[]
		for tag in self.edit_tags_widget.get_text().split(','):
			tags.append(tag.strip())
		url = self.feed_url_widget.get_text()
		self._window.set_sensitive(False)
		while gtk.events_pending(): #make sure the sensitivity change goes through
			gtk.main_iteration()
		feed_id = self._app.add_feed(url)
		self._window.set_sensitive(True)
		if feed_id == -1:
			return #don't hide, give them a chance to try again.
		self._app.apply_tags_to_feed(feed_id, None, tags)
		self.hide()
				
	def on_button_ok_clicked(self,event):
		self.finish()
		
	def on_feed_url_activate(self, event):
		self.finish()
		
	def on_edit_tags_widget_activate(self, event):
		self.finish()
	
	def on_button_cancel_clicked(self,event):
		self.hide()
