#a view that shows the current downloading media, and any unplayed media (For now)

import gtk
import MediaManager
import sets, time, os, glob

import ptvDB
import utils

D_MEDIA_ID    = 0
D_FEED_TITLE  = 1
D_ENTRY_TITLE = 2
D_PROGRESS    = 3
D_SIZE        = 4
D_PIXBUF      = 5

U_DATE_INT    = 0
U_DATE_STR    = 1
U_MEDIA_ID    = 2
U_FEED_TITLE  = 3
U_ENTRY_TITLE = 4 
U_PIXBUF      = 5

MAX_WIDTH  = 48
MAX_HEIGHT = 48
MIN_SIZE   = 24

if ptvDB.RUNNING_SUGAR:
	MAX_WIDTH  = 32
	MAX_HEIGHT = 32
	MIN_SIZE   = 0

class DownloadView:
	def __init__(self, mm, db, gladefile):
		self._mm = mm
		self._db = db
		self._gladefile = gladefile
		
		self._downloads = []
		self._unplayed_media = [] #contains media id
		
		self._downloads_liststore = gtk.ListStore(int, #media_id
											 	  str, #feed_title
											 	  str, #entry_title
											 	  int, #progress
											 	  str, #size
											 	  gtk.gdk.Pixbuf) #icon
											 
		#self._unplayed_liststore  = gtk.ListStore(int, #date as int
		#									 	  str, #date as str
		#									 	  int, #media_id
		#										  str, #feed_title
		#										  str, #entry_title
		#										  gtk.gdk.Pixbuf) #icon
											 
		self.Show()
		self.update_unplayed_media()
		
	def Show(self):
		widget_tree = gtk.glade.XML(self._gladefile, 'download_view','penguintv')
		self._widget = widget_tree.get_widget('download_view')
		
		self._downloads_listview = widget_tree.get_widget('download_list')
		column = gtk.TreeViewColumn(_(''))
		column.set_resizable(True)
		renderer = gtk.CellRendererPixbuf()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, pixbuf=D_PIXBUF)
		self._downloads_listview.append_column(column)
		
		column = gtk.TreeViewColumn(_('Feed'))
		column.set_resizable(True)
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, text=D_FEED_TITLE)
		self._downloads_listview.append_column(column)
		
		column = gtk.TreeViewColumn(_('Entry'))
		column.set_resizable(True)
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, text=D_ENTRY_TITLE)
		self._downloads_listview.append_column(column)
		
		column = gtk.TreeViewColumn(_('Progress'))
		column.set_resizable(True)
		renderer = gtk.CellRendererProgress()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, value=D_PROGRESS)
		self._downloads_listview.append_column(column)
		
		column = gtk.TreeViewColumn(_('Size'))
		column.set_resizable(True)
		renderer = gtk.CellRendererText()
		column.pack_start(renderer, True)
		column.set_attributes(renderer, text=D_SIZE)
		self._downloads_listview.append_column(column)
		
		self._downloads_listview.columns_autosize()
		
		##########
		#self._unplayed_listview = widget_tree.get_widget('unplayed_list')
		#column = gtk.TreeViewColumn(_(''))
		#column.set_resizable(True)
		#renderer = gtk.CellRendererPixbuf()
		#column.pack_start(renderer, True)
		#column.set_attributes(renderer, pixbuf=U_PIXBUF)
		#self._unplayed_listview.append_column(column)
		
		#column = gtk.TreeViewColumn(_('Date'))
		#column.set_resizable(True)
		#renderer = gtk.CellRendererText()
		#column.pack_start(renderer, True)
		#column.set_attributes(renderer, text=U_DATE_STR)
		#self._unplayed_listview.append_column(column)
		
		#column = gtk.TreeViewColumn(_('Feed Title'))
		#column.set_resizable(True)
		#renderer = gtk.CellRendererText()
		#column.pack_start(renderer, True)
		#column.set_attributes(renderer, text=U_FEED_TITLE)
		#self._unplayed_listview.append_column(column)
		
		#column = gtk.TreeViewColumn(_('Entry Title'))
		#column.set_resizable(True)
		#renderer = gtk.CellRendererText()
		#column.pack_start(renderer, True)
		#column.set_attributes(renderer, text=U_ENTRY_TITLE)
		#self._unplayed_listview.append_column(column)
		
		#self._unplayed_listview.columns_autosize()
		
		#unplayed_sorted = gtk.TreeModelSort(self._unplayed_liststore)
		#unplayed_sorted.set_sort_column_id(U_DATE_INT, gtk.SORT_DESCENDING)
		
		self._downloads_listview.set_model(self._downloads_liststore)
		#self._unplayed_listview.set_model(unplayed_sorted)
		
		
		#panes = widget_tree.get_widget('download_panes')
		#panes.set_position(200)
		
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
		
		i=-1
		for item in self._downloads_liststore:
			i+=1
			if item[D_MEDIA_ID] in removed:
				self._downloads_liststore.remove(self._downloads_liststore.get_iter((i,)))
			elif item[D_MEDIA_ID] in unchanged:
				index = current_list.index(item[D_MEDIA_ID])
				item  = self._downloads[index]
				self._downloads_liststore[i][D_PROGRESS] = self._downloads[index].progress
				self._downloads_liststore[i][D_SIZE]     = utils.format_size(self._downloads[index].total_size)
				
		for media_id in added:
			item       = self._downloads[current_list.index(media_id)]
			entry      = self._db.get_entry(item.media['entry_id'])
			feed_title = self._db.get_feed_title(entry['feed_id'])
			pixbuf     = self._get_pixbuf(entry['feed_id'])
			print [media_id, entry['title'], feed_title, item.progress, utils.format_size(item.total_size)]
			self._downloads_liststore.append([media_id, 
											  entry['title'], 
											  feed_title, 
											  item.progress, 
											  utils.format_size(item.total_size), 
											  pixbuf])
			
		
	def update_unplayed_media(self):
		"""gets called when a download finishes"""
		self.update_downloads()
		return
		
		
		
		
		current_list = self._db.get_unplayed_media()
		media_id_list = [item[0] for item in current_list]
		viewing_list = [item[U_MEDIA_ID] for item in self._unplayed_liststore]
			
		oldset = sets.Set(viewing_list)
		newset = sets.Set(media_id_list)
		
		removed = list(oldset.difference(newset))
		added   = list(newset.difference(oldset))
		
		print removed
		print added
		
		i=-1
		for item in self._unplayed_liststore:
			i+=1
			if item[U_MEDIA_ID] in removed:
				self._unplayed_liststore.remove(self._unplayed_liststore.get_iter((i,)))
			
		for media_id in added:
			item = current_list[media_id_list.index(media_id)]
			feed_title  = self._db.get_feed_title(item[2])
			entry       = self._db.get_entry(item[1])
			date_str    = time.strftime("%x",time.localtime(entry['date']))
			entry_title = entry['title']
			pixbuf      = self._get_pixbuf(item[2])
			self._unplayed_liststore.append([entry['date'], date_str, item[0], feed_title, entry_title, pixbuf])
			
		self.update_downloads()
		
	def _get_pixbuf(self, feed_id):
		"""from feedlist.py"""
		filename = os.path.join(self._db.home,'.penguintv','icons',str(feed_id)+'.*')
		result = glob.glob(filename)
		if len(result)==0:
			p = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB,True,8, MIN_SIZE, MIN_SIZE)
			p.fill(0xffffff00)
			return p
	
		try:
			p = gtk.gdk.pixbuf_new_from_file(result[0])
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
		if width < MIN_SIZE and height < MIN_SIZE:
			height = MIN_SIZE
			width = p.get_width() * height / p.get_height()
		if height != p.get_height() or width != p.get_width():
			p = gtk.gdk.pixbuf_new_from_file_at_size(result[0], width, height)
			
		#put a space between the image and the icon (to the left of it)
		#use treeviewcolumn spacing instead
		return p
			
		
