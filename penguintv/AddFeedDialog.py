# Written by Owen Williams
# see LICENSE for license information

import gtk
#import urllib , urlparse loaded as needed
import socket
import gettext
import os.path
import traceback
import sys
import logging

#loaded as needed
#import feedparser
import HTMLParser 

import utils
import AddFeedUtils
from ptvDB import FF_NOAUTODOWNLOAD, FF_NOSEARCH, FF_NOAUTOEXPIRE, \
                  FF_NOTIFYUPDATES, FF_ADDNEWLINES, FF_MARKASREAD
import LoginDialog
if utils.HAS_PYXML:
	import itunes

_=gettext.gettext

class AddFeedDialog:
	def __init__(self,xml,app):
		self._xml = xml
		self._app = app
		
		self._window = xml.get_widget("window_add_feed")
		if not utils.RUNNING_SUGAR and not utils.RUNNING_HILDON:
			self._window.set_transient_for(self._app.main_window.get_parent())
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self._xml.signal_connect(key, getattr(self,key))
		
		if not utils.RUNNING_SUGAR:
			self._edit_tags_widget = self._xml.get_widget("edit_tags_widget")
			self._feed_url_widget = self._xml.get_widget("feed_url")
		else:
			combo = self._xml.get_widget("feed_combo")
			self._feed_url_widget = combo.child
			combo.connect('changed', self.on_sugar_combo_changed)
			self._edit_tags_widget = None
		
	def extract_content(self):
		box = self._xml.get_widget('add_feed_box')
		box.unparent()
		box.show_all()
			
		self._window = None
		return box
				
	def show(self, autolocation=True):
		if utils.RUNNING_HILDON:
			self._window.resize(600,200)
			self._window.show_all()
			
		self._feed_url_widget.grab_focus()
		if self._window:
			self._window.show()
		self._feed_url_widget.set_text("")
		if autolocation:
			self.set_location_automatically()
		
		self._edit_tags_widget.set_text("")
		#if not utils.USE_TAGGING:
		#	l = self._xml.get_widget("add_feed_label")
		#	l.set_text(_("Please enter the URL of the feed you would like to add:"))
		#	self._xml.get_widget("tag_hbox").hide()
			
		if not utils.HAS_SEARCH:
			self._xml.get_widget('b_search').hide()
		if utils.RUNNING_SUGAR:
			self._xml.get_widget('b_notifyupdates').hide()
	
	#ripped from straw
	def set_location_automatically(self):
		def _clipboard_cb(cboard, text, data=None):
			if text.upper().startswith("FEED:") or \
			   text.upper().startswith("HTTP"):
				self._feed_url_widget.set_text(text)
					        	
		clipboard = gtk.clipboard_get(selection="CLIPBOARD")
		clipboard.request_text(_clipboard_cb, None)
	
	def set_location(self, url=""):
		self._feed_url_widget.set_text(url)
		
	#(olpc) Sugar-only
	def set_existing_feeds(self, existing_list):
		assert utils.RUNNING_SUGAR
		
		model = gtk.ListStore(int, str, str) #id, title, url
		
		combo = self._xml.get_widget("feed_combo")
		old_model = combo.get_model()
		
		for feed_id, title, url in existing_list:
			model.append([feed_id, title, url])
			
		combo.set_model(model)
		combo.set_text_column(1)
		
		del old_model
		
		
	def on_window_add_feed_delete_event(self, widget, event):
		if self._window:
			return self._window.hide_on_delete()
		
	def hide(self):
		self._feed_url_widget.set_text("")
		if self._window:
			self._window.hide()
		
	def finish(self):
		flags = 0
		if not utils.RUNNING_SUGAR:
			#reversed
			if not self._xml.get_widget('b_download').get_active():
				flags += FF_NOAUTODOWNLOAD
			#reversed
			if not self._xml.get_widget('b_search').get_active():
				flags += FF_NOSEARCH
			if self._xml.get_widget('b_notifyupdates').get_active():
				flags += FF_NOTIFYUPDATES
			if self._xml.get_widget('b_noautoexpire').get_active():
				flags += FF_NOAUTOEXPIRE
			if self._xml.get_widget('b_addnewlines').get_active():
				flags += FF_ADDNEWLINES
			if self._xml.get_widget('b_markasread').get_active():
				flags += FF_MARKASREAD
	
		tags=[]
		if len(self._edit_tags_widget.get_text()) > 0:
			for tag in self._edit_tags_widget.get_text().split(','):
				tags.append(tag.strip())
		url = self._feed_url_widget.get_text()
		if self._window:
			self._window.set_sensitive(False)
		while gtk.events_pending(): #make sure the sensitivity change goes through
			gtk.main_iteration()
		try:
			url,title = AddFeedUtils.correct_url(url, self._app.glade_prefix)
			if url is None:
				if self._window:
					self._window.set_sensitive(True)
				return
			feed_id = self._app.add_feed(url, title, tags)
			self._app.db.set_flags_for_feed(feed_id, flags)
		except AddFeedUtils.AuthorizationFailed:
			dialog = gtk.Dialog(title=_("Authorization Required"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("You must specify a valid username and password in order to add this feed."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			response = dialog.run()
			dialog.hide()
			del dialog
			if self._window:
				self._window.set_sensitive(True)
			return
		except AddFeedUtils.AuthorizationCancelled:
			if self._window:
				self._window.set_sensitive(True)
			return
		except AddFeedUtils.BadFeedURL, e:
			logging.error(str(e))
			dialog = gtk.Dialog(title=_("No Feed in Page"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("PenguinTV couldn't find a feed in the web page you provided.\nYou will need to find the RSS feed link in the web page yourself.  Sorry."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			response = dialog.run()
			dialog.hide()
			del dialog
			if self._window:
				self._window.set_sensitive(True)
			return
		#except:
		#	self._window.set_sensitive(True)
		#	return 

		if self._window:
			self._window.set_sensitive(True)
		if feed_id == -1:
			return #don't hide, give them a chance to try again.
		
		self.hide()
				
	def on_button_ok_clicked(self,event):
		self.finish()
		
	def on_feed_url_activate(self, event):
		self.finish()
		
	def on_edit_tags_widget_activate(self, event):
		self.finish()
	
	def on_button_cancel_clicked(self,event):
		self.hide()
		
	def on_sugar_combo_changed(self, combo):
		model = combo.get_model()
		active = combo.get_active()
		
		if active == -1:
			return
		
		self._feed_url_widget.set_text(model[active][2])

