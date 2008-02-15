# Written by Owen Williams
# see LICENSE for license information

import penguintv
import utils
from ptvDB import FeedAlreadyExists, FF_NOAUTODOWNLOAD, FF_NOSEARCH, \
				  FF_NOAUTOEXPIRE, FF_NOTIFYUPDATES, FF_ADDNEWLINES, \
				  FF_MARKASREAD 
import gtk
import time, datetime
from math import floor


class FeedPropertiesDialog(gtk.Window):
	def __init__(self,xml,app):
		gtk.Window.__init__(self)
		self._xml = xml
		self._app = app

		#self._window = xml.get_widget("window_feed_properties")
		contents = xml.get_widget("feed_prop_contents")
		p = contents.get_parent()
		contents.reparent(self)
		gtk.Window.set_title(self, p.get_title())
		del p

		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self._xml.signal_connect(key, getattr(self,key))
		self._title_widget = xml.get_widget('title_entry')
		self._rss_widget = xml.get_widget('rss_entry')
		self._link_widget = xml.get_widget('link_entry')
		self._description_widget = xml.get_widget('description_label')
		self._last_poll_widget = xml.get_widget('last_poll_label')
		self._next_poll_widget = xml.get_widget('next_poll_label')
		self._edit_tags_widget = xml.get_widget('edit_tags_widget')
		self._cur_flags = 0
		self._old_title = ""
		self._old_rss = ""
		self._old_link = ""
		self._old_tags = []
		self._old_flags = 0
		
		self._feed_id=0
		
		if utils.RUNNING_HILDON:
			self._hildon_inited = False
				
	def show(self):
		if utils.RUNNING_HILDON:
			if not self._hildon_inited:
				#put in a scrolled viewport so the user can see all the prefs
				parent = self._xml.get_widget('tab1_container')
				contents = self._xml.get_widget('tab1_contents')
				scrolled = gtk.ScrolledWindow()
				scrolled.set_size_request(650, 200)
				scrolled.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
				viewport = gtk.Viewport()
				contents.reparent(viewport)
				scrolled.add(viewport)
				parent.add(scrolled)
				
				parent = self._xml.get_widget('tab2_container')
				contents = self._xml.get_widget('tab2_contents')
				scrolled = gtk.ScrolledWindow()
				scrolled.set_size_request(650, 200)
				scrolled.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
				viewport = gtk.Viewport()
				contents.reparent(viewport)
				scrolled.add(viewport)
				parent.add(scrolled)
				self._hildon_inited = True
			self.show_all()
		self.set_transient_for(self._app.main_window.get_parent())
		self._xml.get_widget('notebook1').set_current_page(0)
		if not utils.HAS_SEARCH:
			self._xml.get_widget('b_search').hide()
		if utils.RUNNING_SUGAR:
			self._xml.get_widget('b_notifyupdates').hide()
		#if not utils.USE_TAGGING
		#	self._edit_tags_widget.hide()
		self._title_widget.grab_focus()
		gtk.Window.show(self)
		
	def set_feedid(self, id):
		self._feed_id = id
	
	def set_title(self, title):
		if title is None:
			title=""
		self._title_widget.set_text(title)
		self._old_title = title
		
	def set_rss(self, rss):
		if rss is None:
			rss=""
		self._rss_widget.set_text(rss)
		self._old_rss = rss
		
	def set_description(self, desc):
		if desc is None:
			desc = ""
		self._description_widget.set_text(desc)
		
	def set_link(self, link):
		if link is None:
			link = ""
		self._link_widget.set_text(link)
		self._old_link = link
		
	def set_last_poll(self, lastpoll):
		self._last_poll_widget.set_text(time.strftime("%X",time.localtime(lastpoll)))
		
	def set_next_poll(self, nextpoll):
		if nextpoll <= time.time():
			self._next_poll_widget.set_text(_("Momentarily"))
		else:
			delta = datetime.timedelta(seconds=nextpoll-time.time())
			d = {'hours':int(floor(delta.seconds/3600)),
				 'mins':int((delta.seconds-(floor(delta.seconds/3600)*3600))/60)}
			self._next_poll_widget.set_text(_("in approx %(hours)sh %(mins)sm") % d)
			
	def set_tags(self, tags):
		text = ""
		if tags:
			for tag in tags:
				text=text+tag+", "
			text = text[0:-2]
		self._edit_tags_widget.set_text(text)
		self._old_tags = tags
		
	def set_flags(self, flags):
		self._old_flags = self._cur_flags = flags
	
		#reversed
		if flags & FF_NOAUTODOWNLOAD == FF_NOAUTODOWNLOAD:
			self._xml.get_widget('b_autodownload').set_active(False)
		else:
			self._xml.get_widget('b_autodownload').set_active(True)
			
		#reversed
		if flags & FF_NOSEARCH == FF_NOSEARCH:
			self._xml.get_widget('b_search').set_active(False)
		else:
			self._xml.get_widget('b_search').set_active(True)
			
		if flags & FF_NOAUTOEXPIRE == FF_NOAUTOEXPIRE:
			self._xml.get_widget('b_noautoexpire').set_active(True)
		else:
			self._xml.get_widget('b_noautoexpire').set_active(False)
			
		if flags & FF_NOTIFYUPDATES == FF_NOTIFYUPDATES:
			self._xml.get_widget('b_notifyupdates').set_active(True)
		else:
			self._xml.get_widget('b_notifyupdates').set_active(False)
			
		if flags & FF_ADDNEWLINES == FF_ADDNEWLINES:
			self._xml.get_widget('b_addnewlines').set_active(True)
		else:
			self._xml.get_widget('b_addnewlines').set_active(False)
			
		if flags & FF_MARKASREAD == FF_MARKASREAD:
			self._xml.get_widget('b_markasread').set_active(True)
		else:
			self._xml.get_widget('b_markasread').set_active(False)
		
	#def on_window_feed_properties_delete_event(self, widget, event):
	#	return self._window.hide_on_delete()
		
	#def hide(self):
	#	self._window.hide()
		
	def on_b_autodownload_toggled(self, b_autodownload):
		# reverse the polarity!
		noautodownload = not b_autodownload.get_active()
		if noautodownload:
			if not self._cur_flags & FF_NOAUTODOWNLOAD == FF_NOAUTODOWNLOAD:
				self._cur_flags += FF_NOAUTODOWNLOAD
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
		else:
			if self._cur_flags & FF_NOAUTODOWNLOAD == FF_NOAUTODOWNLOAD:
				self._cur_flags -= FF_NOAUTODOWNLOAD
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
				
	def on_b_search_toggled(self, b_search):
		# reverse the polarity!
		nosearch = not b_search.get_active()
		if nosearch:
			if not self._cur_flags & FF_NOSEARCH == FF_NOSEARCH:
				self._cur_flags += FF_NOSEARCH
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
		else:
			if self._cur_flags & FF_NOSEARCH == FF_NOSEARCH:
				self._cur_flags -= FF_NOSEARCH
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
				
	def on_b_notifyupdates_toggled(self, b_notifyupdates):
		if b_notifyupdates.get_active():
			if not self._cur_flags & FF_NOTIFYUPDATES == FF_NOTIFYUPDATES:
				self._cur_flags += FF_NOTIFYUPDATES
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
				self._app.emit('notify-tags-changed')
		else:
			if self._cur_flags & FF_NOTIFYUPDATES == FF_NOTIFYUPDATES:
				self._cur_flags -= FF_NOTIFYUPDATES
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
				self._app.emit('notify-tags-changed')
				
	def on_b_noautoexpire_toggled(self, b_noautoexpire):
		if b_noautoexpire.get_active():
			if not self._cur_flags & FF_NOAUTOEXPIRE == FF_NOAUTOEXPIRE:
				self._cur_flags += FF_NOAUTOEXPIRE
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
		else:
			if self._cur_flags & FF_NOAUTOEXPIRE == FF_NOAUTOEXPIRE:
				self._cur_flags -= FF_NOAUTOEXPIRE
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
				
	def on_b_addnewlines_toggled(self, b_addnewlines):
		if b_addnewlines.get_active():
			if not self._cur_flags & FF_ADDNEWLINES == FF_ADDNEWLINES:
				self._cur_flags += FF_ADDNEWLINES
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
				self._app.emit('render-ops-updated')
		else:
			if self._cur_flags & FF_ADDNEWLINES == FF_ADDNEWLINES:
				self._cur_flags -= FF_ADDNEWLINES
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
				self._app.emit('render-ops-updated')
				
	def on_b_markasread_toggled(self, b_markasread):
		if b_markasread.get_active():
			if not self._cur_flags & FF_MARKASREAD == FF_MARKASREAD:
				self._cur_flags += FF_MARKASREAD
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
				self._app.emit('render-ops-updated')
		else:
			if self._cur_flags & FF_MARKASREAD == FF_MARKASREAD:
				self._cur_flags -= FF_MARKASREAD
				self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
				self._app.emit('render-ops-updated')
		
	def on_save_values_activate(self, event):
		new_title = self._title_widget.get_text()

		if new_title != self._old_title:
			#self._app.db.set_feed_name(self._feed_id,new_title)
			self._app.rename_feed(self._feed_id, new_title)
			self._old_title = new_title
		new_rss = self._rss_widget.get_text()

		if new_rss != self._old_rss:
			try:
				self._app.db.set_feed_url(self._feed_id, new_rss)
				self._old_rss = new_rss
			except FeedAlreadyExists:
				dialog = gtk.Dialog(title=_("URL Already in Use"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
				label = gtk.Label(_("A feed already exists with that URL.  Please use a different URL."))
				dialog.vbox.pack_start(label, True, True, 0)
				label.show()
				response = dialog.run()
				dialog.hide()
				del dialog
				
				self._rss_widget.grab_focus()
				return False
		new_link = self._link_widget.get_text()

		if new_link != self._old_link:
			self._app.db.set_feed_link(self._feed_id, new_link)
			self._old_link = new_link

		tags=[tag.strip() for tag in self._edit_tags_widget.get_text().split(',')]
		self._app.apply_tags_to_feed(self._feed_id, self._old_tags, tags)
		
		self._app.db.set_flags_for_feed(self._feed_id, self._cur_flags)
		return True
		
	def on_close_button_clicked(self,event):
		self._finish()
		
	def on_revert_button_clicked(self, event):
		self.set_title(self._old_title)
		self.set_rss(self._old_rss)
		self.set_link(self._old_link)
		self.set_flags(self._old_flags)
		
	def _finish(self):
 		if self.on_save_values_activate(None):
 			self.destroy()
