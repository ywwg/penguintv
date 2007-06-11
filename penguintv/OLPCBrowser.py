# need to set up hulahop before importing this file:
#
#import hulahop
#hulahop.startup(profile_path)
#import OLPCBrowser

import gobject

from hulahop.webview import WebView
import xpcom
from xpcom import components
from xpcom.components import interfaces

class ContentListener(gobject.GObject):
	_com_interfaces_ = interfaces.nsIURIContentListener
	
	__gsignals__ = {
		'open-uri': (gobject.SIGNAL_RUN_LAST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_STRING]))
		}
		
	def __init__(self):
		gobject.GObject.__init__(self)
	
	def canHandleContent(self, contentType, isContentPreferred, desiredContentType):
		return True
		
	def doContent(self, contentType, isContentPreferred, request, contentHandler):
		return False
		
	def isPreferred(self, contentType, desiredContentType):
		return True

	def onStartURIOpen(self, uri):
		result = self.emit('open-uri', uri.spec)
		if result:
			return True
		return False

class Browser(WebView):
	def __init__(self):
		WebView.__init__(self)
		
		browser = self.get_browser()
		self._renderer = browser.queryInterface(interfaces.nsIWebBrowserStream)
		
		cls = components.classes["@mozilla.org/network/io-service;1"]
		self._ioService = cls.getService(interfaces.nsIIOService)
		
		self._content_listener = ContentListener()
		self.__c = xpcom.server.WrapObject(self._content_listener, interfaces.nsIURIContentListener)
		# this isn't working, so __c is a member
		#weak_ref = xpcom.client.WeakReference(self.__c)
		browser.parentURIContentListener = self.__c
		
	def connect(self, signal, callback, *args):
		if signal == "open-uri":
			self._content_listener.connect("open-uri", callback, *args)
		else:
			WebView.connect(self, signal, callback, *args)
			
	def grab_focus(self):
		print "OLPCBrowser grabbing foooooooooooocus"
		self._chrome.setFocus()
		print "ok done"
			
	def open_stream(self, str_uri, mimetype):
		uri = self._ioService.newURI(str_uri, None, None)
		self._renderer.openStream(uri, mimetype)
		
	def append_data(self, data, data_len):
		self._renderer.appendToStream(data)
		
	def close_stream(self):
		self._renderer.closeStream()

