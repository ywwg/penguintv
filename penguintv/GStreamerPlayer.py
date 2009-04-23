#!/usr/bin/env python
#a basic gstreamer-based player.  Can run standalone or inside the widget of your choice
#much help from the mesk player code, totem, and most of all, google.com/codesearch
#Copyright 2006, Owen Williams
#License: GPL

import sys,os,os.path
import pickle
import urllib
import getopt
from math import ceil, floor

import pygst
pygst.require("0.10")
import gst
from gst.extend.discoverer import Discoverer

import pygtk
pygtk.require("2.0")
import gtk 
import gobject

import locale
import gettext
import logging
logging.basicConfig(level=logging.DEBUG)

#locale.setlocale(locale.LC_ALL, '')
_=gettext.gettext

if os.environ.has_key('SUGAR_PENGUINTV'):
	RUNNING_SUGAR = True
else:
	RUNNING_SUGAR = False
	
try:
	import hildon
	RUNNING_HILDON = True
except:
	RUNNING_HILDON = False

class GStreamerPlayer(gobject.GObject):

	__gsignals__ = {
		'playing': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([])),
		'paused': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([])),
		'tick': (gobject.SIGNAL_RUN_FIRST, 
                           gobject.TYPE_NONE, 
                           ([])),
        'item-queued': (gobject.SIGNAL_RUN_LAST, 
        				gobject.TYPE_NONE, 
        				[str, str, gobject.TYPE_PYOBJECT]),
        'item-not-supported': (gobject.SIGNAL_RUN_LAST, 
        					   gobject.TYPE_NONE, 
        					   [str, str, gobject.TYPE_PYOBJECT]),
        'items-removed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, [])
	}

	def __init__(self, layout_dock, playlist, tick_interval=1):
		gobject.GObject.__init__(self)
		self._layout_dock = layout_dock
		self._playlist_name = playlist
		self._media_duration = 0
		self._media_position = 0
		self._last_tick = 0
		self._tick_interval = tick_interval * gst.SECOND
		self._last_index = -1
		self._current_index = 0 #index to tree model
		self._resized_pane = False
		self.__no_seek = False
		self.__is_exposed = False
		self._x_overlay = None
		self._prepare_save = False
		self._do_stop_resume = False
		self._has_video = False
		self._using_playbin2 = True
		
		self._error_dialog = GStreamerErrorDialog()
		
		gobject.timeout_add(300000, self._periodic_save_cb)
		
	###public functions###
		
	def Show(self):
		main_vbox = gtk.VBox()
		
		vbox = gtk.VBox()
		self._hpaned = gtk.HPaned()
		self._player_vbox = gtk.VBox()
		self._drawing_area = gtk.DrawingArea()
		
		color = gtk.gdk.Color(0, 0, 0)
		self._drawing_area.modify_bg(gtk.STATE_NORMAL, color)
		self._drawing_area.connect('expose-event', self._on_drawing_area_exposed)
		self._player_vbox.pack_start(self._drawing_area)
		vbox.pack_start(self._player_vbox, True)
		
		self._seek_scale = gtk.HScale()
		self._seek_scale.set_range(0, 1)
		self._seek_scale.set_draw_value(False)
		self._seek_scale.connect('value-changed', self._on_seek_value_changed)
		vbox.pack_start(self._seek_scale, False)
		
		self._hpaned.add1(vbox)
		
		self._sidepane_vbox = gtk.VBox()
		s_w = gtk.ScrolledWindow()
		s_w.set_shadow_type(gtk.SHADOW_IN)
		s_w.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
		if RUNNING_HILDON:
			hildon.hildon_helper_set_thumb_scrollbar(s_w, True)
		self._queue_listview = gtk.TreeView()
		model = gtk.ListStore(str, str, str, gobject.TYPE_PYOBJECT) #uri, title to display, current track indicator, user data
		self._queue_listview.set_model(model)
		
		column = gtk.TreeViewColumn(_(""))
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, markup=2)
		self._queue_listview.append_column(column)
		
		column = gtk.TreeViewColumn(_("Playlist"))
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, markup=1)
		self._queue_listview.append_column(column)
		self._queue_listview.connect('row-activated', self._on_queue_row_activated)
		self._queue_listview.connect('button-press-event', self._on_queue_row_button_press)
		self._queue_listview.get_selection().set_mode(gtk.SELECTION_MULTIPLE)
		#dnd reorder
		self._TARGET_TYPE_REORDER = 80
		self._TARGET_TYPE_URI_LIST = 81
		drop_types = [('reorder',gtk.TARGET_SAME_WIDGET, self._TARGET_TYPE_REORDER),
					  ('text/uri-list',0,self._TARGET_TYPE_URI_LIST)]
		#for removing items from favorites and reordering
		self._queue_listview.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, drop_types, gtk.gdk.ACTION_MOVE)
		self._queue_listview.enable_model_drag_dest(drop_types, gtk.gdk.ACTION_DEFAULT)
		self._queue_listview.connect('drag-data-received', self._on_queue_drag_data_received)
		
		s_w.add(self._queue_listview)
		self._sidepane_vbox.pack_start(s_w, True)
		
		button = gtk.Button(stock='gtk-remove')
		button.connect("clicked", self._on_remove_clicked)
		if not RUNNING_HILDON:
			button_box = gtk.HButtonBox()
			button_box.set_property('layout-style', gtk.BUTTONBOX_END)
			button_box.add(button)
			self._sidepane_vbox.pack_start(button_box, False)
		else:
			list_bottom_hbox = gtk.HBox(False)
			list_bottom_hbox.pack_start(button, False)
			self._sidepane_vbox.pack_start(list_bottom_hbox, False)
		
		self._hpaned.add2(self._sidepane_vbox)
		
		main_vbox.add(self._hpaned)
		
		self._controls_hbox = gtk.HBox()
		self._controls_hbox.set_spacing(6)
		
		button_box = gtk.HButtonBox()
		button_box.set_homogeneous(False)
		button_box.set_property('layout-style', gtk.BUTTONBOX_START)

		if not RUNNING_HILDON:
			image = gtk.Image()
			image.set_from_stock("gtk-media-previous",gtk.ICON_SIZE_BUTTON)
			button = gtk.Button("")
			button.set_image(image)
		else:
			button = gtk.Button()
			label = gtk.Label(_("Prev"))
			label.set_use_markup(True)
			button.add(label)
			label.show()
		button.set_property('can-focus', False)
		button.connect("clicked", self._on_prev_clicked)
		button_box.pack_start(button, True, True)
		
		if not RUNNING_HILDON:
			image = gtk.Image()
			image.set_from_stock("gtk-media-rewind",gtk.ICON_SIZE_BUTTON)
			button = gtk.Button("")
			button.set_image(image)
		else:
			button = gtk.Button(_("Rew"))
		button.set_property('can-focus', False)
		button.connect("clicked", self._on_rewind_clicked)
		button_box.pack_start(button, True, True)
		
		if not RUNNING_HILDON:
			image = gtk.Image()
			image.set_from_stock("gtk-media-play",gtk.ICON_SIZE_BUTTON)
			self._play_pause_button = gtk.Button("")
			self._play_pause_button.set_image(image)
		else:
			self._play_pause_button = gtk.Button(_("Play"))
		self._play_pause_button.set_property('can-focus', False)
		self._play_pause_button.connect("clicked", self._on_play_pause_toggle_clicked)
		button_box.pack_start(self._play_pause_button, True, True)
	
		if not RUNNING_HILDON:
			image = gtk.Image()
			image.set_from_stock("gtk-media-stop",gtk.ICON_SIZE_BUTTON)
			button = gtk.Button("")
			button.set_image(image)
		else:
			button = gtk.Button(_("Stop"))
		button.set_property('can-focus', False)
		button.connect("clicked", self._on_stop_clicked)
		button_box.pack_start(button, True, True)
		
		if not RUNNING_HILDON:
			image = gtk.Image()
			image.set_from_stock("gtk-media-forward",gtk.ICON_SIZE_BUTTON)
			button = gtk.Button("")
			button.set_image(image)
		else:
			button = gtk.Button(_("FF"))
		button.set_property('can-focus', False)
		button.connect("clicked", self._on_forward_clicked)
		button_box.pack_start(button, True, True)
		
		if not RUNNING_HILDON:
			image = gtk.Image()
			image.set_from_stock("gtk-media-next",gtk.ICON_SIZE_BUTTON)
			button = gtk.Button("")
			button.set_image(image)
		else:
			button = gtk.Button(_("Next"))
		button.set_property('can-focus', False)
		button.connect("clicked", self._on_next_clicked)
		button_box.pack_start(button, True, True)
		
		self._controls_hbox.pack_start(button_box, False)
		
		self._time_label = gtk.Label("")
		self._time_label.set_alignment(0.0,0.5)
		
		if not RUNNING_HILDON:
			self._controls_hbox.pack_start(self._time_label, True)
		else:
			list_bottom_hbox.pack_start(self._time_label, True)
			list_bottom_hbox.reorder_child(self._time_label, 0)
		
		main_vbox.pack_start(self._controls_hbox, False)
		self._layout_dock.add(main_vbox)
		
		self.gstreamer_init()
	
		self._layout_dock.show_all()

	def gstreamer_init(self):
		if self._using_playbin2:
			try:
				self._pipeline = gst.element_factory_make("playbin2", "ptv_bin")
			except:
				self._using_playbin2 = False
				self._pipeline = gst.element_factory_make("playbin", "ptv_bin")
		else:
			self._pipeline = gst.element_factory_make("playbin", "ptv_bin")
		#use default audio sink, but get our own video sink
		self._v_sink = self._get_video_sink()
		self._pipeline.set_property('video-sink',self._v_sink)
		#if RUNNING_HILDON:
		#	self._mp3_sink = gst.element_factory_make('dspmp3sink', 'mp3sink')
		#	self._pcm_sink = gst.element_factory_make('dsppcmsink', 'pcmsink')
			
		bus = self._pipeline.get_bus()
		bus.add_signal_watch()
		bus.connect('message', self._on_gst_message)
		#bus.connect('sync-message::element', self._on_sync_message)

	def get_widget(self):
		return self._layout_dock
		
	def is_exposed(self):
		return self.__is_exposed
		
	def has_video(self):
		return self._has_video
		
	def detach(self):
		"""video window can detach.  queue stays embedded"""
		pass
	
	def reattach(self):
		"""hides external window and reinits embedded window"""
		pass
		
	def toggle_controls(self, show_controls):
		if not show_controls:
			self._controls_hbox.show()
			self._seek_scale.show()
			self._sidepane_vbox.show()
		else:
			self._controls_hbox.hide()
			self._seek_scale.hide()
			self._sidepane_vbox.hide()
			
	def load(self):
		try:
			playlist = open(self._playlist_name, 'r')
		except:
			print "error reading playlist"
			return
			
		self._current_index = pickle.load(playlist)
		self._last_index = -1
		self._media_position = pickle.load(playlist)
		self._media_duration = pickle.load(playlist)
		l = pickle.load(playlist)
		model = self._queue_listview.get_model()
		for uri, name, userdata in l:
			model.append([uri, name, "", userdata])
			filename = gst.uri_get_location(uri)
			self.emit('item-queued', filename, name, userdata)
		if self.__is_exposed:
			if not self._seek_to_saved_position():
				#retry once
				self._seek_to_saved_position()
		playlist.close()
		
	def save(self):
		"""saves playlist"""
		try:
			playlist = open(self._playlist_name, 'w')
		except:
			print "error writing playlist"
			return
			
		pickle.dump(self._current_index, playlist)
		pickle.dump(self._media_position, playlist)
		pickle.dump(self._media_duration, playlist)
		l = []
		for uri, name, current, userdata in self._queue_listview.get_model():
			l.append([uri, name, userdata])
		pickle.dump(l, playlist)
		playlist.close()
		
	def queue_file(self, filename, name=None, userdata=None):
		try:
			os.stat(filename)
		except:
			print "file not found",filename
			return

		if name is None:
			name = os.path.split(filename)[1]
		
		if RUNNING_HILDON:
			ext = os.path.splitext(filename)[1][1:]
			known_good = ['mp3', 'wav', 'm4a', 'wma', 'mpg', 'avi', '3gp', 'rm', 'asf', 'mp4']
			try:
				gst.element_factory_make("oggdemux", "test")
				known_good += ['ogg']
			except:
				pass
				
			self._on_type_discovered(None, ext in known_good, filename, name, userdata)
		else:
			#thanks gstfile.py
			d = Discoverer(filename)
			d.connect('discovered', self._on_type_discovered, filename, name, userdata)
			d.discover()
			
	def unqueue(self, filename=None, userdata=None):
		model = self._queue_listview.get_model()
		
		iter_list = []
		
		if filename is not None:
			logging.warning("UNTESTED CODE:")
			it = model.get_iter_first()
			while it is not None:
				data = model.get(it, 0)[0]
				logging.debug("%s %s" % (str(filename), str(data)))
				if data == "file://" + filename:
					iter_list.append(it)
				it = model.iter_next(it)
				
			if len(iter_list) > 0:
				self._remove_items(iter_list)
				
		if userdata is not None:
			it = model.get_iter_first()
			while it is not None:
				data = model.get(it, 3)[0]
				if data == userdata:
					iter_list.append(it)
				it = model.iter_next(it)
				
			if len(iter_list) > 0:
				self._remove_items(iter_list)
				
	def relocate_media(self, old_dir, new_dir):
		if old_dir[-1] == '/' or old_dir[-1] == '\\':
			old_dir = old_dir[:-1]
			
		if new_dir[-1] == '/' or new_dir[-1] == '\\':
			new_dir = new_dir[:-1]
	
		model = self._queue_listview.get_model()
		if len(model) == 0:
			return
			
		self.stop()
			
		for row in model:
			if row[0].startswith("file://" + old_dir):
				row[0] = row[0].replace(old_dir, new_dir)
			
	def get_queue_count(self):
		return len(self._queue_listview.get_model())
		
	def get_queue(self):
		return list(self._queue_listview.get_model())
		
	def play_pause_toggle(self):
		if self._pipeline.get_state()[1] == gst.STATE_PLAYING:
			self.pause()
		else:
			self.play()
		
	def play(self, notick=False):
		model = self._queue_listview.get_model()
		if len(model) == 0:
			return
		if self._current_index < 0: self._current_index = 0
		uri, title, current, userdata = list(model[self._current_index])
		if self._last_index != self._current_index:
			self._last_index = self._current_index
			selection = self._queue_listview.get_selection()
			i = -1
			for row in model:
				i+=1
				if i == self._current_index:
					row[2] = "&#8226;" #bullet
				else:
					row[2] = ""
			if not self._ready_new_uri(uri):
				return
			self._prepare_display()
			self._prepare_save = True
		else:
			if self._do_stop_resume:
				self._do_stop_resume = False
				self._prepare_display()
				if not self._seek_to_saved_position():
					#gstreamer error, recall ourselves
					self.play()
					return
		self._pipeline.set_state(gst.STATE_PLAYING)
		if not RUNNING_HILDON:
			image = gtk.Image()
			image.set_from_stock("gtk-media-pause",gtk.ICON_SIZE_BUTTON)
			self._play_pause_button.set_image(image)
		else:
			self._play_pause_button.set_label(_("Pause"))
		self._media_duration = -1
		if not notick:
			gobject.timeout_add(500, self._tick)
		#self._pipeline.get_property('stream-info')
		self.emit('playing')
		
	def pause(self):
		try: self._media_position = self._pipeline.query_position(gst.FORMAT_TIME)[0]
		except: pass
		self._pipeline.set_state(gst.STATE_PAUSED)
		if not RUNNING_HILDON:
			image = gtk.Image()
			image.set_from_stock("gtk-media-play",gtk.ICON_SIZE_BUTTON)
			self._play_pause_button.set_image(image)
		else:
			self._play_pause_button.set_label(_("Play"))
		self.emit('paused')
		
	def stop(self):
		#this should release the port, but I hate having a stop button on a computer
		#because it doesn't make sense.
		#unbreak: when video is stopped, we need this option to keep the window black
		self._drawing_area.set_flags(gtk.DOUBLE_BUFFERED)
		try: self._media_position = self._pipeline.query_position(gst.FORMAT_TIME)[0]
		except: pass
		self._pipeline.set_state(gst.STATE_READY)
		#self._last_index = -1
		self._seek_scale.set_range(0,1)
		self._seek_scale.set_value(0)
		self._do_stop_resume = True
		if not RUNNING_HILDON:
			image = gtk.Image()
			image.set_from_stock("gtk-media-play",gtk.ICON_SIZE_BUTTON)
			self._play_pause_button.set_image(image)
		else:
			self._play_pause_button.set_label(_("Play"))
	
		if 'gstxvimagesink' in str(type(self._v_sink)).lower():
			#release the xv port
			self._pipeline.unlink(self._v_sink)
			self._v_sink.set_state(gst.STATE_NULL)
		self.emit('paused')
			
	def ff(self):
		if self._pipeline.get_state()[1] != gst.STATE_PLAYING:
			return
		new_pos = self._media_position + 15 * gst.SECOND
		if new_pos > self._media_duration:
			new_pos = self._media_duration
		self.seek(new_pos)
		
	def rew(self):
		if self._pipeline.get_state()[1] != gst.STATE_PLAYING:
			return
		new_pos = self._media_position - 5 * gst.SECOND
		if new_pos < 0:
			new_pos = 0
		self.seek(new_pos)
		
	def next(self):
		model = self._queue_listview.get_model()
		selection = self._queue_listview.get_selection()
		self._pipeline.set_state(gst.STATE_READY)
		self._current_index += 1
		if self._current_index >= len(model):
			self._current_index = 0
		
		selection.unselect_all()
		selection.select_path((self._current_index,))
		
		self._seek_scale.set_range(0,1)
		self._seek_scale.set_value(0)
		self._do_stop_resume = False
		self.play()
		
	def prev(self):
		selection = self._queue_listview.get_selection()
		self._pipeline.set_state(gst.STATE_READY)
		self._current_index -= 1
		if self._current_index <= 0:
			self._current_index = 0
			self.seek(0)
		selection.unselect_all()
		selection.select_path((self._current_index,))
		self._seek_scale.set_range(0,1)
		self._seek_scale.set_value(0)
		self._do_stop_resume = False
		self.play()
		
	def finish(self):
		self.save()
		self._pipeline.set_state(gst.STATE_READY)
		
	def seek(self, time):
		return self._pipeline.seek(1.0, gst.FORMAT_TIME,
							gst.SEEK_FLAG_FLUSH | gst.SEEK_FLAG_ACCURATE,
							gst.SEEK_TYPE_SET, time,
							gst.SEEK_TYPE_NONE, 0)
							
	def vol_up(self):
		old_vol = floor(self._pipeline.get_property('volume'))
		if old_vol < 10:
			self._pipeline.set_property('volume', old_vol + 1)
		
	def vol_down(self):
		old_vol = ceil(self._pipeline.get_property('volume'))
		if old_vol > 0: 
			self._pipeline.set_property('volume', old_vol - 1)
							
	###handlers###
	
	def _on_gst_message(self, bus, message):
		#print str(message)
		if message.type == gst.MESSAGE_STATE_CHANGED:
			prev, new, pending = message.parse_state_changed()
			if new == gst.STATE_PLAYING:
				if not self._resized_pane:
					self._resize_pane()
		if message.type == gst.MESSAGE_EOS:
			model = self._queue_listview.get_model()
			if self._current_index < len(model) - 1:
				self.next()
			else:
				self.stop()
		elif message.type == gst.MESSAGE_ERROR:
			gerror, debug = message.parse_error()
			logging.error("GSTREAMER ERROR: %s" % debug)
			if not RUNNING_HILDON:
				self._error_dialog.show_error(debug)
		

		
	def _on_play_clicked(self, b): self.play()
		
	def _on_pause_clicked(self, b): self.pause()
	
	def _on_play_pause_toggle_clicked(self, b): self.play_pause_toggle()
	
	def _on_stop_clicked(self, b): self.stop()
		
	def _on_rewind_clicked(self, b): self.rew()
		
	def _on_forward_clicked(self, b): self.ff()
	
	def _on_next_clicked(self, b): self.next()
	
	def _on_prev_clicked(self, b): self.prev()
	
	def _on_type_discovered(self, discoverer, ismedia, filename, name, userdata):
		if ismedia:
			model = self._queue_listview.get_model()
			uri = 'file://'+urllib.quote(filename)
			if RUNNING_SUGAR or RUNNING_HILDON:
				name = '<span size="x-small">'+name+'</span>'
			model.append([uri, name, "", userdata])
			self.emit('item-queued', filename, name, userdata)
			self.save()
		else:
			self.emit('item-not-supported', filename, name, userdata)
	
	def _on_remove_clicked(self, b):
		model, paths = self._queue_listview.get_selection().get_selected_rows()
		self._remove_items([model.get_iter(path) for path in paths])
			
	def _remove_items(self, iter_list):
		model = self._queue_listview.get_model()
		current_uri = model[self._current_index][0]
		
		for i in iter_list:
			if model.get_path(i)[0] == self._current_index:
				print "stopping current"
				self.stop()
			model.remove(i)
			
		if len(model) == 0:
			self._last_index = -1
			self._current_index = 0
			self._media_position = 0
			self._media_duration = 0
			self._update_time_label()
		else:
			try:
				self._current_index = [r[0] for r in model].index(current_uri)
				self._last_index = self._current_index
			except ValueError:
				# If the current_uri was removed, reset to top of list
				self._current_index = 0
				self._last_index = -1
				self._media_position = 0
				self._media_duration = 0
				self._update_time_label()
		self.emit('items-removed')
		
	def _on_seek_value_changed(self, widget):
		if self.__no_seek:
			return
		pos = widget.get_value()
		self.seek(pos)
		
	def _on_queue_row_activated(self, treeview, path, view_column):
		self.pause()
		self._last_index = -1
		self._current_index = path[0]
		self.play()
		
	def _on_queue_row_button_press(self, widget, event):
		if event.button==3: #right click     
			menu = gtk.Menu()   
			
			path = widget.get_path_at_pos(int(event.x),int(event.y))
			model = widget.get_model()
			if path is None: #nothing selected
				return

			item = gtk.ImageMenuItem(_("_Remove"))
			img = gtk.image_new_from_stock('gtk-remove',gtk.ICON_SIZE_MENU)
			item.set_image(img)
			item.connect('activate',self._on_remove_clicked)
			menu.append(item)
				
			menu.show_all()
			menu.popup(None,None,None, event.button,event.time)
			
	def _on_key_press_event(self, widget, event):
		keyname = gtk.gdk.keyval_name(event.keyval)
		self.handle_key(keyname)
	
	def handle_key(self, keyname):
		#if keyname == 'f':
		#	self.toggle_fullscreen()
		if keyname == 'n':
			self.next()
		elif keyname == 'b':
			self.prev()
		elif keyname == 'space' or keyname == 'p':
			self.play_pause_toggle()
		#FIXME: these don't work when we're embedded in penguintv.  why?
		elif keyname == 'Right':
			self.ff()
		elif keyname == 'Left':
			self.rew()
		else:
			return False
		return True
			
	def _on_drawing_area_exposed(self, widget, event):
		if self._x_overlay is None:
			self._x_overlay = self._pipeline.get_by_interface(gst.interfaces.XOverlay)
		self._v_sink.expose()
		if not self.__is_exposed:
			model = self._queue_listview.get_model()
			if len(model) > 0:
				#self._prepare_display()
				if not self._seek_to_saved_position():
					#retry once
					self._seek_to_saved_position()
			self.__is_exposed = True
				
	###utility functions###
	def _get_video_sink(self, compat=False):
		if RUNNING_HILDON:
			if compat:
				return none
			try:
				v_sink = self._pipeline.get_by_name('videosink')
				if v_sink is None:
					v_sink = gst.element_factory_make("xvimagesink", "v_sink")
					bus = self._pipeline.get_bus()
					v_sink.set_bus(bus)
					return v_sink
				else:
					return v_sink
			except:
				logging.error("didn't get videosink :(")
				return None
				
		if compat:
			sinks = ["ximagesink"]
		else:
			sinks = ["xvimagesink","ximagesink"]
		for sink_str in sinks:
			try:
				v_sink = gst.element_factory_make(sink_str, "v_sink")
				break
			except:
				print "couldn't init ",sink_str
		#according to totem this helps set things up (bacon-video-widget-gst-0.10:4290)
		bus = self._pipeline.get_bus()
		v_sink.set_bus(bus)
		return v_sink

	def _ready_new_uri(self, uri):
		"""load a new uri into the pipeline and prepare the pipeline for playing"""
		#if RUNNING_HILDON:
		#	ext = os.path.splitext(uri)[1]
		#	#if ext == '.mp3':
		#	#	logging.debug("readying for mp3")
		#	#	self._pipeline.set_property('audio-sink', self._mp3_sink)
		#	#else:
		#	#	logging.debug("readying for pcm")
		#	#	self._pipeline.set_property('audio-sink', self._pcm_sink)
		self._pipeline.set_state(gst.STATE_READY)
		self._pipeline.set_property('uri',uri)
		self._x_overlay = None #reset so we grab again when we start playing
		return True
		
	def _prepare_display(self, compat=False):
		#if type(self._v_sink) != GstXVImageSink and not compat:
		#do this right at some point: if we are using a substandard sink
		#and we're not being specifically told to use it, try the better one
		
		if 'gstximagesink' in str(type(self._v_sink)).lower() and not compat:
			self._v_sink = self._get_video_sink()
			self._pipeline.set_property('video-sink',self._v_sink)
		if compat:
			self._v_sink = self._get_video_sink(True)
			self._pipeline.set_property('video-sink',self._v_sink)
			
		self._v_sink.set_state(gst.STATE_READY)	
		change_return, state, pending = self._v_sink.get_state(gst.SECOND * 10)
		if change_return != gst.STATE_CHANGE_SUCCESS:
			if 'gstximagesink' in str(type(self._v_sink)).lower():
				print "couldn't find a valid video sink (do something!)"
				return
			#well that didn't work, try again with compatibility sink
			self._v_sink = self._get_video_sink(True)
			self._pipeline.set_property('video-sink',self._v_sink)
			self._prepare_display(True)
			return
 		#maemo throws X Window System errors when doing this -- ignore them
		#http://labs.morpheuz.eng.br/blog/14/08/2007/xv-and-mplayer-on-maemo/
		if RUNNING_HILDON:
			gtk.gdk.error_trap_push()
				
		self._v_sink.set_xwindow_id(self._drawing_area.window.xid)
		#causes expose problems
		#self._v_sink.set_property('sync', True)
		self._v_sink.set_property('force-aspect-ratio', True)
		self._resized_pane = False
		
  		if RUNNING_HILDON:
  			def pop_trap():
				gtk.gdk.flush()
				gtk.gdk.error_trap_pop()
				return False
				
			gobject.idle_add(pop_trap)
		
	def _resize_pane(self):
		#get video width and height so we can resize the pane
		#see totem
		#if (!(caps = gst_pad_get_negotiated_caps (pad)))
		#unbreakme: if there's no video, it doesn't draw right here either
		self._drawing_area.set_flags(gtk.DOUBLE_BUFFERED)
		
		min_width = 200
		max_width = self._hpaned.get_allocation().width - 200 #-200 for the list box
		
		pad = self._v_sink.get_pad('sink')
		if pad is None:
			logging.debug("didn't get video sink pad")
			return
		
		self._resized_pane = True	
			
 		caps = pad.get_negotiated_caps()
 		if caps is None: #no big deal, this might be audio only
 			self._hpaned.set_position(max_width / 2)
 			self._has_video = False
 			return
 		
 		#maemo throws X Window System errors when doing this -- ignore them
		#http://labs.morpheuz.eng.br/blog/14/08/2007/xv-and-mplayer-on-maemo/
		if RUNNING_HILDON:
			gtk.gdk.error_trap_push()

 		self._has_video = True
 		
 		#unbreakme: without this option the video doesn't redraw correctly when exposed
		self._drawing_area.unset_flags(gtk.DOUBLE_BUFFERED)	
 			
  		s = caps[0]
  		movie_aspect = float(s['width']) / s['height']
  		display_height = self._drawing_area.get_allocation().height
  		
  		new_display_width = float(display_height)*movie_aspect
  		if new_display_width >= max_width:
  			self._hpaned.set_position(max_width)
  		elif new_display_width <= min_width:
  			self._hpaned.set_position(min_width)
  		else:
  			self._hpaned.set_position(int(new_display_width))
  		
  		if RUNNING_HILDON:
			def pop_trap():
				gtk.gdk.flush()
				gtk.gdk.error_trap_pop()
				return False
				
			gobject.idle_add(pop_trap)

	def _seek_to_saved_position(self):
		"""many sources don't support seek in ready, so we do it the old fashioned way:
		play, wait for it to play, pause, wait for it to pause, and then seek"""
		model = self._queue_listview.get_model()
		i = -1
		for row in model:
			i+=1
			if i == self._current_index: row[2] = "&#8226;" #bullet
			else: row[2] = ""
		#save, because they may get overwritten when we play and pause
		pos, dur = self._media_position, self._media_duration
		if not RUNNING_HILDON:
			volume = self._pipeline.get_property('volume')
		#temporarily mute to avoid little bloops during this hack
		self._pipeline.set_property('volume',0)
		
		#maemo throws X Window System errors when doing this -- ignore them
		#http://labs.morpheuz.eng.br/blog/14/08/2007/xv-and-mplayer-on-maemo/
		if RUNNING_HILDON:
			gtk.gdk.error_trap_push()

		self.play(True)
		change_return, state, pending = self._pipeline.get_state(gst.SECOND * 10)
		if change_return != gst.STATE_CHANGE_SUCCESS:
			print "some problem changing state to play, may be playbin2 issue?"
			self._using_playbin2 = False
			self.stop()
			self._pipeline.set_state(gst.STATE_NULL)
			self.gstreamer_init()
			self._last_index = -1 #trigger play() to reinit the pipe
			return False
		self.pause()
		if change_return != gst.STATE_CHANGE_SUCCESS:
			print "some problem changing state to pause"
			self._using_playbin2 = False
			self._pipeline.set_state(gst.STATE_NULL)
			self.gstreamer_init()
			self._last_index = -1 #trigger play() to reinit the pipe
			return False
		self._media_position, self._media_duration = pos, dur
		self.seek(self._media_position)
		if self._media_duration <= 0:
			self._media_duration = 1
		self._resize_pane()
		self._seek_scale.set_range(0,self._media_duration)
		self._seek_scale.set_value(self._media_position)
		if not RUNNING_HILDON:
			self._pipeline.set_property('volume',volume)
		else:
			self._pipeline.set_property('volume', 10)
		self._update_time_label()
		
  		if RUNNING_HILDON:
			def pop_trap():
				gtk.gdk.flush()
				gtk.gdk.error_trap_pop()
				return False
				
			gobject.idle_add(pop_trap)
		
		return True
		
	def _tick(self):
		self.__no_seek = True
		try:
			now = self._pipeline.query_position(gst.FORMAT_TIME)[0]
			if now - self._last_tick > self._tick_interval:
				self._last_tick = now
				self.emit('tick')
		except:
			pass
		
		self._update_seek_bar()
		self._update_time_label()
		if self._prepare_save:
			self._prepare_save = False
			self.save()
		self.__no_seek = False
		return self._pipeline.get_state()[1] == gst.STATE_PLAYING
		
	def _periodic_save_cb(self):
		self._prepare_save = True
		return True

	def _update_seek_bar(self):
		#for some reason when paused, hildon tells us the position is 0. Ignore it
		if RUNNING_HILDON and self._pipeline.get_state()[1] == gst.STATE_PAUSED:
			return
		try:
			self._media_position = self._pipeline.query_position(gst.FORMAT_TIME)[0]
			#print self._media_position, self._media_duration
			if self._media_position > self._media_duration:
				self._media_duration = self._pipeline.query_duration(gst.FORMAT_TIME)[0]
				self._seek_scale.set_range(0,self._media_duration)
			self._seek_scale.set_value(self._media_position)
			
		except Exception, e:
			print e
			
	def _update_time_label(self):
		def nano_to_string(long_val):
			seconds = long_val / gst.SECOND
			minutes = seconds / 60
			seconds = seconds % 60
			return "%i:%.2i" % (minutes,seconds)
			
		self._time_label.set_text(nano_to_string(self._media_position)+" / "+nano_to_string(self._media_duration))
		
	#def _on_sync_message(self, bus, message):
	#	if message.structure is None:
	#		return
	#	if message.structure.get_name() == 'prepare-xwindow-id':
	#		logging.debug("forcing aspect to true")
	#		message.src.set_property('force-aspect-ratio', True)
	###drag and drop###
		
	def _on_queue_drag_data_received(self, treeview, context, x, y, selection, targetType, time):
		if targetType == self._TARGET_TYPE_REORDER:
			treeview.emit_stop_by_name('drag-data-received')
			model, paths_to_copy = treeview.get_selection().get_selected_rows()
			if len(paths_to_copy) > 1:
				print "can only move one at a time"
				return
			row = list(model[paths_to_copy[0][0]])
			iter_to_copy = model.get_iter(paths_to_copy[0])
			try:
				path, pos = treeview.get_dest_row_at_pos(x, y)
				target_iter = model.get_iter(path)
				
				playing_uri = model[self._current_index][0]
				
				if self.checkSanity(model, iter_to_copy, target_iter):
					self.iterCopy(model, target_iter, row, pos)
					context.finish(True, True, time) #finishes the move
					i=-1
					for row in model:
						i+=1
						if playing_uri == row[0]:
							self._last_index = self._current_index = i
							row[2]="&#8226;" #bullet
						else:
							row[2]=""							
				else:
					context.finish(False, False, time)
			except:
				model.append(row)
				context.finish(True, True, time)
		elif targetType == self._TARGET_TYPE_URI_LIST:
			uri_list = [s for s in selection.data.split('\r\n') if len(s) > 0]
			for uri in uri_list:
				uri = uri.replace("file://", "")
				uri = urllib.unquote(uri)
				self.queue_file(uri)			

	def checkSanity(self, model, iter_to_copy, target_iter):
		path_of_iter_to_copy = model.get_path(iter_to_copy)
		path_of_target_iter = model.get_path(target_iter)
		if path_of_target_iter[0:len(path_of_iter_to_copy)] == path_of_iter_to_copy:
			return False
		else:
			return True
	
	def iterCopy(self, target_model, target_iter, row, pos):
		if (pos == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE) or (pos == gtk.TREE_VIEW_DROP_INTO_OR_AFTER):
			new_iter = target_model.append(row)
		elif pos == gtk.TREE_VIEW_DROP_BEFORE:
			new_iter = target_model.insert_before(target_iter, row)
		elif pos == gtk.TREE_VIEW_DROP_AFTER:
			new_iter = target_model.insert_after(target_iter, row)		
			
class GStreamerErrorDialog(gtk.Window):
	def __init__(self, type=gtk.WINDOW_TOPLEVEL):
		gtk.Window.__init__(self, type)
		self._last_message = ""
		self._label = gtk.Label()
		
		#gtk preparation
		vbox = gtk.VBox()
		vbox.pack_start(self._label, True, True, 0)
		hbox = gtk.HBox()
		l = gtk.Label("")
		hbox.pack_start(l, True)
		button = gtk.Button(stock='gtk-ok')
		button.connect('clicked', self._on_ok_clicked)
		hbox.pack_start(button, False)
		vbox.pack_start(hbox, False)
		self.add(vbox)
		self.connect('delete-event', self._on_delete_event)
		
	def show_error(self, error_msg):
		if error_msg == self._last_message:
			return
		self._last_message = error_msg
		self._label.set_text(error_msg)
		self.show_all()
			
	def _on_ok_clicked(self, button):
		self.hide()
			
	def _on_delete_event(self, widget, event):
		return self.hide_on_delete()
		
#########app
def do_quit(self, widget, player):
	player.finish()
	gtk.main_quit()
	
def items_removed(player):
	print player.get_queue_count()
	
def item_not_supported(app, player, filename, name):
	print filename,name, "not supported"
	
fullscreen = False
def on_app_key_press_event(widget, event, player, window):
	global fullscreen
	keyname = gtk.gdk.keyval_name(event.keyval)
	if keyname == 'f' or (RUNNING_HILDON and keyname == 'F6'):
		#maemo throws X Window System errors when doing this -- ignore them
		#http://labs.morpheuz.eng.br/blog/14/08/2007/xv-and-mplayer-on-maemo/
		if RUNNING_HILDON:
			gtk.gdk.error_trap_push()
		fullscreen = not fullscreen
		player.toggle_controls(fullscreen)
		if fullscreen:
			window.window.fullscreen()
		else:
			window.window.unfullscreen()
		if RUNNING_HILDON:
			def pop_trap():
				gtk.gdk.flush()
				gtk.gdk.error_trap_pop()
				return False
				
			gobject.idle_add(pop_trap)
		
if __name__ == '__main__': # Here starts the dynamic part of the program 
	window = gtk.Window()
	if RUNNING_SUGAR:
		import sugar.env
		home = os.path.join(sugar.env.get_profile_path(), 'penguintv')
	else:
		home = os.path.join(os.getenv('HOME'), ".penguintv")
	try:
		opts, args = getopt.getopt(sys.argv[1:], "p:", ["--playlist"])
	except getopt.GetoptError, e:
		print "error %s", str(e)
		sys.exit(1)
	playlist = os.path.join(home, 'gst_playlist.pickle')
	if len(opts) > 0:
		for o, a in opts:
			if o in ('-p', '--playlist'):
				playlist = a
								
	app = GStreamerPlayer(window, playlist)
	app.Show()
	
	window.connect('delete-event', do_quit, app)
	window.connect('key-press-event', on_app_key_press_event, app, window)
	window.resize(640,480)
	app.connect('items-removed', items_removed)	
	app.connect('item-not-supported', item_not_supported)
	
				
	app.load()

	for item in args:
		app.queue_file(item)
	gtk.main()
	
