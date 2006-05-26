# Written by Owen Williams
# see LICENSE for license information

import penguintv


class EditTextTagsDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self._app = app
		self._window = xml.get_widget("window_edit_tags_single")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
		self.edit_tags_widget = self.xml.get_widget("edit_tags_widget")
		self.feed_id=0
		self.old_tags = []
				
	def show(self):
		self.edit_tags_widget.grab_focus()
		self._window.show()
		
	def on_window_edit_tags_single_delete_event(self, widget, event):
		return self._window.hide_on_delete()
		
	def hide(self):
		self.edit_tags_widget.set_text("")
		self._window.hide()
		
	def set_tags(self, tags):
		text = ""
		if tags:
			for tag in tags:
				text=text+tag+", "
			text = text[0:-2]
		self.edit_tags_widget.set_text(text)
		self.old_tags = tags
	
	def set_feed_id(self, feed_id):
		self.feed_id = feed_id
	
	def on_button_ok_clicked(self,event):
		tags=[]
		for tag in self.edit_tags_widget.get_text().split(','):
			tags.append(tag.strip())
		self._app.apply_tags_to_feed(self.feed_id, self.old_tags, tags)
		self.hide()
		
		
	def on_edit_tags_widget_activate(self, event):
		tags=[]
		for tag in self.edit_tags_widget.get_text().split(','):
			tags.append(tag.strip())
		self._app.apply_tags_to_feed(self.feed_id, self.old_tags, tags)
		self.hide()
	
	def on_button_cancel_clicked(self,event):
		self.hide()
