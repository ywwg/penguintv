# Written by Owen Williams
# see LICENSE for license information

import penguintv


class RenameFeedDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self._app = app
		self._window = xml.get_widget("window_rename_feed")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
		self.feed_name_widget = self.xml.get_widget("feed_name")
		self.feed_id=0
				
	def show(self):
		self.feed_name_widget.grab_focus()
		self._window.show()
		
	def on_window_rename_feed_delete_event(self, widget, event):
		return self._window.hide_on_delete()
		
	def hide(self):
		self.feed_name_widget.set_text("")
		self._window.hide()
		
	def set_feed_name(self, name):
		self.feed_name_widget.set_text(name)
	
	def set_feed_id(self, feed_id):
		self.feed_id = feed_id	
		
	def on_feed_name_activate(self, event):
		self.finish()
				
	def on_button_ok_clicked(self,event):
		self.finish()
		
	def finish(self):
		self._app.rename_feed(self.feed_id, self.feed_name_widget.get_text())
		self.hide()
	
	def on_button_cancel_clicked(self,event):
		print "cancel"
		self.hide()
