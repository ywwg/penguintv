import gtk
import gobject

class TrayIconTips(gtk.Window):
	"""Custom tooltips derived from gtk.Window() that allow for markup text and multiple widgets, e.g. a progress bar. ;)"""
	MARGIN = 4
	
	__gsignals__ = {
		'clicked': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([gobject.TYPE_INT])),
		'closed': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([]))
	}

	def __init__(self, widget=None):
		gtk.Window.__init__(self, gtk.WINDOW_POPUP)
		
		if widget is not None:
			self._pos_widget = widget
		
		# from gtktooltips.c:gtk_tooltips_force_window
		self.set_app_paintable(True)
		self.set_resizable(False)
		self.set_name("gtk-tooltips")
		self.connect('expose-event', self._on__expose_event)
		self.connect('event-after', self._motion_cb)
		self.connect('button_press_event', self.__button_press_cb)
		self.set_events(gtk.gdk.EXPOSURE_MASK |
				gtk.gdk.LEAVE_NOTIFY_MASK |
				gtk.gdk.BUTTON_PRESS_MASK)

		self._timeout = 5000
		self._hide_ok = True
		self.use_notifications_location = False
		self.notifications_location = 0
		
		#basic notification widget
		hbox = gtk.HBox()
		hbox.set_spacing(5)
		self._image = gtk.Image()
		hbox.pack_start(self._image, False)

		vbox = gtk.VBox()		
		self._title = gtk.Label()
		self._title.set_justify(gtk.JUSTIFY_LEFT)
		self._title.set_alignment(0, .5)
		vbox.pack_start(self._title, False)
		self._text = gtk.Label()
		self._text.set_justify(gtk.JUSTIFY_LEFT)
		self._text.set_alignment(0, .5)
		vbox.pack_start(self._text, True)
		
		hbox.pack_start(vbox, True, True)
		
		vbox = gtk.VBox()
		img = gtk.Image()
		img.set_from_stock("gtk-close", gtk.ICON_SIZE_MENU)
		button = gtk.Button("")
		button.set_image(img)
		button.connect('clicked', self.__close_clicked_cb)
		vbox.pack_start(button, False, False)
		label = gtk.Label("")
		vbox.pack_start(label, True, True)
		hbox.pack_start(vbox, False, False)
		
		align = gtk.Alignment(0,0,1,1)
		align.set_padding(10,10,10,10)
		align.add(hbox)
		
		self.add(align)
		align.show_all()
		
		self.set_size_request(500,96)

	def _calculate_pos(self, widget):
		icon_screen, icon_rect, icon_orient = widget.get_geometry()
		x = icon_rect[0]
		y = icon_rect[1]
		width = icon_rect[2]
		height = icon_rect[3]
		w, h = self.size_request()

		screen = self.get_screen()
		pointer_screen, px, py, _ = screen.get_display().get_pointer()
		if pointer_screen != screen:
			px = x
			py = y
		try:
			# Use the monitor that the systemtray icon is on
			monitor_num = screen.get_monitor_at_point(x, y)
		except:
			# No systemtray icon, use the monitor that the pointer is on
			monitor_num = screen.get_monitor_at_point(px, py)
		monitor = screen.get_monitor_geometry(monitor_num)

		try:
			# If the tooltip goes off the screen horizontally, realign it so that
			# it all displays.
			if (x + w) > monitor.x + monitor.width:
				x = monitor.x + monitor.width - w
			# If the tooltip goes off the screen vertically (i.e. the system tray
			# icon is on the bottom of the screen), realign the icon so that it
			# shows above the icon.
			if ((y + h + height + self.MARGIN) >
				monitor.y + monitor.height):
				y = y - h - self.MARGIN
			else:
				y = y + height + self.MARGIN
		except:
			pass

		if self.use_notifications_location == False:
			try:
				return x, y
			except:
				#Fallback to top-left:
				return monitor.x, monitor.y
		elif self.notifications_location == 0:
			try:
				return x, y
			except:
				#Fallback to top-left:
				return monitor.x, monitor.y
		elif self.notifications_location == 1:
			return monitor.x, monitor.y
		elif self.notifications_location == 2:
			return monitor.x + monitor.width - w, monitor.y
		elif self.notifications_location == 3:
			return monitor.x, monitor.y + monitor.height - h
		elif self.notifications_location == 4:
			return monitor.x + monitor.width - w, monitor.y + monitor.height - h

	def _motion_cb (self, widget, event):
		if event.type == gtk.gdk.LEAVE_NOTIFY:
			self._hide_ok = True
		if event.type == gtk.gdk.ENTER_NOTIFY:
			self._hide_ok = False
			
	def __button_press_cb(self, widget, event):
		self.emit('clicked', 1)
		
	def __close_clicked_cb(self, widget):
		self.hide()
		self.emit('closed')

	# from gtktooltips.c:gtk_tooltips_paint_window
	def _on__expose_event(self, window, event):
		w, h = window.size_request()
		window.style.paint_flat_box(window.window,
									gtk.STATE_NORMAL, gtk.SHADOW_OUT,
									None, window, "tooltip",
									0, 0, w, h)
		return False

	def _real_display(self, widget):
		x, y = self._calculate_pos(widget)
		self.move(x, y)
		self.show()

	# Public API
	def close(self):
		gtk.Window.hide(self)
		self.notif_handler = None

	def hide(self):
		if self._hide_ok:
			gtk.Window.hide(self)
			self.notif_handler = None
			return False
		else:
			return True
		
	def set_timeout(self, timeout):
		self._timeout = timeout
		
	def display_notification(self, title, text, icon=None):
		if icon is not None:
			self._image.set_from_pixbuf(icon)
		else:
			self._image.set_from_stock('gtk-dialog-info', gtk.ICON_SIZE_DIALOG)
		self._image.show()
		self._title.set_markup('<span size="x-large"><b>'+title+'</b></span>')
		self._text.set_markup(text)

		self._real_display(self._pos_widget)
		gobject.timeout_add(self._timeout, self.hide)
