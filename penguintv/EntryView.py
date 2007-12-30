import logging
import time
import os
import htmllib, HTMLParser
import formatter
import threading
import re

import gobject
import gtk
import ptvDB

import utils
from penguintv import DEFAULT, MANUAL_SEARCH, TAG_SEARCH, MAJOR_DB_OPERATION
import EntryFormatter
import Downloader

try:
	#not good enough to load it below.  need to load it module-wide
	#or else random images don't load.  gtkmozembed is VERY picky!
	import gtkmozembed
except:
	pass
	


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
                           ([gobject.TYPE_INT, gobject.TYPE_PYOBJECT])),
		#unused except by planetview
		'entries-selected': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT, gobject.TYPE_PYOBJECT]))
    }	

	def __init__(self, widget_tree, feed_list_view, entry_list_view, 
				 app, main_window, renderer=EntryFormatter.GTKHTML):
		gobject.GObject.__init__(self)
		self._app = app
		self._db = self._app.db
		self._mm = self._app.mediamanager
		self._main_window = main_window
		self._renderer = renderer
		self._moz_realized = False
		self._state = S_DEFAULT
		self._auth_info = (-1, "","") #user:pass, url
		html_dock = widget_tree.get_widget('html_dock')
		
		scrolled_window = gtk.ScrolledWindow()
		html_dock.add(scrolled_window)
		scrolled_window.set_property("hscrollbar-policy",gtk.POLICY_AUTOMATIC)
		scrolled_window.set_property("vscrollbar-policy",gtk.POLICY_AUTOMATIC)
		
		if self._renderer == EntryFormatter.GTKHTML:
			import SimpleImageCache
			import gtkhtml2
			#scrolled_window = gtk.ScrolledWindow()
			#html_dock.add(scrolled_window)
			#scrolled_window.set_property("hscrollbar-policy",gtk.POLICY_AUTOMATIC)
			#scrolled_window.set_property("vscrollbar-policy",gtk.POLICY_AUTOMATIC)
			self._current_scroll_v = scrolled_window.get_vadjustment().get_value()
			self._current_scroll_h = scrolled_window.get_hadjustment().get_value()
			self._scrolled_window = scrolled_window
				
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
		if self._renderer==EntryFormatter.GTKHTML:
			f = open (os.path.join(self._app.glade_prefix,"gtkhtml.css"))
			for l in f.readlines(): self._css += l
			f.close()
			scrolled_window.set_property("shadow-type",gtk.SHADOW_IN)
			htmlview = gtkhtml2.View()
			self._document = gtkhtml2.Document()
			self._document.connect("link-clicked", self._link_clicked)
			htmlview.connect("on_url", self.on_url)
			self._document.connect("request-url", self._request_url)
			htmlview.get_vadjustment().set_value(0)
			htmlview.get_hadjustment().set_value(0)
			scrolled_window.set_hadjustment(htmlview.get_hadjustment())
			scrolled_window.set_vadjustment(htmlview.get_vadjustment())
			
			self._document.clear()
			htmlview.set_document(self._document)		
			scrolled_window.add(htmlview)
			self._htmlview = htmlview
			self._document_lock = threading.Lock()
			self._image_cache = SimpleImageCache.SimpleImageCache()
		elif self._renderer==EntryFormatter.MOZILLA:
			f = open (os.path.join(self._app.glade_prefix,"mozilla.css"))
			for l in f.readlines(): self._css += l
			f.close()
			if not utils.init_gtkmozembed():
				print "Error initializing mozilla.  Penguintv may crash shortly"
			gtkmozembed.set_profile_path(self._db.home, 'gecko')
			self._moz = gtkmozembed.MozEmbed()
			self._moz.connect("open-uri", self._moz_link_clicked)
			self._moz.connect("link-message", self._moz_link_message)
			self._moz.connect("realize", self._moz_realize, True)
			self._moz.connect("unrealize", self._moz_realize, False)
			self._moz.load_url("about:blank")
			#html_dock.add(self._moz)
			scrolled_window.add_with_viewport(self._moz)
			self._moz.show()
			if utils.HAS_GCONF:
				import gconf
				self._conf = gconf.client_get_default()
				self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_moz_font)
			self._reset_moz_font()
			
		html_dock.show_all()
		#self.display_custom_entry("<html></html>")
		
		self._entry_formatter = EntryFormatter.EntryFormatter(self._mm)
		#self._auto_mark_viewed = self._db.get_setting(ptvDB.BOOL, '/apps/penguintv/auto_mark_viewed', True)
		
		#signals
		self._handlers = []
		h_id = feed_list_view.connect('no-feed-selected', self.__feedlist_none_selected_cb)
		self._handlers.append((feed_list_view.disconnect, h_id))
		h_id = entry_list_view.connect('no-entry-selected', self.__entrylist_none_selected_cb)
		self._handlers.append((entry_list_view.disconnect, h_id))
		h_id = entry_list_view.connect('entry-selected', self.__entry_selected_cb)
		self._handlers.append((entry_list_view.disconnect, h_id))
		h_id = self._app.connect('entry-updated', self.__entry_updated_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('render-ops-updated', self.__render_ops_updated_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('entrylist-read', self.__entrylist_read_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('state-changed', self.__state_changed_cb)
		self._handlers.append((self._app.disconnect, h_id))
		h_id = self._app.connect('feed-polled', self.__feed_polled_cb)
		self._handlers.append((self._app.disconnect, h_id))
		
		#h_id = app.connect('setting-changed', self.__setting_changed_cb)
		#self._handlers.append((app.disconnect, h_id))
		
	def __feedlist_none_selected_cb(self, o):
		self.display_item()
		
	def __entrylist_none_selected_cb(self, o):
		self.display_item()
		
	def __entry_selected_cb(self, o, entry_id, feed_id):
		item = self._db.get_entry(entry_id)
		media = self._db.get_entry_media(entry_id)
		if media:
			item['media']=media
		else:
			item['media']=[]
		#if self._auto_mark_viewed:
		#	if self._db.get_flags_for_feed(feed_id) & ptvDB.FF_MARKASREAD:
		#		item['read'] = 1
		self.display_item(item)
		
	def __entry_updated_cb(self, app, entry_id, feed_id):
		self.update_if_selected(entry_id, feed_id)
		
	def __render_ops_updated_cb(self, app):
		self._convert_newlines = (-1, False)
		self.update_if_selected(self._current_entry['entry_id'], self._current_entry['feed_id'])
		
	def __entrylist_read_cb(self, app, feed_id, entrylist):
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
	
	def on_url(self, view, url):
		if url == None:
			url = ""
		self._main_window.display_status_message(url)
		
	def _moz_link_message(self, data):
		self._main_window.display_status_message(self._moz.get_link_message())

	def _link_clicked(self, document, link):
		link = link.strip()
		self.emit('link-activated', link)
		
	def _moz_link_clicked(self, mozembed, link):
		link = link.strip()
		self.emit('link-activated', link)
		return True #don't load url please
	
	def _moz_realize(self, widget, realized):
		self._moz_realized = realized
		self.display_item()
		 
	def _dmoz_link_clicked(self, link):
		link = link.strip()
		self.emit('link-activated', link)
		return False #don't load url please (different from regular moz!)
		
	def _gconf_reset_moz_font(self, client, *args, **kwargs):
		self._reset_moz_font()
	
	def _reset_moz_font(self):
		def isNumber(x):
			try:
				float(x)
				return True
			except:
				return False
				
		def isValid(x):
			if x in ["Bold", "Italic", "Regular","BoldItalic"]:#,"Demi","Oblique" Book 
				return False
			return True
				
		moz_font = self._db.get_setting(ptvDB.STRING, '/desktop/gnome/interface/font_name', "Sans Serif 12")
		#take just the beginning for the font name.  prepare for dense, unreadable code
		self._moz_font = " ".join(map(str, [x for x in moz_font.split() if not isNumber(x)]))
		self._moz_font = "'"+self._moz_font+"','"+" ".join(map(str, [x for x in moz_font.split() if isValid(x)])) + "',Arial"
		self._moz_size = int([x for x in moz_font.split() if isNumber(x)][-1])+4
		if not self._currently_blank:
			self.display_item(self._current_entry)

	def _request_url(self, document, url, stream):
		try:
			#this was an experiment in threaded image loading.  What happened is the stream would be closed
			#when this function exited, so by the time the image downloaded the stream was invalid
			#self._image_cache.get_image(self._current_entry['entry_id'], url, stream)
			#also the _request_url func is called by a gtk signal, and that really has to be
			#in the main thread
			stream.write(self._image_cache.get_image(url))
			stream.close()
		except Exception, ex:
			stream.close()
			raise
			
	def get_selected(self):
		if len(self._current_entry) == 0:
			return None
		elif not self._currently_blank:
			return self._current_entry['entry_id']
		return None
	
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
		item = self._db.get_entry(entry_id)
		media = self._db.get_entry_media(entry_id)
		if media:
			item['media']=media
		else:
			item['media']=[]

		self.display_item(item)
		
	def display_custom_entry(self, message):
		if self._renderer==EntryFormatter.GTKHTML:
			self._document_lock.acquire()
			self._document.clear()
			self._document.open_stream("text/html")
			self._document.write_stream("""<html><style type="text/css">
            body { background-color: %s; }</style><body>%s</body></html>""" % (self._background_color,message))
			self._document.close_stream()
			self._document_lock.release()
		elif self._renderer==EntryFormatter.MOZILLA:
			if self._moz_realized:
				self._moz.open_stream("http://ywwg.com","text/html")
				while len(message)>60000:
					part = message[0:60000]
					message = message[60000:]
					self._moz.append_data(part, long(len(part)))
				self._moz.append_data(message, long(len(message)))
				self._moz.close_stream()		
		#self.scrolled_window.hide()
		self._custom_entry = True
		return
		
	def undisplay_custom_entry(self):
		if self._custom_entry:
			message = "<html></html>"
			if self._renderer==EntryFormatter.GTKHTML:
				self._document_lock.acquire()
				self._document.clear()
				self._document.open_stream("text/html")
				self._document.write_stream(message)
				self._document.close_stream()
				self._document_lock.release()
			elif self._renderer==EntryFormatter.MOZILLA:
				if self._moz_realized:
					self._moz.open_stream("http://ywwg.com","text/html")
					self._moz.append_data(message, long(len(message)))
					self._moz.close_stream()	
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
		if self._renderer == EntryFormatter.GTKHTML:
			va = self._scrolled_window.get_vadjustment()
			ha = self._scrolled_window.get_hadjustment()
			rescroll=0
			
		if item:
			if self._renderer == EntryFormatter.GTKHTML:
				try:
					if item['entry_id'] == self._current_entry['entry_id']:
						if not self._currently_blank:
							self._current_scroll_v = va.get_value()
							self._current_scroll_h = ha.get_value()
						rescroll=1
				except:
					pass
			self._current_entry = item	
			self._currently_blank = False
			if self._convert_newlines[0] != item['feed_id']:
				self._convert_newlines = (item['feed_id'], 
				       self._db.get_flags_for_feed(item['feed_id']) & ptvDB.FF_ADDNEWLINES == ptvDB.FF_ADDNEWLINES)
			
			if item['feed_id'] != self._auth_info[0] and self._auth_info[0] != -2:
				feed_info = self._db.get_feed_info(item['feed_id'])
				if feed_info['auth_feed']:
					self._auth_info = (item['feed_id'],feed_info['auth_userpass'], feed_info['auth_domain'])
				else:
					self._auth_info = (-2, "","")
		else:
			self._convert_newlines = (-1, False)
			self._currently_blank = True
			if self._renderer == EntryFormatter.GTKHTML:
				self._current_scroll_v = va.get_value()
				self._current_scroll_h = ha.get_value()	
	
		if self._renderer == EntryFormatter.MOZILLA:
			if item is not None:
				#no comments in css { } please!
				#FIXME windows: os.path.join... wrong direction slashes?  does moz care?
				html = (
	            """<html><head>
	            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
				<style type="text/css">
	            body { background-color: %s; color: %s; font-family: %s; font-size: %s; }
	            %s
	            </style>
	            <title>title</title></head><body>%s</body></html>""") % (self._background_color,
	            														 self._foreground_color,
	            														 self._moz_font, 
	            														 self._moz_size, 
	            														 self._css, 
	            														 self._entry_formatter.htmlify_item(item, convert_newlines=self._convert_newlines[1]))
			else:
				html="""<html><style type="text/css">
	            body { background-color: %s;}</style><body></body></html>""" % (self._background_color,)
		else:
			if item is not None:
				html = (
	            """<html><head>
	            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
	            <style type="text/css">
	            body { background-color: %s; color: %s; }
	            %s
	            </style>
	            <title>title</title></head><body>%s</body></html>""") % (self._background_color, 
	            														 self._foreground_color,
	            														 self._css,
	            														 self._entry_formatter.htmlify_item(item, convert_newlines=self._convert_newlines[1]))
			else:
				html="""<html><style type="text/css">
	            body { background-color: %s; }</style><body></body></html>""" % (self._background_color,)
		
		#do highlighting for search mode
		html = html.encode('utf-8')
		if len(highlight)>0:
			try:
				highlight = highlight.replace("*","")
				p = HTMLHighlightParser(highlight)
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
			
		if self._renderer == EntryFormatter.GTKHTML:
			p = HTMLimgParser()
			p.feed(html)
			uncached=0
			for url in p.images:
				if self._image_cache.is_cached(url)==False:
					uncached+=1
			if uncached>0:
				self._document.clear()
				self._document.open_stream("text/html")
				d = { 	"background_color": self._background_color,
						"loading": _("Loading images...")}
				self._document.write_stream("""<html><style type="text/css">
            body { background-color: %(background_color)s; }</style><body><i>%(loading)s</i></body></html>""" % d) 
				self._document.close_stream()
				image_loader_thread = threading.Thread(None, self._do_download_images, None, (self._current_entry['entry_id'], html, p.images))
				image_loader_thread.start()
				return #so we don't bother rescrolling, below
			else:
				self._document.clear()
				self._document.open_stream("text/html")
				self._document.write_stream(html)
				self._document.close_stream()
				
			if rescroll==1:
				va.set_value(self._current_scroll_v)
				ha.set_value(self._current_scroll_h)
			else:
				va.set_value(va.lower)
				ha.set_value(ha.lower)
		elif self._renderer == EntryFormatter.MOZILLA:	
			if self._moz_realized:
				self._moz.open_stream("file:///","text/html") #that's a base uri for local links.  should be current dir
				while len(html)>60000:
					part = html[0:60000]
					html = html[60000:]
					self._moz.append_data(part, long(len(part)))
				self._moz.append_data(html, long(len(html)))
				self._moz.close_stream()
		
		if item is not None:		
			gobject.timeout_add(2000, self._do_delayed_set_viewed, item)
		return
		
	def _do_delayed_set_viewed(self, entry):
		if entry == self._current_entry:
			if not self._current_entry['read'] and \
			   not self._current_entry['keep'] and \
			   len(self._current_entry['media']) == 0:
				self.emit('entries-viewed', self._current_entry['feed_id'], [self._current_entry])
		return False

	def _do_download_images(self, entry_id, html, images):
		self._document_lock.acquire()
		for url in images:
			self._image_cache.get_image(url)
		#we need to go out to the app so we can queue the load request
		#in the main gtk thread
		self._app._entry_image_download_callback(entry_id, html)
		self._document_lock.release()
		
	def _images_loaded(self, entry_id, html):
		#if we're changing, nevermind.
		#also make sure entry is the same and that we shouldn't be blanks
		if self._main_window.is_changing_layout() == False and entry_id == self._current_entry['entry_id'] and self._currently_blank == False:
			va = self._scrolled_window.get_vadjustment()
			ha = self._scrolled_window.get_hadjustment()
			self._document.clear()
			self._document.open_stream("text/html")
			self._document.write_stream(html)
			self._document.close_stream()

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
	
		#just make it gray for quitting
		if self._renderer==EntryFormatter.GTKHTML:
			self._document_lock.acquire()
			self._document.clear()
			self._document.open_stream("text/html")
			self._document.write_stream("""<html><style type="text/css">
            body { background-color: %s; }</style><body></body></html>""" % (self._insensitive_color,))
			self._document.close_stream()
			self._document_lock.release()
		elif self._renderer==EntryFormatter.MOZILLA:
			#FIXME: this doesn't work, we quit before it renders
			message = """<html><head><style type="text/css">
            body { background-color: %s; }</style></head><body></body></html>""" % (self._insensitive_color,)
			self.display_custom_entry(message)
		#self.scrolled_window.hide()
		self._custom_entry = True
		return
