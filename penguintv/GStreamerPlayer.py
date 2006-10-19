#!/usr/bin/env python
#a basic gstreamer-based player.  

import pygst
pygst.require("0.10")
import gst

import pygtk
pygtk.require("2.0")
import gtk

import ptvDB

class GStreamerPlayer:
	def __init__(self, db, layout_dock):
		self._db = db	
		self._layout_dock = layout_dock
		
	def Show(self):
		hpaned = gtk.HPaned()
		vbox = gtk.VBox()
		self._drawing_area = gtk.DrawingArea()
		vbox.pack_start(self._drawing_area)
		button_box = gtk.HButtonBox()
		button = gtk.Button(stock='gtk-media-play')
		button.connect("clicked", self._on_play_clicked)
		button_box.add(button)
		button = gtk.Button(stock='gtk-media-pause')
		button.connect("clicked", self._on_pause_clicked)
		button_box.add(button)
		vbox.pack_start(button_box, False)
		hpaned.add1(vbox)
		
		self._queue_listview = gtk.TreeView()
		model = gtk.ListStore(str, str) #filename, title to display
		self._queue_listview.set_model(model)
		column = gtk.TreeViewColumn(_("Playlist"))
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, markup=1)
		self._queue_listview.append_column(column)
		hpaned.add2(self._queue_listview)
		self._layout_dock.add(hpaned)
		
		#Gstreamer init
		self._pipeline = gst.Pipeline('ptv_pipeline')
		videotestsrc = gst.element_factory_make("videotestsrc", "video")
		self._pipeline.add(videotestsrc)
		self._sink = gst.element_factory_make("xvimagesink", "sink")
		self._pipeline.add(self._sink)
		videotestsrc.link(self._sink)	
		
		self._layout_dock.show_all()
		
	def detach(self):
		"""video window can detach.  queue stays embedded"""
		pass
	
	def reattach(self):
		"""hides external window and reinits embedded window"""
		pass
		
	def queue_file(self, filename):
		"""returns true if we can play this file, false if not"""
		pass
		
	def play(self):
		self._sink.set_xwindow_id(self._drawing_area.window.xid)
		self._pipeline.set_state(gst.STATE_PLAYING)
		
	def pause(self):
		self._pipeline.set_state(gst.STATE_READY)
		
	def ff(self):
		pass
		
	def rew(self):
		pass
		
	def next(self):
		pass
		
	def prev(self):
		pass
		
	def finish(self):
		"""pauses, saves state, and cleans up gstreamer"""
		pass
		
	def _on_play_clicked(self, button):
		self.play()
		
	def _on_pause_clicked(self, button):
		self.pause()

	def _update_seek_bar(self):
		pass
		
def do_quit(self, widget):
	gtk.main_quit()
		
if __name__ == '__main__': # Here starts the dynamic part of the program 
	db = ptvDB.ptvDB()
	
	window = gtk.Window()
	app = GStreamerPlayer(db, window)
	app.Show()
	window.connect('delete-event', do_quit)
	gtk.main()
	
