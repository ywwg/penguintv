import gtk
import gobject

import ptvDB
from Downloader import FINISHED, FINISHED_AND_PLAY
import trayicon.TrayIcon
import IconManager
import utils
import MainWindow

NOTIFY_ENTRY = 0
NOTIFY_DOWNLOAD = 1

class PtvTrayIcon:
	def __init__(self, app, icon):
		self._app = app
		self._app.connect('feed-polled', self._feed_polled_cb)
		self._app.connect('notify-tags-changed', self._update_notification_feeds)
		self._app.connect('download-finished', self._download_finished_cb)
		self._app.connect('app-loaded', self._app_loaded_cb)
		self._app.connect('setting-changed', self.__setting_changed_cb)
		
		self._db = self._app.db
		self._updates = []
		self._updater_id = -1
		self._notification_feeds = []
		self._update_notification_feeds()
		self._icon_manager = IconManager.IconManager(self._db.home)
		
		self._show_notifications = self._db.get_setting(ptvDB.BOOL, 
		                            '/apps/penguintv/show_notifications', True)
		
		#Set up the right click menu
		menu = """
			<ui>
				<menubar name="Menubar">
					<menu action="Menu">
						<menuitem action="Play"/>
						<menuitem action="Pause"/>
						<separator/>
						<menuitem action="Refresh"/>
						<separator/>
						<menuitem action="ShowNotifications"/>
						<menuitem action="About"/>
						<menuitem action="Quit"/>
					</menu>
				</menubar>
			</ui>
		"""

		actions = [
			('Menu',  None, 'Menu'),
			('Play', gtk.STOCK_MEDIA_PLAY, _('_Play'), None, _('Play Media'), self.__play_cb),
			('Pause', gtk.STOCK_MEDIA_PAUSE, _('_Pause'), None, _('Pause Media'), self.__pause_cb),
			('Refresh', gtk.STOCK_REFRESH, _('_Refresh'), None, _('Refresh feeds'), self.__refresh_cb),
			('About', gtk.STOCK_ABOUT, _('_About'), None, _('About PenguinTV'), self.__about_cb),
			('Quit', gtk.STOCK_QUIT, _('_Quit'), None, _('Quit PenguinTV'), self.__quit_cb) ]

		actiongroup = gtk.ActionGroup('Actions')
		actiongroup.add_actions(actions)
		
		actions = [
			('ShowNotifications', None, _('Show Notifications'), 
			           None, _('Show feed and download updates'), 
			           self.__toggle_notifs_cb, self._show_notifications) ]
			           
		actiongroup.add_toggle_actions(actions)
		
		#Use UIManager to turn xml into gtk menu
		self.manager = gtk.UIManager()
		self.manager.insert_action_group(actiongroup, 0)
		self.manager.add_ui_from_string(menu)
		menu = self.manager.get_widget('/Menubar/Menu/About').props.parent
		
		show_always = self._db.get_setting(ptvDB.BOOL, '/apps/penguintv/show_notification_always', True)
		
		self._tray_icon = trayicon.TrayIcon.StatusTrayIcon(icon, menu, show_always)
		self._tray_icon.connect('notification-clicked', self._notification_clicked_cb)
		
		d = {'version': utils.VERSION}
		self._tray_icon.set_tooltip(_("PenguinTV Version %(version)s") % d)
		
		play, pause = self._get_playpause_menuitems()
		play.hide()
		pause.hide()
		self._player_showing = False
		
	def set_show_always(self, b):
		self._tray_icon.set_show_always(b)
		
	def set_tooltip(self, m):
		if len(m) == 0:
			d = {'version': utils.VERSION}
			self._tray_icon.set_tooltip(_("PenguinTV Version %(version)s") % d)
		else:
			self._tray_icon.set_tooltip(m)
			
	def clear_notifications(self):
		self._updates = []
		self._tray_icon.clear_notifications()
			
	def __setting_changed_cb(self, app, typ, datum, value):
		if datum == '/apps/penguintv/show_notifications':
			show_notifs_item = self.manager.get_widget('/Menubar/Menu/ShowNotifications')
			if value != show_notifs_item.get_active():
				show_notifs_item.set_active(value)
				self._show_notifications = value
				if value == False:
					self.clear_notifications()

	def _app_loaded_cb(self, app):
		play, pause = self._get_playpause_menuitems()
		if self._app.player.using_internal_player():
			self._app.player.connect_internal('playing', self.__gst_playing_cb)
			self._app.player.connect_internal('paused', self.__gst_paused_cb)
			
			if len(self._app.player.get_queue()) > 0:
				play.show()
				pause.hide()
			else:
				play.hide()
				pause.hide()
			
		self._app.main_window.connect('player-show', self.__gst_player_show_cb)
		self._app.main_window.connect('player-hide', self.__gst_player_hide_cb)
		
	def _update_notification_feeds(self, obj=None):
		self._notification_feeds = self._db.get_feeds_for_flag(ptvDB.FF_NOTIFYUPDATES)
				
	def _download_finished_cb(self, app, d):
		if (d.status == FINISHED or d.status == FINISHED_AND_PLAY) and \
		                                      self._show_notifications:
			entry = self._db.get_entry(d.media['entry_id'])
			entry_title = utils.my_quote(entry['title'])
			feed_title = self._db.get_feed_title(entry['feed_id'])
			feed_title = utils.my_quote(feed_title)
			icon = self._icon_manager.get_icon(entry['feed_id'])
			
			title = _("Download Complete")
			d2 = {'feed_title':feed_title,
				 'entry_title':entry_title,
				 'size': utils.format_size(d.total_size)}
			message = _("<b>%(feed_title)s:</b> %(entry_title)s" % d2)
			
			self._tray_icon.display_notification(title, message, icon, (NOTIFY_DOWNLOAD, d.media['media_id']))
					
	def _feed_polled_cb(self, app, feed_id, update_data):
		try:
			new_entries = update_data['new_entries']
		except:
			return
			
		## debug: guarantee notification 
		#if new_entries == 0:
		#	new_entries = 10
		
		if feed_id in self._notification_feeds and self._show_notifications:
			entries = self._db.get_entrylist(feed_id)[0:new_entries]
			entries = [(feed_id,e[0]) for e in entries]
			entries.reverse()
			if len(self._updates) >= 10:
				self._updates += entries[-2:]
			else:
				self._updates += entries[-7:] # seven max
			
			if self._updater_id == -1:
				self._updater_id = gobject.idle_add(self._push_update_handler)
			
	def _push_update_handler(self):
		if len(self._updates) == 0 or not self._show_notifications:
			self._updater_id = -1
			return False
		feed_id, entry_id = self._updates.pop(0)
		feed_title = self._db.get_feed_title(feed_id)
		entry = self._db.get_entry(entry_id)
		icon = self._icon_manager.get_icon(feed_id)
		
		feed_title = utils.my_quote(feed_title)
		entry_title = utils.my_quote(entry['title'])
		
		self._tray_icon.display_notification(feed_title, entry_title, icon, (NOTIFY_ENTRY, entry))
		return True
		
	def _notification_clicked_cb(self, obj, userdata):
		if userdata[0] == NOTIFY_DOWNLOAD:
			self._app.activate_link("play:"+str(userdata[1]))
		elif userdata[0] == NOTIFY_ENTRY:
			entry = userdata[1]
			#self._app.select_entry(entry['entry_id'])
			self._app.mark_entry_as_viewed(entry['entry_id'], entry['feed_id'])
			self._app.activate_link(entry['link'])
		
	def __quit_cb(self, data):
		self._app.do_quit()
		
	def __about_cb(self, data):
		self._app.main_window.on_about_activate(None)
		
	def __refresh_cb(self, data):
		self._app.poll_feeds()
		
	def __toggle_notifs_cb(self, toggleaction):
		show_notifs = toggleaction.get_active()
		self._db.set_setting(ptvDB.BOOL, '/apps/penguintv/show_notifications',
							 show_notifs)
		self._show_notifications = show_notifs
		if show_notifs == False:
			self.clear_notifications()
		
	def _get_playpause_menuitems(self):
		playitem = self.manager.get_widget('/Menubar/Menu/Play')
		pauseitem = self.manager.get_widget('/Menubar/Menu/Pause')
		return playitem, pauseitem
		
	def __play_cb(self, obj):
		def _expose_check_generator():
			"""Wait for player to become exposed, then play"""
			for i in range(0,10):
				if self._app.player.internal_player_exposed():
					self._app.player.control_internal("play")
					yield True
					break
				yield False
			yield False

		if self._app.player.using_internal_player():
			if not self._app.player.internal_player_exposed():
				self._app.main_window.notebook_select_page(MainWindow.N_PLAYER)
				gobject.timeout_add(200, _expose_check_generator().next)
			else:
				self._app.player.control_internal("play")
			
	def __pause_cb(self, obj):
		if self._app.player.using_internal_player():
			self._app.player.control_internal("pause")
			
	def __gst_player_show_cb(self, obj):
		if not self._player_showing:
			play, pause = self._get_playpause_menuitems()
			play.show()
			pause.hide()
			self._player_showing = True
		
	def __gst_player_hide_cb(self, obj):
		play, pause = self._get_playpause_menuitems()
		play.hide()
		pause.hide()
		self._player_showing = False
		
	def __gst_playing_cb(self, obj):
		play, pause = self._get_playpause_menuitems()
		play.hide()
		pause.show()
	
	def __gst_paused_cb(self, obj):
		play, pause = self._get_playpause_menuitems()
		play.show()
		pause.hide()
