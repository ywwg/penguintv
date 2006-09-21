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

GTKHTML=0
MOZILLA=1
DEMOCRACY_MOZ=2
GECKOEMBED=3

class EntryView:
	def __init__(self, widget_tree, app, main_window, renderrer=GTKHTML):
		self._app = app
		self._mm = self._app.mediamanager
		self._main_window = main_window
		self._RENDERRER = renderrer
		scrolled_window = widget_tree.get_widget('html_scrolled_window')
		scrolled_window.set_property("hscrollbar-policy",gtk.POLICY_AUTOMATIC)
		scrolled_window.set_property("vscrollbar-policy",gtk.POLICY_AUTOMATIC)
		
		if self._RENDERRER == GTKHTML:
			import SimpleImageCache
			import gtkhtml2
		elif self._RENDERRER == MOZILLA:
			import gtkmozembed
		elif self._RENDERRER == DEMOCRACY_MOZ:
			from democracy_moz import MozillaBrowser
		elif self._RENDERRER == GECKOEMBED:
			import geckoembed
				
		#thanks to straw, again
		style = scrolled_window.get_style().copy()
		self._currently_blank=True
		self._scrolled_window = scrolled_window
		self._current_entry={}
		self._current_scroll_v = scrolled_window.get_vadjustment().get_value()
		self._current_scroll_h = scrolled_window.get_hadjustment().get_value()
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
                
		#for style in [style.fg, style.bg, style.base, style.text, style.mid, style.light, style.dark]:
		#	for category in [gtk.STATE_NORMAL, gtk.STATE_PRELIGHT, gtk.STATE_SELECTED, gtk.STATE_ACTIVE, gtk.STATE_INSENSITIVE]:
		#		print "#%.2x%.2x%.2x;" % (style[category].red / 256, style[category].blue / 256,style[category].green / 256)
		#	print "==========="
        
        #const found in __init__        
		if self._RENDERRER==GTKHTML:
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
		elif self._RENDERRER==MOZILLA:
			self._moz = gtkmozembed.MozEmbed()
			self._moz.connect("open-uri", self._moz_link_clicked)
			#self._moz.connect("link-messsage", self._moz_link_message)
			self._moz.load_url("about:blank")
			self._moz.get_location()
			scrolled_window.add_with_viewport(self._moz)
			import gconf
			self._conf = gconf.client_get_default()
			self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_moz_font)
			self._reset_moz_font()
		elif self._RENDERRER==DEMOCRACY_MOZ:
			self._mb = MozillaBrowser.MozillaBrowser()
			self._moz = self._mb.getWidget()
			self._moz.connect("link-message", self._moz_link_message)
			self._mb.setURICallBack(self._dmoz_link_clicked)
			self._moz.load_url("about:blank")
			self._moz.get_location()
			scrolled_window.add_with_viewport(self._moz)
			import gconf
			self._conf = gconf.client_get_default()
			self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_moz_font)
			self._reset_moz_font()
		elif self._RENDERRER == GECKOEMBED:
			path = os.path.join(os.getenv('HOME'), '.penguintv','gecko')
			geckoembed.set_profile_path(path)
			self._moz = geckoembed.Browser()
			self._moz.load_address('about:blank')
			self._moz.connect("open-uri", self._moz_link_clicked)
			scrolled_window.add_with_viewport(self._moz)
			import gconf
			self._conf = gconf.client_get_default()
			self._conf.notify_add('/desktop/gnome/interface/font_name',self._gconf_reset_moz_font)
			self._reset_moz_font()
			
		scrolled_window.show_all()
		#self.display_custom_entry("<html></html>")
		
	def on_url(self, view, url):
		if url == None:
			url = ""
		self._main_window.display_status_message(url)
		return
		
	def _moz_link_message(self, data):
		print "boink"
		print self._moz.get_link_message()

	def _link_clicked(self, document, link):
		link = link.strip()
		self._app.activate_link(link)
		return
		
	def _moz_link_clicked(self, mozembed, uri):
		#WAIT:  gtkmozembed is returning the wrong type -- coming out as a pointer, should be string
		#wait for fixes
		print "when this stops being a pointer, we can use MOZ"
		print uri
		#link = link.strip()
		#self._app.activate_link(link)
		return True #don't load url please
		 
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
				
		moz_font = self._conf.get_string('/desktop/gnome/interface/font_name')
		#take just the beginning for the font name.  prepare for dense, unreadable code
		self._moz_font = " ".join(map(str, [x for x in moz_font.split() if isNumber(x)==False]))
		self._moz_font = "'"+self._moz_font+"','"+" ".join(map(str, [x for x in moz_font.split() if isValid(x)])) + "',Arial"
		self._moz_size = int([x for x in moz_font.split() if isNumber(x)][-1])+4
		if self._currently_blank == False:
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
			
		if entry_id != self._current_entry['entry_id'] or self._currently_blank==True:
			return	
		#assemble the updated info and display
		self._app.display_entry(self._current_entry['entry_id'])
	
	def display_item(self, item=None, highlight=""):
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
					if self._currently_blank == False:
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
		
		enc = None
		
		style_adjustments=""
		if self._RENDERRER == MOZILLA or self._RENDERRER == DEMOCRACY_MOZ or self._RENDERRER == GECKOEMBED:
			if item is not None:
				html = (
	            """<html><head>
	            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
	            <style type="text/css">
	            body { background-color: %s;
	            	   color: %s;
	                   font-family: %s;
	                   font-size: %s;
	                   <!--  Why doesn't background-image work?
	                   background-image:  url('file:///home/owen/src/penguintv/cvs/trunk/penguintv/share/penguintvicon.png');
					   background-repeat: no-repeat;
					   background-attachment: fixed-->
			    }
	            dd { padding-left: 20pt; }  <!-- for eschaton -->
	            q { font-style: italic;}
	            .heading { background-color: #f0f0ff; border-width:1px; border-style: solid; padding:12pt; margin:12pt; }
	            blockquote { display: block; color: #444444; background-color:#EEEEFF; border-color:#DDDDDD; border-width:2px; border-style: solid; padding:12pt; margin:12pt;}
	            .stitle {font-size:14pt; font-weight:bold; font-family: 'Lucida Grande', Verdana, Arial, Sans-Serif; padding-bottom:20pt;}
	            .sdate {font-size:8pt; color: #777777}
	            .content {padding-left:20pt;margin-top:12pt;}
	            .media {background-color:#EEEEEE; border-color:#000000; border-width:2px; border-style: solid; padding:8pt; margin:8pt; }
	            </style>
	            <title>title</title></head><body>%s</body></html>""") % (self._background_color,self._foreground_color,self._moz_font, self._moz_size, self._htmlify_item(item))
			else:
				html="""<html><style type="text/css">
	            body { background-color: %s;}</style><body></body></html>""" % (self._background_color,)
		else:
			if item is not None:
				html = (
	            """<html><head>
	            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
	            <style type="text/css">
	            body { background-color: %s;color: %s;}
	            dd { padding-left: 20pt; }  <!-- for eschaton -->
	            q { font-style: italic;}
	            .heading { background-color: #f0f0ff; border-width:1px; border-style: solid; padding:12pt; margin:12pt; }
	            blockquote { display: block; color: #444444; background-color:#EEEEFF; border-color:#DDDDDD; border-width:2px; border-style: solid; padding:12pt; margin:12pt;}
	            .stitle {font-size:14pt; font-weight:bold; font-family: 'Lucida Grande', Verdana, Arial, Sans-Serif; padding-bottom:20pt;}
	            .sdate {font-size:8pt; color: #777777}
	            .content {padding-left:20pt;margin-top:12pt;}
	            .media {background-color:#EEEEEE; border-color:#000000; border-width:2px; border-style: solid; padding:8pt; margin:8pt; }
	            </style>
	            <title>title</title></head><body>%s</body></html>""") % (self._background_color,self._foreground_color,self._htmlify_item(item))
			else:
				html="""<html><style type="text/css">
	            body { background-color: %s; }</style><body></body></html>""" % (self._background_color,)
		#print html
		html = html.encode('utf-8')
		if self._RENDERRER == GTKHTML:
			if len(highlight)>0:
				try:
					highlight = highlight.replace("*","")
					p = HTMLHighlightParser(highlight)
					p.feed(html)
					html = p.new_data
				except:
					pass
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
		elif self._RENDERRER == MOZILLA or self._RENDERRER == DEMOCRACY_MOZ or self._RENDERRER == GECKOEMBED:
			self._moz.open_stream("http://ywwg.com","text/html") #that's a base uri for local links.  should be current dir
			self._moz.append_data(html, long(len(html)))
			self._moz.close_stream()
		
		if rescroll==1:
			va.set_value(self._current_scroll_v)
			ha.set_value(self._current_scroll_h)
		else:
			va.set_value(va.lower)
			ha.set_value(ha.lower)
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
		
	def display_custom_entry(self, message):
		if self._RENDERRER==GTKHTML:
			self._document_lock.acquire()
			self._document.clear()
			self._document.open_stream("text/html")
			self._document.write_stream("""<html><style type="text/css">
            body { background-color: %s; }</style><body>%s</body></html>""" % (self._background_color,message))
			self._document.close_stream()
			self._document_lock.release()
		elif self._RENDERRER==MOZILLA or self._RENDERRER == DEMOCRACY_MOZ or self._RENDERRER == GECKOEMBED:
			self._moz.open_stream("http://ywwg.com","text/html")
			self._moz.append_data(message, long(len(message)))
			self._moz.close_stream()		
		#self.scrolled_window.hide()
		self._custom_entry = True
		return
		
	def undisplay_custom_entry(self):
		if self._custom_entry:
			message = "<html></html>"
			if self._RENDERRER==GTKHTML:
				self._document_lock.acquire()
				self._document.clear()
				self._document.open_stream("text/html")
				self._document.write_stream(message)
				self._document.close_stream()
				self._document_lock.release()
			elif self._RENDERRER==MOZILLA or self._RENDERRER == DEMOCRACY_MOZ or self._RENDERRER == GECKOEMBED:
				self._moz.open_stream("http://ywwg.com","text/html")
				self._moz.append_data(message, long(len(message)))
				self._moz.close_stream()	
			self._custom_entry = False

	def _htmlify_item(self, item):
		""" Take an item as returned from ptvDB and turn it into an HTML page.  Very messy at times,
		    but there are lots of alternate designs depending on the status of media. """
	
		#global download_status
		ret = []
		#ret.append('<div class="heading">')
		if item.has_key('title'):
			ret.append('<div class="stitle">%s</div>' % item['title'])
		if item.has_key('creator'):
			if item['creator']!="" and item['creator'] is not None:
				ret.append('By %s<br/>' % (item['creator'],))			
		if item['date'] != (0,0,0,0,0,0,0,0,0):
			ret.append('<div class="sdate">%s</div><br/>' % time.strftime('%a %b %d, %Y %X',time.localtime(item['date'])))
   		#ret.append('</div>')
		if item.has_key('media'):
			ret.append('<div class="media">')
			for medium in item['media']:
				if medium['download_status']==ptvDB.D_NOT_DOWNLOADED:    
					ret.append('<p>'+utils.html_command('download:',medium['media_id'])+' '+
									 utils.html_command('downloadqueue:',medium['media_id'])+
							         ' (%s)</p>' % (utils.format_size(medium['size'],)))
				elif medium['download_status'] == ptvDB.D_DOWNLOADING: 
					if medium.has_key('progress_message'): #downloading and we have a custom message
						ret.append('<p><i>'+medium['progress_message']+'</i> '+
						                    utils.html_command('pause:',medium['media_id'])+' '+
						                    utils.html_command('stop:',medium['media_id'])+'</p>')
					elif self._mm.has_downloader(medium['media_id']): #we have a downloader object
						downloader = self._mm.get_downloader(medium['media_id'])
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
					if self._mm.has_downloader(medium['media_id']):	
						downloader = self._mm.get_downloader(medium['media_id'])
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
					if self._mm.has_downloader(medium['media_id']):	
						downloader = self._mm.get_downloader(medium['media_id'])
						error_msg = downloader.message
					else:
						error_msg = _("There was an error downloading the file.")
					ret.append('<p>'+medium['url'][medium['url'].rfind('/')+1:]+': '+str(error_msg)+'  '+
											 utils.html_command('retry',medium['media_id'])+' '+
											 utils.html_command('tryresume:',medium['media_id'])+' '+
											 utils.html_command('cancel:',medium['media_id'])+'(%s)</p>' % (utils.format_size(medium['size']),))
			ret.append('</div>')
		ret.append('<div class="content">')
		if item.has_key('description'):
			ret.append('<br/>%s ' % item['description'])
		ret.append('</div>')
		if item.has_key('link'):
			ret.append('<br/><a href="'+item['link']+'">'+_("Full Entry...")+'</a><br />' )
		ret.append('</p>')
		return "".join(ret)

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
		style = self._scrolled_window.get_style()
		GRAY = "#%.2x%.2x%.2x;" % (
                style.base[gtk.STATE_INSENSITIVE].red / 256,
                style.base[gtk.STATE_INSENSITIVE].blue / 256,
                style.base[gtk.STATE_INSENSITIVE].green / 256)
		if self._RENDERRER==GTKHTML:
			self._document_lock.acquire()
			self._document.clear()
			self._document.open_stream("text/html")
			self._document.write_stream("""<html><style type="text/css">
            body { background-color: %s; }</style><body></body></html>""" % (GRAY,))
			self._document.close_stream()
			self._document_lock.release()
		elif self._RENDERRER==MOZILLA or self._RENDERRER == DEMOCRACY_MOZ or self._RENDERRER == GECKOEMBED:
			self._moz.open_stream("http://ywwg.com","text/html")
			message = """<html><style type="text/css">
            body { background-color: %s; }</style><body></body></html>""" % (GRAY,)
			self._moz.append_data(message, long(len(message)))
			self._moz.close_stream()		
		#self.scrolled_window.hide()
		self._custom_entry = True
		return
		
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
					data=data[:place]+self.style_start+data[place:place+l]+self.style_end+data[place+l:]
					data_u=data_u[:place]+self.style_start+data_u[place:place+l]+self.style_end+data_u[place+l:]
					place+=len(self.style_start)+len(term)+len(self.style_end)
		self.new_data+=data
