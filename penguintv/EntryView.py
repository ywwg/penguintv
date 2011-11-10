import logging
import os
import htmllib, HTMLParser
import formatter

import gobject
import gtk
import ptvDB

import html.PTVhtml
import utils
from penguintv import DEFAULT, MANUAL_SEARCH, TAG_SEARCH, MAJOR_DB_OPERATION
import EntryFormatter
import Downloader
import ThreadPool

#states
S_DEFAULT = 0
S_SEARCH  = 1

class EntryView(gobject.GObject):

	__gsignals__ = {
        'link-activated': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
		'entries-viewed': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT]))
    }	

	def __init__(self, widget_tree, feed_list_view, entry_list_view, 
				 app, main_window, renderer=EntryFormatter.WEBKIT):
		gobject.GObject.__init__(self)
		self._app = app
		self._mm = self._app.mediamanager
		self._main_window = main_window
		self._renderer = renderer
		self._state = S_DEFAULT
		self._auth_info = (-1, "","") #user:pass, url
		self._widget_tree = widget_tree
		html_dock = self._widget_tree.get_widget('html_dock')
		
		self._scrolled_window = gtk.ScrolledWindow()
		html_dock.add(self._scrolled_window)
		self._scrolled_window.set_property("hscrollbar-policy",gtk.POLICY_AUTOMATIC)
		self._scrolled_window.set_property("vscrollbar-policy",gtk.POLICY_AUTOMATIC)
		
		#thanks to straw, again
		style = html_dock.get_style().copy()
		self._currently_blank=True
		self._current_entry={}
		self._updater_timer=0
		self._custom_entry = False
		self._convert_newlines = (-1, False)
		self._background_color = "#%.2x%.2x%.2x;" % (
                style.base[gtk.STATE_NORMAL].red / 256,
                style.base[gtk.STATE_NORMAL].blue / 256,
                style.base[gtk.STATE_NORMAL].green / 256)
                
		self._foreground_color = "#%.2x%.2x%.2x;" % (
                style.text[gtk.STATE_NORMAL].red / 256,
                style.text[gtk.STATE_NORMAL].blue / 256,
                style.text[gtk.STATE_NORMAL].green / 256)
                
		self._insensitive_color = "#%.2x%.2x%.2x;" % (
                style.base[gtk.STATE_INSENSITIVE].red / 256,
                style.base[gtk.STATE_INSENSITIVE].blue / 256,
                style.base[gtk.STATE_INSENSITIVE].green / 256)
                
		#for style in [style.fg, style.bg, style.base, style.text, style.mid, style.light, style.dark]:
		#	for category in [gtk.STATE_NORMAL, gtk.STATE_PRELIGHT, gtk.STATE_SELECTED, gtk.STATE_ACTIVE, gtk.STATE_INSENSITIVE]:
		#		print "#%.2x%.2x%.2x;" % (style[category].red / 256, style[category].blue / 256,style[category].green / 256)
		#	print "==========="
        
        #const found in __init__   
        
		self._css = ""
		
		#self.display_custom_entry("<html></html>")
		
		self._entry_formatter = EntryFormatter.EntryFormatter(self._mm)
		self._search_formatter = EntryFormatter.EntryFormatter(self._mm, True)
		#self._auto_mark_viewed = self._app.db.get_setting(ptvDB.BOOL, '/apps/penguintv/auto_mark_viewed', True)
		
		#signals
		self._handlers = []
		h_id = feed_list_view.connect('no-feed-selected', self.__feedlist_none_selected_cb)
		self._handlers.append((feed_list_view.disconnect, h_id))
		h_id = entry_list_view.connect('no-entry-selected', self.__entrylist_none_selected_cb)
		self._handlers.append((entry_list_view.disconnect, h_id))
		h_id = entry_list_view.connect('entry-selected', self.__entry_selected_cb)
		self._handlers.append((entry_list_view.disconnect, h_id))
		h_id = entry_list_view.connect('search-entry-selected', self.__search_entry_selected_cb)
		self._handlers.append((entry_list_view.disconnect, h_id))
		h_id = self._app.connect('entry-updated', self.__entry_updated_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('render-ops-updated', self.__render_ops_updated_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('entries-viewed', self.__entries_viewed_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('entries-unviewed', self.__entries_viewed_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('state-changed', self.__state_changed_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('feed-polled', self.__feed_polled_cb)
		self._handlers.append((self._app.disconnect, h_id))
		
		#h_id = app.connect('setting-changed', self.__setting_changed_cb)
		#self._handlers.append((app.disconnect, h_id))
		
		if self._renderer == EntryFormatter.WEBKIT:
			import html.PTVWebkit
			self._html_widget = html.PTVWebkit.PTVWebkit(self, self._app.db.home, utils.get_share_prefix())
		elif self._renderer == EntryFormatter.MOZILLA:
			import html.PTVMozilla
			self._html_widget = html.PTVMozilla.PTVMozilla(self, self._app.db.home, utils.get_share_prefix())
		elif self._renderer == EntryFormatter.GTKHTML:
			import html.PTVGtkHtml
			self._html_widget = html.PTVGtkHtml.PTVGtkHtml(self, self._app.db.home, utils.get_share_prefix())
			
	def get_display_id(self):
		try:
			return self._current_entry['entry_id']
		except:
			return None
		
	def get_bg_color(self):
		return self._background_color
		
	def get_fg_color(self):
		return self._foreground_color
		
	def get_in_color(self):
		return self._insensitive_color
		
	def post_show_init(self):
		html_dock = self._widget_tree.get_widget('html_dock')
		self._html_widget.post_show_init(self._scrolled_window)
		self._html_widget.connect('link-message', self.__link_message_cb)
		self._html_widget.connect('open-uri', self.__open_uri_cb)
		self._USING_AJAX = self._html_widget.is_ajax_ok()
		
		html_dock.show_all()
		
	def __feedlist_none_selected_cb(self, o):
		self.display_item()
		
	def __entrylist_none_selected_cb(self, o):
		self.display_item()
		
	def __entry_selected_cb(self, o, entry_id, feed_id):
		item = self._app.db.get_entry(entry_id)
		media = self._app.db.get_entry_media(entry_id)
		if media:
			item['media']=media
		else:
			item['media']=[]
		#if self._auto_mark_viewed:
		#	if self._app.db.get_flags_for_feed(feed_id) & ptvDB.FF_MARKASREAD:
		#		item['read'] = 1
		self.display_item(item)

	def __search_entry_selected_cb(self, o, entry_id, feed_id, search_query):
		item = self._app.db.get_entry(entry_id)
		media = self._app.db.get_entry_media(entry_id)
		if media:
			item['media']=media
		else:
			item['media']=[]
		self.display_item(item, search_query)
		
	def __entry_updated_cb(self, app, entry_id, feed_id):
		self.update_if_selected(entry_id, feed_id)
		
	def __render_ops_updated_cb(self, app):
		self._convert_newlines = (-1, False)
		self.update_if_selected(self._current_entry['entry_id'], self._current_entry['feed_id'])
		
	def __entries_viewed_cb(self, app, viewlist):
		for feed_id, entrylist in viewlist:
			for e in entrylist:
				self.update_if_selected(e, feed_id)
			
	def __feed_polled_cb(self, app, feed_id, update_data):
		pass
		#FIXME: "custom entry" doesn't really work well
		#if feed_id == self._current_entry['feed_id']:
		#	if update_data['pollfail']:
		#		self.display_custom_entry("<b>"+_("There was an error trying to poll this feed.")+"</b>")
		#	else:
		#		self.undisplay_custom_entry()
		
	#def __setting_changed_cb(self, app, typ, datum, value):
	#	if datum == '/apps/penguintv/auto_mark_viewed':
	#		self._auto_mark_viewed = value
	
	def __link_message_cb(self, o, message):
		if not utils.RUNNING_HILDON:
			self._main_window.display_status_message(message)
	
	def __open_uri_cb(self, o, uri):
		self.emit('link-activated', uri)

	def get_selected(self):
		if len(self._current_entry) == 0:
			return None
		elif not self._currently_blank:
			return self._current_entry['entry_id']
		return None
		
	def progress_update(self, entry_id, feed_id):
		self.update_if_selected(entry_id, feed_id)
	
	def update_if_selected(self, entry_id, feed_id):
		"""tests to see if this is the currently-displayed entry, 
		and if so, goes back to the app and asks to redisplay it."""
		#item, progress, message = data
		try:
			if len(self._current_entry) == 0:
				return
		except:
			print "exception"
			return
			
		if entry_id != self._current_entry['entry_id'] or self._currently_blank:
			return	
		#assemble the updated info and display
		item = self._app.db.get_entry(entry_id)
		media = self._app.db.get_entry_media(entry_id)
		if media:
			item['media']=media
		else:
			item['media']=[]

		self.display_item(item)
		
	def display_custom_entry(self, message):
		self._html_widget.render("<html><body>%s</body></html>" % message)
		self._custom_entry = True
		
	def undisplay_custom_entry(self):
		if self._custom_entry:
			message = "<html></html>"
			self._html_widget.render(message)
			self._custom_entry = False
			
	def _unset_state(self):
		self.display_custom_entry("")
	
	def __state_changed_cb(self, app, newstate, data=None):
		d = {DEFAULT: S_DEFAULT,
			 MANUAL_SEARCH: S_SEARCH,
			 TAG_SEARCH: S_SEARCH,
			 #penguintv.ACTIVE_DOWNLOADS: S_DEFAULT,
			 MAJOR_DB_OPERATION: S_DEFAULT}
			 
		newstate = d[newstate]
		
		if newstate == self._state:
			return
		
		self._unset_state()
		self._state = newstate
	
	def display_item(self, item=None, highlight=""):
		#when a feed is refreshed, the item selection changes from an entry,
		#to blank, and to the entry again.  We used to lose scroll position because of this.
		#Now, scroll position is saved when a blank entry is displayed, and if the next
		#entry is the same id as before the blank, we restore those old values.
		#we have a bool to figure out if the current page is blank, in which case we shouldn't
		#save its scroll values.
		if item:
			self._current_entry = item	
			self._currently_blank = False
			if self._convert_newlines[0] != item['feed_id']:
				self._convert_newlines = (item['feed_id'], 
				       self._app.db.get_flags_for_feed(item['feed_id']) & ptvDB.FF_ADDNEWLINES == ptvDB.FF_ADDNEWLINES)
			
			if item['feed_id'] != self._auth_info[0] and self._auth_info[0] != -2:
				feed_info = self._app.db.get_feed_info(item['feed_id'])
				if feed_info['auth_feed']:
					self._auth_info = (item['feed_id'],feed_info['auth_userpass'], feed_info['auth_domain'])
				else:
					self._auth_info = (-2, "","")
		else:
			self._convert_newlines = (-1, False)
			self._currently_blank = True
	
		if self._state == S_SEARCH:
			formatter = self._search_formatter
			if item is not None:
				item['feed_title'] = self._app.db.get_feed_title(item['feed_id'])
		else:
			formatter = self._entry_formatter
			
		if item is None:
			header = """<style type="text/css">
				body { background-color: %s;}</style>""" % (self._background_color,)
		else:
			header = ""
	
		html = self._html_widget.build_header(header)
		
		if item is None:
			html += """<body></body></html>""" 
		else:
			html += "<body>%s</body></html>" % formatter.htmlify_item(item, convert_newlines=self._convert_newlines[1])
	
		#do highlighting for search mode
		html = html.encode('utf-8')
		if len(highlight)>0:
			try:
				highlight = highlight.replace("*","")
				p = EntryFormatter.HTMLHighlightParser(highlight)
				p.feed(html)
				html = p.new_data
			except:
				pass
			
		if self._auth_info[0] >= 0:	
			try:
				p = EntryFormatter.HTMLImgAuthParser(self._auth_info[2], self._auth_info[1])
				p.feed(html)
				html = p.new_data
			except:
				pass
				
		#print html
		
		self._html_widget.render(html, "file:///", self.get_display_id())
			
		if item is not None:		
			gobject.timeout_add(2000, self._do_delayed_set_viewed, item)
		return
		
	def _do_delayed_set_viewed(self, entry):
		if entry == self._current_entry:
			if not self._current_entry['read'] and \
			   not self._current_entry['keep'] and \
			   len(self._current_entry['media']) == 0:
				self.emit('entries-viewed', [(self._current_entry['feed_id'], [self._current_entry['entry_id']])])
		return False

	def scroll_down(self):
		""" Old straw function, _still_ not used.  One day I might have "space reading" """
		va = self._scrolled_window.get_vadjustment()
		old_value = va.get_value()
		new_value = old_value + va.page_increment
		limit = va.upper - va.page_size
		if new_value > limit:
			new_value = limit
		va.set_value(new_value)
		return new_value > old_value
		
	def finish(self):
		for disconnector, h_id in self._handlers:
			disconnector(h_id)
	
		self._html_widget.finish()
		self._custom_entry = True
		return
