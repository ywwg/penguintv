# Written by Owen Williams
# see LICENSE for license information

#import penguintv
import gtk
#import urllib , urlparse loaded as needed
import socket
import gettext
import os.path
import traceback
import sys

#loaded as needed
#import feedparser
import HTMLParser 

import utils
import LoginDialog
if utils.HAS_PYXML:
	import itunes

_=gettext.gettext

class AddFeedDialog:
	def __init__(self,xml,app):
		self._xml = xml
		self._app = app
		self._window = xml.get_widget("window_add_feed")
		for key in dir(self.__class__):
			if key[:3] == 'on_':
				self._xml.signal_connect(key, getattr(self,key))
		self._feed_url_widget = self._xml.get_widget("feed_url")
		self._edit_tags_widget = self._xml.get_widget("edit_tags_widget")
		self._tag_hbox = self._xml.get_widget('tag_hbox')
		self._label = self._xml.get_widget('add_feed_label')
				
	def show(self):
		self._feed_url_widget.grab_focus()
		self._window.show()
		self._feed_url_widget.set_text("")
		self.set_location()
		self._edit_tags_widget.set_text("")
		#if utils.RUNNING_SUGAR:
		#	self._tag_hbox.hide()
		#	self._label.set_text(_('Please enter the URL of the feed you would like to add'))
	
	#ripped from straw
	def set_location(self):
		def _clipboard_cb(cboard, text, data=None):
			if text:
				if text[0:4] == "http":
					self._feed_url_widget.set_text(text)
				elif text[0:5] == "feed:":
					self._feed_url_widget.set_text(text[5:])
					        	
		clipboard = gtk.clipboard_get(selection="CLIPBOARD")
		clipboard.request_text(_clipboard_cb, None)
		
	def on_window_add_feed_delete_event(self, widget, event):
		return self._window.hide_on_delete()
		
	def hide(self):
		self._feed_url_widget.set_text("")
		self._window.hide()
		
	def finish(self):
		tags=[]
		if len(self._edit_tags_widget.get_text()) > 0:
			for tag in self._edit_tags_widget.get_text().split(','):
				tags.append(tag.strip())
		url = self._feed_url_widget.get_text()
		self._window.set_sensitive(False)
		while gtk.events_pending(): #make sure the sensitivity change goes through
			gtk.main_iteration()
		try:
			url,title = self._correct_url(url)
			if url is None:
				self._window.set_sensitive(True)
				return
			feed_id = self._app.add_feed(url,title)
		except AuthorizationFailed:
			dialog = gtk.Dialog(title=_("Authorization Required"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("You must specify a valid username and password in order to add this feed."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			response = dialog.run()
			dialog.hide()
			del dialog
			self._window.set_sensitive(True)
			return
		except AuthorizationCancelled:
			self._window.set_sensitive(True)
			return
		except BadFeedURL, e:
			dialog = gtk.Dialog(title=_("No Feed in Page"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))
			label = gtk.Label(_("PenguinTV couldn't find a feed in the web page you provided.\nYou will need to find the RSS feed link in the web page yourself.  Sorry."))
			dialog.vbox.pack_start(label, True, True, 0)
			label.show()
			response = dialog.run()
			dialog.hide()
			del dialog
			self._window.set_sensitive(True)
			return
		#except:
		#	self._window.set_sensitive(True)
		#	return 

		self._window.set_sensitive(True)
		if feed_id == -1:
			return #don't hide, give them a chance to try again.
		if len(tags) > 0:
			self._app.apply_tags_to_feed(feed_id, None, tags)
			#HACK: total hack to select the first tag they entered
			#(tag order not preserved in DB, so we can't use the standard API
			#self._app.main_window.select_feed(feed_id)
			self._app.main_window.set_active_filter(self._app.main_window.get_filter_index(tags[0]))
		self.hide()
				
	def on_button_ok_clicked(self,event):
		self.finish()
		
	def on_feed_url_activate(self, event):
		self.finish()
		
	def on_edit_tags_widget_activate(self, event):
		self.finish()
	
	def on_button_cancel_clicked(self,event):
		self.hide()
		
	def _correct_url(self,url):
		"""figures out if the url is a feed, or if it's actually a web page with a feed in it.  Also does http auth.  returns
		the correct url and a title"""
		
		import feedparser
		import HTMLParser
		import urlparse
		import urllib
		
		class my_url_opener(urllib.FancyURLopener):
			"""Little class to pop up a login window"""
			NONE = 0		
			FAILED = 1
			CANCELLED = 2

			def __init__(self, widget):
				urllib.FancyURLopener.__init__(self)
				self.widget = widget
				self.username = None
				self.password = None
				self.tries = 0
				self.failed_auth = 0 
				
			def prompt_user_passwd(self, host, realm):
				if self.tries==3:
					self.failed_auth = my_url_opener.FAILED
					return (None,None)
				d = LoginDialog.LoginDialog(self.widget)
				response = d.run()
				d.hide()
				if response != gtk.RESPONSE_OK:
					self.failed_auth = my_url_opener.CANCELLED
					return (None,None)
				self.username = d.username
				self.password = d.password
				self.tries+=1
				return (d.username, d.password)
				
		if utils.HAS_PYXML:
			if itunes.is_itunes_url(url):
				url = itunes.get_rss_from_itunes(url)
				print "got itunes url:",url
				
		urllib._urlopener = my_url_opener(gtk.glade.XML(self._app.glade_prefix+'/penguintv.glade', "dialog_login",'penguintv'))
		url_stream = None
		try:
			url_stream = urllib.urlopen(url)	
		except socket.timeout:
			raise BadFeedURL,"The website took too long to respond, and the connection timed out."
		except IOError, e:
			if "No such file or directory" in e:
				return self._correct_url("http://"+url)
			raise BadFeedURL,"There was an error loading the url."
		except Exception, e:
			raise BadFeedURL,"There was an error loading the url."
		title = url
		if urllib._urlopener.failed_auth == my_url_opener.FAILED:
			raise AuthorizationFailed
		if urllib._urlopener.failed_auth == my_url_opener.CANCELLED:
			raise AuthorizationCancelled
		if urllib._urlopener.username is not None:
			#build an auth-compatible url
			
			#scheme://netloc/path;parameters?query#fragment
			#http://www.cwi.nl:80/%7Eguido/Python.html
			#('http', 'www.cwi.nl:80', '/%7Eguido/Python.html', '', '', '')
			u_t = urlparse.urlparse(url)
			url = u_t[0]+"://"+str(urllib._urlopener.username)+":"+str(urllib._urlopener.password)+"@"+u_t[1]+u_t[2]
			title = u_t[0]+"://"+str(urllib._urlopener.username)+":"+("*"*len(urllib._urlopener.password))+"@"+u_t[1]+u_t[2]
			if len(u_t[3])>0:
				url=url+";"+u_t[3]
				title=title+";"+u_t[3]
			if len(u_t[4])>0:
				url=url+"?"+u_t[4]
				title=title+";"+u_t[4]
			if len(u_t[5])>0:
				url=url+"#"+u_t[5]
				title=title+";"+u_t[5]
			url_stream = urllib.urlopen(url)
		
		mimetype = url_stream.info()['Content-Type'].split(';')[0].strip()
		handled_mimetypes = ['application/atom+xml','application/rss+xml','application/rdf+xml','application/xml','text/xml', 'text/plain']
		if mimetype in handled_mimetypes:
			pass
		elif mimetype in ['text/html', 'application/xhtml+xml']:
			p = AltParser()
			try:
				for line in url_stream.readlines():
					p.feed(line)
					if p.head_end: #if we've gotten an error, we need the whole page
						break #otherwise the header is enough
					
				available_versions = p.alt_tags
				if len(available_versions)==0: #this might actually be a feed
					data = feedparser.parse(url)
					if len(data['channel']) == 0 or len(data['items']) == 0: #nope
						print "warning: no alt mimetypes:"+str(p.alt_tags)
						raise BadFeedURL
					else:
						pass #we're good
				else:
					newurl=""
					url_choices = []
					for mimetype, pos_url, t in available_versions:
						if mimetype in handled_mimetypes:
							#first clean it up
							if pos_url[:4]!="http": #maybe the url is not fully qualified (fix for metaphilm.com)
								if pos_url[0:2] == '//': #fix for gnomefiles.org
									pos_url = "http:"+pos_url
								elif pos_url[0] == '/': #fix for lwn.net.  Maybe we should do more proper base detection?
									parsed = urlparse.urlsplit(url)
									pos_url=parsed[0]+"://"+parsed[1]+pos_url
								else:
									pos_url=os.path.split(url)[0]+'/'+pos_url
									
							#now test sizes
							url_choices.append((pos_url, t))
							
					if len(url_choices) > 1:
						newurl, title = self._choose_url(url_choices)
					elif len(url_choices) == 1:
						newurl, title = url_choices[0]
					if newurl == "":
						print "warning: unhandled alt mimetypes:"+str(p.alt_tags)
						raise BadFeedURL
					url = newurl	
			except HTMLParser.HTMLParseError:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				error_msg = ""
				for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
					error_msg += s
				#sometimes this is actually the feed (pogue's posts @ nytimes.com)
				p = feedparser.parse(url)
				if len(p['channel']) == 0 or len(p['items']) == 0: #ok there really is a problem here
					print "htmlparser error:"
					print error_msg
					raise BadFeedURL
		else:
			print "warning: unhandled page mimetypes: "+str(mimetype)+"<--"
			raise BadFeedURL
		return (url,title)
		
	def _choose_url(self, url_list):
		dialog = gtk.Dialog(title=_("Choose Feed"), parent=None, flags=gtk.DIALOG_MODAL, buttons=(gtk.STOCK_CANCEL, gtk.RESPONSE_REJECT, gtk.STOCK_OK, gtk.RESPONSE_ACCEPT))

		label = gtk.Label(_("Please choose one of the feeds in this page"))
		dialog.vbox.pack_start(label, True, True, 0)
		
		list_widget = gtk.TreeView()
		model = gtk.ListStore(str, str)
		r = gtk.CellRendererText()
		c = gtk.TreeViewColumn('Feeds')
		c.pack_start(r)
		c.set_attributes(r, markup=1)
		list_widget.append_column(c)
		list_widget.set_model(model)
		dialog.vbox.pack_start(list_widget)
		
		for url, title in url_list:
			model.append([url, title])
		
		dialog.show_all()
		response = dialog.run()
		dialog.hide()
		del dialog
		if response == gtk.RESPONSE_ACCEPT:	
			selection = list_widget.get_selection()
			s_iter = selection.get_selected()[1]
			if s_iter is None:
				return None
			return list(model[s_iter])
		return None

class AltParser(HTMLParser.HTMLParser):
	def __init__(self):
		HTMLParser.HTMLParser.__init__(self)
		self.alt_tags=[]
		self.head_end=False
		
	def handle_starttag(self, tag, attrs):
		"""Signal when we get to a tag."""
		if tag=='link':
			attr_dic = {}
			for attr in attrs:
				attr_dic[attr[0]] = attr[1]
			try:
				if attr_dic['rel'] == 'alternate':
					if attr_dic['type'] in ['application/atom+xml','application/rss+xml','text/xml']:
						attr_dic.setdefault('title',attr_dic['href'])
						self.alt_tags.append((attr_dic['type'], attr_dic['href'], attr_dic['title']))
			except:
				pass

	def handle_endtag(self, tag):
		if tag == 'head':
			self.head_end=True


class AuthorizationFailed(Exception):
	def __init__(self):
		pass
	def __str__(self):
		return "Bad username or password"
		
class AuthorizationCancelled(Exception):
	def __init__(self):
		pass
	def __str__(self):
		return "Authorization cancelled"
		
class BadFeedURL(Exception):
	def __init__(self, message="couldn't get a feed from this url"):
		self.message = message
	def __str__(self):
		return self.message
