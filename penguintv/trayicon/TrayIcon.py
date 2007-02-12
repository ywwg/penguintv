#!/usr/bin/env python

import os, sys
import traceback
#debug so utils imports
sys.path.append("/home/owen/penguintv/penguintv")

import time

import pygtk
pygtk.require("2.0")
import gtk 
import gobject

import utils

#try:
#	import pynotify
#	HAS_PYNOTIFY = True
#except ImportError:
#	HAS_PYNOTIFY = False
#	import SonataNotification

#pynotify crashes with version 0.1.0, can't use
#(can't even tell the difference!)
HAS_PYNOTIFY = False
import SonataNotification

MAX_HEIGHT = 96
MAX_WIDTH = 96
MIN_SIZE = 16
	
class StatusTrayIcon(gtk.StatusIcon):

	__gsignals__ = {
		'notification-clicked': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_PYOBJECT]))
	}

	def __init__(self, icon):
		#Init StatusIcon
		gtk.StatusIcon.__init__(self)
		
		if HAS_PYNOTIFY:
			#Initialize Notification
			pynotify.init("PenguinTVNotification")

		#Set up the right click menu
		menu = '''
			<ui>
				<menubar name="Menubar">
					<menu action="Menu">
						<menuitem action="About"/>
						<menuitem action="Quit"/>
					</menu>
				</menubar>
			</ui>
		'''

		actions = [
			('Menu',  None, 'Menu'),
			('About', gtk.STOCK_ABOUT, '_About', None, 'About PenguinTV', self.__about_cb),
			('Quit', gtk.STOCK_QUIT, '_Quit', None, 'Quit PenguinTV', self.__quit_cb) ]

		actiongroup = gtk.ActionGroup('Actions')
		actiongroup.add_actions(actions)

		#Use UIManager to turn xml into gtk menu
		self.manager = gtk.UIManager()
		self.manager.insert_action_group(actiongroup, 0)
		self.manager.add_ui_from_string(menu)
		self.menu = self.manager.get_widget('/Menubar/Menu/About').props.parent

		###Might want to run a check so we know that the icon is actually here
		###I noticed some error checking in MainWindow.py when setting the icon.
		###Perhaps we can do something similar here!?
		self.set_from_file(icon)

		self.set_tooltip('')
		self.set_visible(True)

		#Assign callbacks
		#self.connect('activate', self.__click_cb)
		#^put that in mainwindow or something
		self.connect('popup-menu', self.__popup_menu_cb)
		
		self._notifications = []
		self._updater_id = -1
		self._notification_displaying = False
		
	def display_notification(self, title, message, icon=None, userdata=None):
		self._notifications.append([title, message, icon, userdata])
		if self._updater_id == -1:
			self._updater_id = gobject.timeout_add(500, self._display_notification_handler)
			
	def _display_notification_handler(self):
		if len(self._notifications) == 0:
			self._updater_id = -1
			return False
		if self._notification_displaying:
			return True
		title, message, icon, userdata = self._notifications.pop(0)
		icon_pixbuf = self._scale_pixbuf(icon)
		if HAS_PYNOTIFY:
			self._display_pynotification(title, message, icon_pixbuf, userdata)
		else:
			self._display_sonatafication(title, message, icon_pixbuf, userdata)
		return True
			
	def _display_pynotification(self, title, message, icon=None, userdata=None):
		self._notification_displaying = True
		if icon is not None:
			notification = pynotify.Notification(title, message, None)
			notification.set_icon_from_pixbuf(icon)
		else:
			notification = pynotify.Notification(title, message, "info")
	
		notification.set_timeout(5000)
		notification.set_data('userdata', userdata)
		notification.add_action('default', 'Default Action', self.__pynotification_click_cb)
		notification.connect('closed', self.__notification_closed_cb)

		screen, rect, orient = self.get_geometry()
		notification.set_hint("x", rect.x +(rect.width / 2))
		notification.set_hint("y", rect.y +(rect.height / 2))
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

	def __pynotification_click_cb(self, notification, action):
		userdata = notification.get_data('userdata')
		self.emit('notification-clicked', userdata)
		notification.close()

	def __notification_closed_cb(self, widget):
		self._notification_displaying = False

	def __quit_cb(self, data):
		#gtk.main_quit()
		pass

	def __about_cb(self, data):
		dialog = gtk.AboutDialog()
		dialog.set_name(_('PenguinTV'))
		dialog.set_version(utils.VERSION)
		dialog.set_comments(_('A podcast, video blog, and rss aggregator.'))
		dialog.set_website('http://penguintv.sourceforge.net')
		dialog.run()
		dialog.destroy()

def _test_tray_icon(icon):
	icon.display_notification('title','message')
	icon.set_tooltip('yo yo yo!')
	icon.display_notification('title2','message2')
	icon.display_notification('title3','message3')
	icon.display_notification('title4','message4')
	return False
	
if __name__ == '__main__': # Here starts the dynamic part of the program 
	trayicon = StatusTrayIcon('/usr/share/pixmaps/penguintvicon.png')
	gobject.timeout_add(2000, _test_tray_icon, trayicon)
	
	gtk.main()
