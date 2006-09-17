# Written by Owen Williams
# see LICENSE for license information

import penguintv
from ptvDB import FeedAlreadyExists
import gtk
import time, datetime
from math import floor


class FeedPropertiesDialog:
	def __init__(self,xml,app):
		self.xml = xml
		self._app = app
		self._window = xml.get_widget("window_feed_properties")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self.xml.signal_connect(key, getattr(self,key))
		self.title_widget = xml.get_widget('title_entry')
		self.rss_widget = xml.get_widget('rss_entry')
		self.link_widget = xml.get_widget('link_entry')
		self.description_widget = xml.get_widget('description_label')
		self.last_poll_widget = xml.get_widget('last_poll_label')
		self.next_poll_widget = xml.get_widget('next_poll_label')
		self.old_title = ""
		self.old_rss = ""
		self.old_link = ""
		
		self.feed_id=0
				
	def show(self):
		self.title_widget.grab_focus()
		self._window.show()
		
	def set_feedid(self, id):
		self.feed_id = id
	
	def set_title(self, title):
		if title is None:
			title=""
		self.title_widget.set_text(title)
		self.old_title = title
		
	def set_rss(self, rss):
		if rss is None:
			rss=""
		self.rss_widget.set_text(rss)
		self.old_rss = rss
		
	def set_description(self, desc):
		if desc is None:
			desc = ""
		self.description_widget.set_text(desc)
		
	def set_link(self, link):
		if link is None:
			link = ""
		self.link_widget.set_text(link)
		self.old_link = link
		
	def set_last_poll(self, lastpoll):
		self.last_poll_widget.set_text(time.strftime("%X",time.localtime(lastpoll)))
		
	def set_next_poll(self, nextpoll):
		if nextpoll <= time.time():
			self.next_poll_widget.set_text(_("Momentarily"))
		else:
			delta = datetime.timedelta(seconds=nextpoll-time.time())
			d = {'hours':int(floor(delta.seconds/3600)),
				 'mins':int((delta.seconds-(floor(delta.seconds/3600)*3600))/60)}
			self.next_poll_widget.set_text(_("in approx %(hours)sh %(mins)sm") % d)
		
	def on_window_feed_properties_delete_event(self, widget, event):
		return self._window.hide_on_delete()
		
	def hide(self):
		self._window.hide()
		
	def on_save_values_activate(self, event):
		new_title = self.title_widget.get_text()
		if new_title != self.old_title:
			self._app.db.set_feed_name(self.feed_id,new_title)
			self.old_title = new_title
		new_rss = self.rss_widget.get_text()
		if new_rss != self.old_rss:
			try:
				self._app.db.set_feed_url(self.feed_id, new_rss)
				self.old_rss = new_rss
			except FeedAlreadyExists:
				dialog = gtk.Dialog(title=_("URL Already in Use"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
				label = gtk.Label(_("A feed already exists with that URL.  Please use a different URL."))
				dialog.vbox.pack_start(label, True, True, 0)
				label.show()
				response = dialog.run()
				dialog.hide()
				del dialog
				
				self.rss_widget.grab_focus()
				return False
		new_link = self.link_widget.get_text()
		if new_link != self.old_link:
			self._app.db.set_feed_link(self.feed_id, new_link)
			self.old_link = new_link
		return True
		
				
	def on_close_button_clicked(self,event):
		self.finish()
		
	def on_revert_button_clicked(self, event):
		self.set_title(self.old_title)
		self.set_rss(self.old_rss)
		self.set_link(self.old_link)
		
	def finish(self):
 		if self.on_save_values_activate(None):
 			self.hide()
