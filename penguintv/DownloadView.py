#a view that shows the current downloading media, and any unplayed media (For now)

import gtk
import sets, time, os, glob
import traceback
import logging

import IconManager
import MediaManager
import ptvDB
import utils

if utils.RUNNING_HILDON:
	import hildon

from Downloader import PAUSED, STOPPED, QUEUED

D_MEDIA_ID           = 0
D_DESCRIPTION         = 1
D_DESCRIPTION_MARKUP  = 2
D_PROGRESS           = 3
D_SIZE               = 4
D_SIZE_MARKUP        = 5
D_PIXBUF             = 6
D_STATUS             = 7
D_STATUS_MARKUP      = 8

MAX_WIDTH  = 48
MAX_HEIGHT = 48
MIN_SIZE   = 24

class DownloadView:
	def __init__(self, app, mm, db, gladefile):
		self._app = app
		self._mm = mm
		self._icon_manager = IconManager.IconManager(self._app.db.home)
		self._gladefile = gladefile
		
		self._downloads = []
		self._unplayed_media = [] #contains media id
		
		self._downloads_liststore = gtk.ListStore(int, #media_id
											 	  str, #description 
											 	  str, #description_markup
											 	  int, #progress
											 	  str, #size
											 	  str, #size markup
											 	  gtk.gdk.Pixbuf, #icon
											 	  int, #status
											 	  str) #status markup
										 
		self.Show()
		#self.update_unplayed_media()
		
	def Show(self):
		widget_tree = gtk.glade.XML(self._gladefile, 'download_view','penguintv')
		for key in dir(self.__class__): #python insaneness
			if key[:3] == 'on_':
				widget_tree.signal_connect(key, getattr(self, key))
				
		if utils.RUNNING_SUGAR:
			widget_tree.get_widget('stop_toolbutton').set_stock_id(None)
			widget_tree.get_widget('stop_toolbutton').set_icon_name('stock-close')
			widget_tree.get_widget('pause_toolbutton').set_stock_id(None)
			widget_tree.get_widget('pause_toolbutton').set_icon_name('stock-media-pause')
			widget_tree.get_widget('resume_toolbutton').set_stock_id(None)
			widget_tree.get_widget('resume_toolbutton').set_icon_name('stock-go-down')

		if utils.RUNNING_HILDON:
			sw = widget_tree.get_widget('d_v_scrolledwindow')
			hildon.hildon_helper_set_thumb_scrollbar(sw, True)
				
		self._widget = widget_tree.get_widget('download_view')
		self._resume_button = widget_tree.get_widget('resume_toolbutton')
		self._resume_button.set_sensitive(False)
		
		self._downloads_listview = widget_tree.get_widget('download_list')
		try:
			self._downloads_listview.set_rubber_banding(True)
		except:
			pass #not everyone can do this
		selection = self._downloads_listview.get_selection()
		selection.set_mode(gtk.SELECTION_MULTIPLE)
		selection.connect("changed", self._on_selection_changed)
		
		column = gtk.TreeViewColumn(_(''))
		column.set_resizable(True)
		renderer = gtk.CellRendererPixbuf()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, pixbuf=D_PIXBUF)
		self._downloads_listview.append_column(column)

		column = gtk.TreeViewColumn(_('Progress'))
		column.set_resizable(True)
		renderer = gtk.CellRendererProgress()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, value=D_PROGRESS)
		self._downloads_listview.append_column(column)
				
		column = gtk.TreeViewColumn(_('Description'))
		column.set_resizable(True)
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, markup=D_DESCRIPTION_MARKUP)
		self._downloads_listview.append_column(column)
		
		column = gtk.TreeViewColumn(_('Size'))
		column.set_resizable(True)
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, markup=D_SIZE_MARKUP)
		self._downloads_listview.append_column(column)
		
		column = gtk.TreeViewColumn(_('Status'))
		column.set_resizable(True)
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, markup=D_STATUS_MARKUP)
		self._downloads_listview.append_column(column)
		self._downloads_listview.columns_autosize()
		self._downloads_listview.set_model(self._downloads_liststore)
		self._widget.show_all()
		
	def get_widget(self):
		return self._widget
		
	def update_downloads(self):
		"""gets called a lot (once for every progress callback) so be quick"""
		self._downloads = self._mm.get_download_list()
		current_list = [item.media['media_id'] for item in self._downloads]
		viewing_list = [item[D_MEDIA_ID] for item in self._downloads_liststore]

		oldset = sets.Set(viewing_list)
		newset = sets.Set(current_list)
		
		removed   = list(oldset.difference(newset))
		added     = list(newset.difference(oldset))
		unchanged = list(oldset.intersection(newset))
		
		#slower but works better, because the list is changing all over the place
		for item in removed:
			i=-1
			for row in self._downloads_liststore:
				i+=1
				if row[0] == item:
					self._downloads_liststore.remove(self._downloads_liststore.get_iter((i,)))
					break
		
		tree,selected = self._downloads_listview.get_selection().get_selected_rows()
		selected = [i[0] for i in selected] 

		i=-1
		for item in self._downloads_liststore:
			i+=1
			if item[D_MEDIA_ID] in unchanged:
				index = current_list.index(item[D_MEDIA_ID])
				medium = self._downloads[index]

				iter = self._downloads_liststore[i]
				iter[D_PROGRESS] = medium.progress
				iter[D_SIZE]     = utils.format_size(medium.total_size)
				#iter[D_STATUS] refers to the old status

				if medium.status == PAUSED or medium.status == QUEUED:
					if iter[D_STATUS] != medium.status:
						if i in selected:
							iter[D_DESCRIPTION_MARKUP] = '<i>'+utils.my_quote(iter[D_DESCRIPTION])+'</i>'
							iter[D_SIZE_MARKUP]= '<i>'+iter[D_SIZE]+'</i>'
							if medium.status == PAUSED:
								iter[D_STATUS_MARKUP] = '<i>'+_("Paused")+'</i>'
							elif medium.status == QUEUED:
								iter[D_STATUS_MARKUP] = '<i>'+_("Queued")+'</i>'
						else:
							iter[D_DESCRIPTION_MARKUP] = '<span color="#777"><i>'+utils.my_quote(iter[D_DESCRIPTION])+'</i></span>'
							iter[D_SIZE_MARKUP] = '<span color="#777"><i>'+iter[D_SIZE]+'</i></span>'
							if medium.status == PAUSED:
								iter[D_STATUS_MARKUP] = '<span color="#777"><i>'+_("Paused")+'</i></span>'
							elif medium.status == QUEUED:
								iter[D_STATUS_MARKUP] = '<span color="#777"><i>'+_("Queued")+'</i></span>'
						iter[D_STATUS] = medium.status
				else:
					#if iter[D_STATUS] == PAUSED or i in selected:
					iter[D_DESCRIPTION_MARKUP] = utils.my_quote(iter[D_DESCRIPTION])
					iter[D_SIZE_MARKUP]= iter[D_SIZE]
					iter[D_STATUS] = medium.status
					iter[D_STATUS_MARKUP] = ""
					
		#check resume button sensitivity
		resume_sens = False
		i=-1
		for item in self._downloads_liststore:
			i+=1
			if item[D_STATUS] == PAUSED or item[D_STATUS] == QUEUED:
				if i in selected:
					resume_sens = True
					break
		self._resume_button.set_sensitive(resume_sens)

		for media_id in added:
			item        = self._downloads[current_list.index(media_id)]
			try:
				entry       = self._app.db.get_entry(item.media['entry_id'])
				description = self._app.db.get_feed_title(entry['feed_id']) + " " + utils.get_hyphen() + " " + entry['title']
				size        = utils.format_size(item.total_size)
			except:
				logging.warning("trouble getting entry updating downloads: %s" % str(item))
				continue
			if item.status == PAUSED:
				description_markup = '<span color="#777"><i>'+utils.my_quote(description)+'</i></span>'
				size_markup = '<span color="#777"><i>'+size+'</i></span>'
				status_markup = '<i>'+_("Paused")+'</i>'
			elif item.status == QUEUED:
				description_markup = '<span color="#777"><i>'+utils.my_quote(description)+'</i></span>'
				size_markup = '<span color="#777"><i>'+size+'</i></span>'
				status_markup = '<i>'+_("Queued")+'</i>'
			else:
				description_markup = utils.my_quote(description)
				size_markup = size
				status_markup = ""

			pixbuf = self._icon_manager.get_icon_pixbuf(entry['feed_id'], 
					   MAX_WIDTH, MAX_HEIGHT, MIN_SIZE, MIN_SIZE)
			self._downloads_liststore.append([media_id, 
											  description, 
											  description_markup,
											  item.progress, 
											  size, 
											  size_markup,
											  pixbuf,
											  item.status,
											  status_markup])
			
		#make sure both lists are sorted the same way
		id_list = [row[D_MEDIA_ID] for row in self._downloads_liststore]
		self._downloads.sort(lambda x,y: id_list.index(x.media['media_id']) - id_list.index(y.media['media_id']))
			
	def on_stop_toolbutton_clicked(self, widget):
		selection = self._downloads_listview.get_selection()
		tree,selected = selection.get_selected_rows()
		medialist = []
		for index in selected: #build a list to avoid race conditions
			medialist.append((self._downloads[index[0]].status, self._downloads[index[0]].media))
		#start by getting rid of queued, stopped, end with active downloads
		medialist.sort()
		for status, medium in medialist:
			print "stopping",medium['url']
			self._app.do_cancel_download(medium)
		selection.unselect_all()
		
	def on_pause_toolbutton_clicked(self, widget):
		selection = self._downloads_listview.get_selection()
		tree,selected = selection.get_selected_rows()
		for index in selected:
			self._app.do_pause_download(self._downloads_liststore[index[0]][D_MEDIA_ID])

	def on_resume_toolbutton_clicked(self, widget):
		selection = self._downloads_listview.get_selection()
		tree,selected = selection.get_selected_rows()
		for index in selected:
			self._app.do_resume_download(self._downloads_liststore[index[0]][D_MEDIA_ID])
		
	def on_download_list_row_activated(self, treeview, path, viewcolumn):
		d = self._downloads[path[0]]
		self._app.select_entry(d.media['entry_id'])
			
	def _on_selection_changed(self, selection):		
		tree,selected = selection.get_selected_rows()
		selected = [i[0] for i in selected]
		
		resume_sens = False
		i=-1
		for item in self._downloads_liststore:
			i+=1

			if item[D_STATUS] == PAUSED or item[D_STATUS] == QUEUED:
				if i in selected:
					item[D_DESCRIPTION_MARKUP] = '<i>'+utils.my_quote(item[D_DESCRIPTION])+'</i>'
					item[D_SIZE_MARKUP]= '<i>'+item[D_SIZE]+'</i>'
					if item[D_STATUS] == PAUSED:
						item[D_STATUS_MARKUP] = '<i>'+_("Paused")+'</i>'
						resume_sens = True
					elif item[D_STATUS] == QUEUED:
						item[D_STATUS_MARKUP] = '<i>'+_("Queued")+'</i>'
				else:
					item[D_DESCRIPTION_MARKUP] = '<span color="#777"><i>'+utils.my_quote(item[D_DESCRIPTION])+'</i></span>'
					item[D_SIZE_MARKUP]= '<span color="#777"><i>'+item[D_SIZE]+'</i></span>'
					if item[D_STATUS] == PAUSED:
						item[D_STATUS_MARKUP] = '<span color="#777"><i>'+_("Paused")+'</i></span>'
					elif item[D_STATUS] == QUEUED:
						item[D_STATUS_MARKUP] = '<span color="#777"><i>'+_("Queued")+'</i></span>'
			else:
				item[D_DESCRIPTION_MARKUP] = utils.my_quote(item[D_DESCRIPTION])
				item[D_SIZE_MARKUP] = item[D_SIZE]
				item[D_STATUS_MARKUP] = ""
		self._resume_button.set_sensitive(resume_sens)
