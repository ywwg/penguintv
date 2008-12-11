#imports copied from addfeeddialog

import gtk
import socket
import gettext
import os.path
import traceback
import sys

import logging

import HTMLParser 

import utils
from ptvDB import FF_NOAUTODOWNLOAD, FF_NOSEARCH, FF_NOAUTOEXPIRE, \
                  FF_NOTIFYUPDATES, FF_ADDNEWLINES, FF_MARKASREAD
import LoginDialog
if utils.HAS_PYXML:
	import itunes

_=gettext.gettext

def correct_url(url, glade_prefix):
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
			
	if url[0:5] == 'feed:':
		url = 'http:' + url[5:]
			
	if utils.HAS_PYXML:
		if itunes.is_itunes_url(url):
			try:
				url = itunes.get_rss_from_itunes(url)
			except:
				raise BadFeedURL,"Error trying to get itunes podcast"
			
	urllib._urlopener = my_url_opener(gtk.glade.XML(os.path.join(glade_prefix, 'dialogs.glade'), "dialog_login", 'penguintv'))
	url_stream = None
	try:
		#logging.debug("opening url: %s" % url)
		url_stream = urllib.urlopen(url)	
		#logging.debug("done")
	except socket.timeout:
		raise BadFeedURL,"The website took too long to respond, and the connection timed out."
	except IOError, e:
		if "No such file or directory" in e:
			return correct_url("http://"+url, glade_prefix)
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
					raise BadFeedURL, "warning: no alt mimetypes: %s" % str(p.alt_tags)
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
					newurl, title = _choose_url(url_choices)
					if newurl is None:
						raise BadFeedURL, "User canceled operation"
				elif len(url_choices) == 1:
					newurl, title = url_choices[0]
				if newurl == "":
					raise BadFeedURL, "warning: unhandled alt mimetypes: %s" % str(p.alt_tags)
				url = newurl	
		except HTMLParser.HTMLParseError:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			error_msg = ""
			for s in traceback.format_exception(exc_type, exc_value, exc_traceback):
				error_msg += s
			#sometimes this is actually the feed (pogue's posts @ nytimes.com)
			try:
				p = feedparser.parse(url)
			except Exception, e:
				raise BadFeedURL, "feedparser error: %s" % str(e)
			if len(p['channel']) == 0 or len(p['items']) == 0: #ok there really is a problem here
				raise BadFeedURL, "htmlparser error: %s" % error_msg
	else:
		raise BadFeedURL, "warning: unhandled page mimetypes: %s<--" % str(mimetype)
	return (url,title)
	
def _choose_url(url_list):
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
		model.append((url, title))
	
	dialog.show_all()
	response = dialog.run()
	dialog.hide()
	del dialog
	if response == gtk.RESPONSE_ACCEPT:	
		selection = list_widget.get_selection()
		s_iter = selection.get_selected()[1]
		if s_iter is None:
			return (None, None)
		return list(model[s_iter])
	return (None, None)

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
