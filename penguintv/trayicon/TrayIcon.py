#!/usr/bin/env python

import os, sys
import traceback
#debug so utils imports
#sys.path.append("/home/owen/penguintv/penguintv")
import logging

import time

import pygtk
pygtk.require("2.0")
import gtk 
import gobject

import utils

HAS_PYNOTIFY = False
if utils.RUNNING_HILDON:
	import hildon
elif utils.get_pynotify_ok():
	import pynotify
	HAS_PYNOTIFY = True
else:
	import SonataNotification

MAX_HEIGHT = 64
MAX_WIDTH = 64
MIN_SIZE = 16
	
class StatusTrayIcon(gtk.StatusIcon):

	__gsignals__ = {
		'notification-clicked': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT])),
	}

	def __init__(self, icon, menu=None, show_always=True, parent=None):
		#Init StatusIcon
		gtk.StatusIcon.__init__(self)
		
		if HAS_PYNOTIFY:
			#Initialize Notification
			pynotify.init("PenguinTVNotification")

		self.set_from_file(icon)

		self.set_tooltip('')
		
		if menu is not None:
			self.menu = menu
			self.connect('popup-menu', self.__popup_menu_cb)
		
		self._notifications = []
		self._updater_id = -1
		self._notification_displaying = False
		self._show_always = show_always
		self._parent = parent
		self.set_visible(self._show_always)
		
	def set_parent(self, p):
		self._parent = p
		
	def set_show_always(self, b):
		self._show_always = b
		if self._show_always:
			self.set_visible(True)
		elif not self._notification_displaying:
			self.set_visible(False)
		
	def display_notification(self, title, message, icon=None, userdata=None):
		self.set_visible(True)
		self._notifications.append([title, message, icon, userdata])
		if self._updater_id == -1:
			self._updater_id = gobject.timeout_add(1000, self._display_notification_handler)
			
	def clear_notifications(self):
		self._notifications = []
			
	def _display_notification_handler(self):
		if len(self._notifications) == 0:
			self._updater_id = -1
			return False
		if self._notification_displaying:
			return True
		title, message, icon, userdata = self._notifications.pop(0)
		icon_pixbuf = self._scale_pixbuf(icon)
		if utils.RUNNING_HILDON:
			self._display_hildonnotification(title, message, icon, userdata)
		elif HAS_PYNOTIFY:
			self._display_pynotification(title, message, icon_pixbuf, userdata)
		else:
			self._display_sonatafication(title, message, icon_pixbuf, userdata)
		return True
	
	def _display_hildonnotification(self, title, message, icon=None, userdata=None):
		self._notification_displaying = True
		if self._parent is None:
			logging.info("not showing notification, no parent widget")
		logging.debug("showing notification: %s %s" % (title, message))
		try:
			b = hildon.hildon_banner_show_information_with_markup(self._parent, icon, "<b>%s</b>\n%s" % (title, message))
		except TypeError:
			#banner bug not fixed yet
			b = hildon.hildon_banner_show_information_with_markup(self._parent, "NULL", "<b>%s</b>\n%s" % (title, message))
		if icon is not None:
			b.set_icon_from_file(icon)
		b.set_timeout(3000)
		def done_showing():
			self._notification_displaying = False
			return False
		gobject.timeout_add(5000, done_showing)
			
	def _display_pynotification(self, title, message, icon=None, userdata=None):
		#don't need this, pynotifications can stack up
		#self._notification_displaying = True
		#logging.debug("displaying pynotification: %s %s" % (title, message))
		if icon is not None:
			notification = pynotify.Notification(title, message, None)
			notification.set_icon_from_pixbuf(icon)
		else:
			notification = pynotify.Notification(title, message, "info")
	
		notification.set_timeout(3000)
		notification.set_data('userdata', userdata)
		#setting a default action used to work, but now it causes the notification to become
		#a boring OK/Cancel dialog box, which is weird
		#notification.add_action('default', 'Default Action', self.__pynotification_click_cb)
		#notification.connect('closed', self.__notification_closed_cb)

		#screen, rect, orient = self.get_geometry()
		#notification.set_hint("x", rect.x +(rect.width / 2))
		#notification.set_hint("y", rect.y +(rect.height / 2))
		notification.show()
		
	def _display_sonatafication(self, title, message, icon=None, userdata=None):
		self._notification_displaying = True
		notification = SonataNotification.TrayIconTips(self)
		notification.set_timeout(5000)
		notification.display_notification(title, message, icon)
		notification.connect('hide', self.__notification_closed_cb)
		notification.connect('clicked', self.__sonatafication_click_cb, userdata)
		notification.connect('closed', self.__notification_closed_cb)
		
	def _scale_pixbuf(self, filename):
		try:
			p = gtk.gdk.pixbuf_new_from_file(filename)
		except:
			p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, MIN_SIZE, MIN_SIZE)
			p.fill(0xffffff00)
			return p
		height = p.get_height()
		width = p.get_width()
		if height > MAX_HEIGHT:
			height = MAX_HEIGHT
			width = p.get_width() * height / p.get_height()
		if width > MAX_WIDTH:
			width = MAX_WIDTH
			height = p.get_height() * width / p.get_width()
		if height != p.get_height() or width != p.get_width():
			p = gtk.gdk.pixbuf_new_from_file_at_size(filename, width, height)
		return p

	###Callbacks
	def __popup_menu_cb(self, status, button, time):
		self.menu.popup(None, None, None, button, time)
		
	def __sonatafication_click_cb(self, notification, action, userdata):
		self.emit('notification-clicked', userdata)
		notification.close()

	def __pynotification_click_cb(self, notification, action):
		userdata = notification.get_data('userdata')
		self.emit('notification-clicked', userdata)
		notification.close()

	def __notification_closed_cb(self, widget):
		self._notification_displaying = False
		if not self._show_always:
			self.set_visible(False)

	def __menu_cb(self, data):
		action = data.get_accel_path().split("/")[-1]
		self.emit('menu-clicked', action)

def _test_tray_icon(icon):
	icon.display_notification('title','message','/home/owen/src/penguintv/share/penguintvicon.png')
	icon.set_tooltip('yo yo yo!')
	icon.display_notification('title2','message2','/home/owen/src/penguintv/share/penguintvicon.png')
	icon.display_notification('title3','message3','/home/owen/src/penguintv/share/penguintvicon.png')
	icon.display_notification('title4','message4','/home/owen/src/penguintv/share/penguintvicon.png')
	return False
	
if __name__ == '__main__': # Here starts the dynamic part of the program 
	h = None
	if utils.RUNNING_HILDON:
		h = hildon.Window()
		l = gtk.Label("hello world")
		h.add(l)
		h.show_all()
		
	trayicon = StatusTrayIcon('/home/owen/src/penguintv/share/penguintvicon.png', parent=h)
	gobject.timeout_add(2000, _test_tray_icon, trayicon)
	
	gtk.main()
