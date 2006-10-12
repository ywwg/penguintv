import gtk
import pango
from ptvDB import T_ALL, T_TAG, T_SEARCH, T_BUILTIN
from FeedList import ALL, DOWNLOADED
from MainWindow import F_TEXT, F_COUNT, F_SEPARATOR, F_FAVORITE, F_NOT_FAVORITE, F_TYPE

class FilterSelectorWidget:
	def __init__(self, xml, main_window, model):
		self._xml = xml
		self._main_window = main_window
		self._model = model
		
		self._widget = self._xml.get_widget('filter_selector_widget')
		self._pane = self._xml.get_widget('hpaned')
		self._favorites_treeview = self._xml.get_widget('favorites_treeview')
		self._favorites_filter = self._model.filter_new()
		self._favorites_filter.set_visible_column(F_FAVORITE)
		self._favorites_treeview.set_model(self._favorites_filter)

		column = gtk.TreeViewColumn('Favorites')
		renderer = gtk.CellRendererText()
		column.pack_start(renderer)
		column.set_attributes(renderer, text=F_COUNT)
		self._favorites_treeview.append_column(column)
		

		self._all_tags_treeview = self._xml.get_widget('all_tags_treeview')
		self._all_tags_filter = self._model.filter_new()
		self._all_tags_filter.set_visible_column(F_NOT_FAVORITE)
		self._all_tags_treeview.set_model(self._all_tags_filter)
		
		column = gtk.TreeViewColumn('Tags')
		renderer = gtk.CellRendererText()
		column.pack_start(renderer)
		column.set_attributes(renderer, text=F_COUNT)
		self._all_tags_treeview.append_column(column)
		
		self._favorites_treeview.get_selection().connect("changed", self._on_selection_changed)
		self._all_tags_treeview.get_selection().connect("changed", self._on_selection_changed)
		self._all_tags_treeview.set_row_separator_func(lambda model,iter: model[model.get_path(iter)[0]][F_SEPARATOR])
		self._xml.get_widget('all_feeds_button').connect('clicked', self._select_all_feeds)
		self._xml.get_widget('downloaded_media_button').connect('clicked', self._select_downloaded_media)
		
		self._old_list = []
		
		
	def is_visible(self):
		return self._widget.get_property('visible')
		
	def ShowAt(self, x, y):
		context = self._widget.create_pango_context()
		style = self._widget.get_style().copy()
		font_desc = style.font_desc
		metrics = context.get_metrics(font_desc, None)
		char_width = metrics.get_approximate_char_width()
		
		widest_left = 0
		widest_right = 0
		for row in self._model:
			if row[F_TYPE] == T_BUILTIN or row[F_FAVORITE]:
				width = len(row[F_COUNT])
				if width > widest_left:
					widest_left = width
			if row[F_NOT_FAVORITE]:
				width = len(row[F_COUNT])
				if width > widest_right:
					widest_right = width
		
		pane_position = pango.PIXELS((widest_left+10)*char_width)
		window_width  = pango.PIXELS((widest_left+widest_right+10)*char_width)+100
		
		self._widget.move(x,y)
		self._widget.resize(window_width,500)
		self._pane.set_position(pane_position)
		self._favorites_filter.refilter()
		self._all_tags_filter.refilter()
		self._favorites_treeview.columns_autosize()
		self._all_tags_treeview.columns_autosize()
		self._widget.show_all()
						
	def Hide(self):
		self._widget.hide()
		
	def _on_selection_changed(self, selection):
		model, iter = selection.get_selected()
		if iter is not None:
			i=-1
			for row in self._model:
				i+=1
				if row[F_TEXT] == model[iter][F_TEXT]:
					break
			self._main_window.set_active_filter(i)
			self.Hide()
			selection.unselect_all()
			
	def _select_all_feeds(self, button):
		self._main_window.set_active_filter(ALL)
		self.Hide()
		
	def _select_downloaded_media(self, button):
		self._main_window.set_active_filter(DOWNLOADED)
		self.Hide()
		
