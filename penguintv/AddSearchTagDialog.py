# Written by Owen Williams
# see LICENSE for license information

import ptvDB
import gtk
import gettext

import utils
import LoginDialog

_=gettext.gettext

class AddSearchTagDialog:
	def __init__(self,xml,app):
		self._xml = xml
		self._app = app
		self._window = xml.get_widget("window_add_search_tag")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self._xml.signal_connect(key, getattr(self,key))
		self._query_widget = self._xml.get_widget("query_entry")
		self._tag_name_widget = self._xml.get_widget("tag_name_entry")
		
	def set_query(self, query):
		self._query_widget.set_text(query)
	
	def set_tag_name(self, tag_name):
		self._tag_name_widget.set_text(tag_name)
				
	def show(self):
		self._window.set_transient_for(self._app.main_window.get_parent())
		self._tag_name_widget.grab_focus()
		self._window.show()
		#self.feed_url_widget.set_text("")
		self._tag_name_widget.set_text("")
		
	def on_window_add_feed_delete_event(self, widget, event):
		return self._window.hide_on_delete()
		
	def hide(self):
		self._tag_name_widget.set_text("")
		self._query_widget.set_text("")
		self._window.hide()
		
	def finish(self):
		try:
			self._app.add_search_tag(self._query_widget.get_text(), self._tag_name_widget.get_text())
		except ptvDB.TagAlreadyExists, e:
			dialog = gtk.Dialog(title=_("Tag Name Already Exists"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("That tag name is already in use.  Please choose a different name."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			dialog.run()
			dialog.hide()
			del dialog
			self._tag_name_widget.grab_focus()
			return
		self.hide()
				
	def on_button_ok_clicked(self,event):
		self.finish()
		
	def on_tag_name_entry_activate(self, event):
		self.finish()
		
	def on_button_cancel_clicked(self,event):
		self.hide()
