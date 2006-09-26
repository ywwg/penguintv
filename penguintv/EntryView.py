import gobject
import gtk
import ptvDB
import penguintv
import Downloader
import utils
import time
import os
import htmllib, HTMLParser
import formatter
import threading
import re

#import traceback

try:
	#not good enough to load it below.  need to load it module-wide
	#or else random images don't load.  gtkmozembed is VERY picky!
	import gtkmozembed
except:
	pass

GTKHTML=0
MOZILLA=1
DEMOCRACY_MOZ=2

class EntryView:
	def __init__(self, widget_tree, app, main_window, renderer=GTKHTML):
		self._app = app
		self._db = self._app.db
		self._mm = self._app.mediamanager
		self._main_window = main_window
		self._renderer = renderer
		self._moz_realized = False
		html_dock = widget_tree.get_widget('html_dock')
		
		scrolled_window = gtk.ScrolledWindow()
		html_dock.add(scrolled_window)
		scrolled_window.set_property("hscrollbar-policy",gtk.POLICY_AUTOMATIC)
		scrolled_window.set_property("vscrollbar-policy",gtk.POLICY_AUTOMATIC)
		
		if self._renderer == GTKHTML:
			import SimpleImageCache
			import gtkhtml2
			#scrolled_window = gtk.ScrolledWindow()
			#html_dock.add(scrolled_window)
			#scrolled_window.set_property("hscrollbar-policy",gtk.POLICY_AUTOMATIC)
			#scrolled_window.set_property("vscrollbar-policy",gtk.POLICY_AUTOMATIC)
			self._current_scroll_v = scrolled_window.get_vadjustment().get_value()
			self._current_scroll_h = scrolled_window.get_hadjustment().get_value()
			self._scrolled_window = scrolled_window
		elif self._renderer == MOZILLA:
			import gtkmozembed
		elif self._renderer == DEMOCRACY_MOZ:
			from democracy_moz import MozillaBrowser
				
		#thanks to straw, again
		style = html_dock.get_style().copy()
		self._currently_blank=True
		self._current_entry={}
		self._updater_timer=0
		self._custom_entry = False
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
		if self._renderer==GTKHTML:
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
		elif self._renderer==MOZILLA:
			f = open (os.path.join(self._app.glade_prefix,"mozilla.css"))
			for l in f.readlines(): self._css += l
			f.close()
			gtkmozembed.set_profile_path(os.path.join(os.getenv('HOME'),".penguintv"), 'gecko')
			self._moz = gtkmozembed.MozEmbed()
			self._moz.connect("open-uri", self._moz_link_clicked)
			self._moz.connect("link-message", self._moz_link_message)
			self._moz.connect("realize", self._moz_realize, True)
			self._moz.connect("unrealize", self._moz_realize, False)
			self._moz.load_url("about:blank")
			#html_dock.add(self._moz)
			scrolled_window.add_with_viewport(self._moz)
			self._moz.show()
			if ptvDB.HAS_GCONF:
				import gconf
				self._conf = gconf.client_get_default()
				self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_moz_font)
			self._reset_moz_font()
		elif self._renderer==DEMOCRACY_MOZ:
			f = open (os.path.join(self._app.glade_prefix,"mozilla.css"))
			for l in f.readlines(): self._css += l
			f.close()
			self._mb = MozillaBrowser.MozillaBrowser()
			self._moz = self._mb.getWidget()
			self._moz.connect("link-message", self._moz_link_message)
			self._moz.connect("realize", self._moz_realize, True)
			self._moz.connect("unrealize", self._moz_realize, False)
			self._mb.setURICallBack(self._dmoz_link_clicked)
			self._moz.load_url("about:blank")
			scrolled_window.add_with_viewport(self._moz)
			if ptvDB.HAS_GCONF:
				import gconf
				self._conf = gconf.client_get_default()
				self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_moz_font)
			self._reset_moz_font()
			
		html_dock.show_all()
		#self.display_custom_entry("<html></html>")
			
	def on_url(self, view, url):
		if url == None:
			url = ""
		self._main_window.display_status_message(url)
		return
		
	def _moz_link_message(self, data):
		self._main_window.display_status_message(self._moz.get_link_message())

	def _link_clicked(self, document, link):
		link = link.strip()
		self._app.activate_link(link)
		return
		
	def _moz_link_clicked(self, mozembed, link):
		link = link.strip()
		self._app.activate_link(link)
		return True #don't load url please
	
	def _moz_realize(self, widget, realized):
		self._moz_realized = realized
		 
	def _dmoz_link_clicked(self, link):
		link = link.strip()
		self._app.activate_link(link)
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
	
	def update_if_selected(self, entry_id=None):
		"""tests to see if this is the currently-displayed entry, 
		and if so, goes back to the app and asks to redisplay it."""
		#item, progress, message = data
		try:
			if len(self._current_entry) == 0:
				return
		except:
			return
			
		if entry_id != self._current_entry['entry_id'] or self._currently_blank:
			return	
		#assemble the updated info and display
		self._app.display_entry(self._current_entry['entry_id'])
		
	def display_custom_entry(self, message):
		if self._renderer==GTKHTML:
			self._document_lock.acquire()
			self._document.clear()
			self._document.open_stream("text/html")
			self._document.write_stream("""<html><style type="text/css">
            body { background-color: %s; }</style><body>%s</body></html>""" % (self._background_color,message))
			self._document.close_stream()
			self._document_lock.release()
		elif self._renderer==MOZILLA or self._renderer == DEMOCRACY_MOZ:
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
			if self._renderer==GTKHTML:
				self._document_lock.acquire()
				self._document.clear()
				self._document.open_stream("text/html")
				self._document.write_stream(message)
				self._document.close_stream()
				self._document_lock.release()
			elif self._renderer==MOZILLA or self._renderer == DEMOCRACY_MOZ:
				if self._moz_realized:
					self._moz.open_stream("http://ywwg.com","text/html")
					self._moz.append_data(message, long(len(message)))
					self._moz.close_stream()	
			self._custom_entry = False
	
	def display_item(self, item=None, highlight=""):
		if self._renderer == GTKHTML:
			va = self._scrolled_window.get_vadjustment()
			ha = self._scrolled_window.get_hadjustment()
			rescroll=0
		
			#when a feed is refreshed, the item selection changes from an entry,
			#to blank, and to the entry again.  We used to lose scroll position because of this.
			#Now, scroll position is saved when a blank entry is displayed, and if the next
			#entry is the same id as before the blank, we restore those old values.
			#we have a bool to figure out if the current page is blank, in which case we shouldn't
			#save its scroll values.
			if item:
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
			else:
				#traceback.print_stack()
				self._currently_blank = True
				self._current_scroll_v = va.get_value()
				self._current_scroll_h = ha.get_value()	
		
		if self._renderer == MOZILLA or self._renderer == DEMOCRACY_MOZ:
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
	            														 htmlify_item(item, self._mm))
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
	            														 htmlify_item(item, self._mm))
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
			
		#print html
			
		if self._renderer == GTKHTML:
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
		elif self._renderer == MOZILLA or self._renderer == DEMOCRACY_MOZ:	
			if self._moz_realized:
				self._moz.open_stream("http://ywwg.com","text/html") #that's a base uri for local links.  should be current dir
				while len(html)>60000:
					part = html[0:60000]
					html = html[60000:]
					self._moz.append_data(part, long(len(part)))
				self._moz.append_data(html, long(len(html)))
				self._moz.close_stream()
		return
		
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
		#just make it gray for quitting
		if self._renderer==GTKHTML:
			self._document_lock.acquire()
			self._document.clear()
			self._document.open_stream("text/html")
			self._document.write_stream("""<html><style type="text/css">
            body { background-color: %s; }</style><body></body></html>""" % (self._insensitive_color,))
			self._document.close_stream()
			self._document_lock.release()
		elif self._renderer==MOZILLA or self._renderer == DEMOCRACY_MOZ:
			#FIXME: this doesn't work!
			message = """<html><head><style type="text/css">
            body { background-color: %s; }</style></head><body>WHEEEEEEEEEEEEEEE</body></html>""" % (self._insensitive_color,)
			self.display_custom_entry(message)
		#self.scrolled_window.hide()
		self._custom_entry = True
		return
		
def htmlify_item(item, mm=None, ajax=False, with_feed_titles=False, indicate_new=False):
	""" Take an item as returned from ptvDB and turn it into an HTML page.  Very messy at times,
	    but there are lots of alternate designs depending on the status of media. """

	#global download_status
	ret = []
	#ret.append('<div class="heading">')
	if indicate_new:
		if not item['read']:
			ret.append('<div class="entry_new">')
		else:
			ret.append('<div class="entry_old">')
	else:
		ret.append('<div class="entry">')
	if with_feed_titles:
		if item.has_key('title') and item.has_key('feed_title'):
			ret.append('<div class="stitle">%s<br/>%s</div>' % (item['feed_title'],item['title']))
	else:
		if item.has_key('title'):
			if indicate_new and not item['read']:
				ret.append('<div class="stitle">&#10036;%s</div>' % item['title'])
			else:
				ret.append('<div class="stitle">%s</div>' % item['title'])
			
	if item.has_key('creator'):
		if item['creator']!="" and item['creator'] is not None:
			ret.append('By %s<br/>' % (item['creator'],))			
	if item['date'] != (0,0,0,0,0,0,0,0,0):
		ret.append('<div class="sdate">%s</div><br/>' % time.strftime('%a %b %d, %Y %X',time.localtime(item['date'])))
		#ret.append('</div>')
	if item.has_key('media'):
		
		if mm is not None and not ajax:
			for medium in item['media']:
				ret += htmlify_media(medium, mm)
		else:
			ret += '<span id="' + str(item['entry_id']) + '"></span>'
	ret.append('<div class="content">')
	if item.has_key('description'):
		ret.append('<br/>%s ' % item['description'])
	ret.append('</div>')
	if item.has_key('link'):
		ret.append('<br/><a href="'+item['link']+'">'+_("Full Entry...")+'</a><br />' )
	ret.append('</p></div>')
	return "".join(ret)
	
def htmlify_media(medium, mm):
	ret = []
	ret.append('<div class="media">')
	if medium['download_status']==ptvDB.D_NOT_DOWNLOADED:    
		ret.append('<p>'+utils.html_command('download:',medium['media_id'])+' '+
						 utils.html_command('downloadqueue:',medium['media_id'])+
				         ' (%s)</p>' % (utils.format_size(medium['size'],)))
	elif medium['download_status'] == ptvDB.D_DOWNLOADING: 
		if medium.has_key('progress_message'): #downloading and we have a custom message
			ret.append('<p><i>'+medium['progress_message']+'</i> '+
			                    utils.html_command('pause:',medium['media_id'])+' '+
			                    utils.html_command('stop:',medium['media_id'])+'</p>')
		elif mm.has_downloader(medium['media_id']): #we have a downloader object
			downloader = mm.get_downloader(medium['media_id'])
			if downloader.status == Downloader.DOWNLOADING:
				d = {'progress':downloader.progress,
				     'size':utils.format_size(medium['size'])}
				ret.append('<p><i>'+_("Downloaded %(progress)d%% of %(size)s") % d +'</i> '+
				            utils.html_command('pause:',medium['media_id'])+' '+
				            utils.html_command('stop:',medium['media_id'])+'</p>')
			elif downloader.status == Downloader.QUEUED:
				ret.append('<p><i>'+_("Download queued") +'</i> '+
				            utils.html_command('pause:',medium['media_id'])+' '+
				            utils.html_command('stop:',medium['media_id'])+'</p>')
			elif downloader.status == Downloader.STOPPED:
				ret.append("STOPPPPPPPPPED")
		elif medium.has_key('progress'):       #no custom message, but we have a progress value
			d = {'progress':medium['progress'],
			     'size':utils.format_size(medium['size'])}
			ret.append('<p><i>'+_("Downloaded %(progress)d%% of %(size)s") % d +'</i> '+
			            utils.html_command('pause:',medium['media_id'])+' '+
			            utils.html_command('stop:',medium['media_id'])+'</p>')
		else:       # we have nothing to go on
			ret.append('<p><i>'+_('Downloading %s...') % utils.format_size(medium['size'])+'</i> '+utils.html_command('pause:',medium['media_id'])+' '+
													  utils.html_command('stop:',medium['media_id'])+'</p>')
	elif medium['download_status'] == ptvDB.D_DOWNLOADED:
		if mm.has_downloader(medium['media_id']):	
			downloader = mm.get_downloader(medium['media_id'])
			ret.append('<p>'+ str(downloader.message)+'</p>')
		filename = medium['file'][medium['file'].rfind("/")+1:]
		if utils.is_known_media(medium['file']): #we have a handler
			if os.path.isdir(medium['file']) and medium['file'][-1]!='/':
				medium['file']=medium['file']+'/'
			ret.append('<p>'+utils.html_command('play:',medium['media_id'])+' '+
							 utils.html_command('redownload',medium['media_id'])+' '+
							 utils.html_command('delete:',medium['media_id'])+' <br/><font size="3">(<a href="reveal://%s">%s</a>: %s)</font></p>' % (medium['file'], filename, utils.format_size(medium['size'])))
		elif os.path.isdir(medium['file']): #it's a folder
			ret.append('<p>'+utils.html_command('file://',medium['file'])+' '+
						     utils.html_command('redownload',medium['media_id'])+' '+
						     utils.html_command('delete:',medium['media_id'])+'</p>')
		else:                               #we have no idea what this is
			ret.append('<p>'+utils.html_command('file://',medium['file'])+' '+
							 utils.html_command('redownload',medium['media_id'])+' '+
							 utils.html_command('delete:',medium['media_id'])+' <br/><font size="3">(<a href="reveal://%s">%s</a>: %s)</font></p>' % (medium['file'], filename, utils.format_size(medium['size'])))
	elif medium['download_status'] == ptvDB.D_RESUMABLE:
		ret.append('<p>'+utils.html_command('resume:',medium['media_id'])+' '+
						 utils.html_command('redownload',medium['media_id'])+' '+
						 utils.html_command('delete:',medium['media_id'])+'(%s)</p>' % (utils.format_size(medium['size']),))	
	elif medium['download_status'] == ptvDB.D_ERROR:
		if mm.has_downloader(medium['media_id']):	
			downloader = mm.get_downloader(medium['media_id'])
			error_msg = downloader.message
		else:
			error_msg = _("There was an error downloading the file.")
		ret.append('<p>'+medium['url'][medium['url'].rfind('/')+1:]+': '+str(error_msg)+'  '+
								 utils.html_command('retry',medium['media_id'])+' '+
								 utils.html_command('tryresume:',medium['media_id'])+' '+
								 utils.html_command('cancel:',medium['media_id'])+'(%s)</p>' % (utils.format_size(medium['size']),))
	ret.append('</div>')								 
	return ret
#class EntryDownloaderThread(threading.Thread):
#	def __init__(self):
#		threading.Thread.__init__(self)
#		pass

class HTMLimgParser(htmllib.HTMLParser):
	def __init__(self):
		htmllib.HTMLParser.__init__(self, formatter.NullFormatter())
		self.images=[]
		
	def do_img(self, attributes):
		for name, value in attributes:
			if name == 'src':
				new_image = value
				self.images.append(new_image)
				
class HTMLHighlightParser(HTMLParser.HTMLParser):
	def __init__(self, highlight_terms):
		HTMLParser.HTMLParser.__init__(self)
		self.terms = [a.upper() for a in highlight_terms.split() if a.upper() not in ["AND","OR","NOT"]]
		self.new_data = ""
		self.style_start="""<span style="background-color: #ffff00">"""
		self.style_end  ="</span>"
		self.tag_stack = []
		
	def handle_starttag(self, tag, attrs):
		if len(attrs)>0:
			self.new_data+="<"+str(tag)+" "+" ".join([i[0]+"=\""+i[1]+"\"" for i in attrs])+">"
		else:
			self.new_data+="<"+str(tag)+">"
		self.tag_stack.append(tag)
			
	def handle_startendtag(self, tag, attrs):
		if len(attrs)>0:
			self.new_data+="<"+str(tag)+" "+" ".join([i[0]+"=\""+i[1]+"\"" for i in attrs])+"/>"
		else:
			self.new_data+="<"+str(tag)+"/>"
		self.tag_stack.pop(-1)
			
	def handle_endtag(self, tag):
		self.new_data+="</"+str(tag)+">"
	
	def handle_data(self, data):
		data_u = data.upper()
		if self.tag_stack[-1] != "style":
			for term in self.terms:
				l = len(term)
				place = 0
				while place != -1:
					#we will never match on the replacement style because the replacement is all 
					#lowercase and the terms are all uppercase
					place = data_u.find(term, place)
					if place == -1:
						break
					data   = data  [:place] + self.style_start + data  [place:place+l] + self.style_end + data  [place+l:]
					data_u = data_u[:place] + self.style_start + data_u[place:place+l] + self.style_end + data_u[place+l:]
					place+=len(self.style_start)+len(term)+len(self.style_end)
		self.new_data+=data
