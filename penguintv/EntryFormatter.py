import os, os.path
import htmllib, HTMLParser
import time
import logging
import traceback

import gtk

from ptvDB import D_NOT_DOWNLOADED, D_DOWNLOADING, D_DOWNLOADED, D_RESUMABLE, \
				  D_ERROR, D_WARNING
import Downloader
import utils

GTKHTML=0
MOZILLA=1

class EntryFormatter:
	def __init__(self, mm=None, with_feed_titles=False, indicate_new=False, basic_progress=False, ajax_url=None):
		self._mm = mm
		self._with_feed_titles = with_feed_titles
		self._indicate_new = indicate_new
		self._basic_progress = basic_progress
		self._ajax_url = ajax_url
		
	def htmlify_item(self, item, convert_newlines=False):
		""" Take an item as returned from ptvDB and turn it into an HTML page.  Very messy at times,
			but there are lots of alternate designs depending on the status of media. """

		#global download_status
		ret = []
		#ret.append('<div class="heading">')
		if self._indicate_new:
			if item['new']:
				ret.append("""<div class="entry_new" oncontextmenu="javascript:parent.location='rightclick:%i'">""" % item['entry_id'])
			else:
				ret.append("""<div class="entry_old" oncontextmenu="javascript:parent.location='rightclick:%i'">""" % item['entry_id'])
		else:
			ret.append("""<div class="entry" oncontextmenu="javascript:parent.location='rightclick:%i'">""" % item['entry_id'])

		ret.append('''<table style="text-align: left; width: 100%;" border="0" cellpadding="0" cellspacing="0"><tr><td>''')

		if self._with_feed_titles:
			if item.has_key('title') and item.has_key('feed_title'):
				ret.append('<div class="stitle">%s:<br/>%s</div>' % (item['feed_title'],item['title']))
		else:
			if item.has_key('title'):
				if self._indicate_new and item['new']:
					if utils.RUNNING_HILDON:
						indicator="*"
					else:
						indicator="&#10036;"
					ret.append('<div class="stitle"><a href="#%s"></a>%s%s</div>' % (item['entry_id'],indicator,item['title']))
				else:
					ret.append('<div class="stitle"><a href="#%s"></a>%s</div>' % (item['entry_id'],item['title']))

		ret.append('</td><td style="text-align: right;">')

		if not utils.RUNNING_SUGAR:
			cb_status = item['keep'] and "CHECKED" or "UNCHECKED"
			cb_function = item['keep'] and "unkeep" or "keep"
	
			ret.append('''<form id="keep"> <input type="checkbox" id="keep" name="keep" class="radio" onclick="parent.location='%s:%i'" %s="yes"><a href="%s:%i">%s</a></form>''' % 
			           (cb_function, item['entry_id'], cb_status, cb_function, item['entry_id'], _('Keep New')))

		ret.append('</td></tr></table>')

		if item.has_key('creator'):
			if item['creator']!="" and item['creator'] is not None:
				ret.append('By %s<br/>' % (item['creator'],))			
		if item['date'] != (0,0,0,0,0,0,0,0,0):
			ret.append('<div class="sdate">%s</div>' % time.strftime('%a %b %d, %Y %X',time.localtime(item['date'])))
			#ret.append('</div>')

		if item.has_key('media'):
			for medium in item['media']:
				ret += self.htmlify_media(medium)
		ret.append('<div class="content">')
		if item.has_key('description'):
			if convert_newlines:
				ret.append('%s' % item['description'].replace('\n', '<br/>'))
			else:
				ret.append('%s' % item['description'])
		ret.append('</div>')
		if item.has_key('link'):
			ret.append('<a href="' + item['link'] + '">' + _("Full Entry...") + '</a>')
		ret.append('</p></div>')
		return "".join(ret)
	
	def htmlify_media(self, medium):
		ret = []
		ret.append('<div class="media">')
		if medium['download_status']==D_NOT_DOWNLOADED:  
			ret.append('''<table border="0" cellpadding="0" cellspacing="12pt"><tr><td>''')
			ret.append(self._html_command('download:',medium['media_id']) + "</td><td>")
			ret.append(self._html_command('downloadqueue:',medium['media_id']) + "</td><td>")
			ret.append('(%s)</p>' % (utils.format_size(medium['size'],)) + "</td></tr></table>")
		elif medium['download_status'] == D_DOWNLOADING: 
			if self._basic_progress:
				if self._ajax_url is None:
					logging.debug('<img src="file://' + os.path.join(utils.get_glade_prefix(), "pixmaps", "throbber.gif") + '"/>')
					ret.append('<img src="file://' + os.path.join(utils.get_glade_prefix(), "pixmaps", "throbber.gif") + '"/>')
				else:
					ret.append('<img src="' + self._ajax_url + '/pixmaps/throbber.gif"/>')
				ret.append('<i>'+_('Downloading %s...') % utils.format_size(medium['size'])+'</i> '+self._html_command('pause:',medium['media_id'])+' '+self._html_command('stop:',medium['media_id']))
			elif medium.has_key('progress_message'): #downloading and we have a custom message
				if self._ajax_url is None:
					ret.append('<img src="file://' + os.path.join(utils.get_glade_prefix(), "pixmaps", "throbber.gif") + '"/>')
				else:
					ret.append('<img src="' + self._ajax_url + '/pixmaps/throbber.gif"/>')
				ret.append('<p><i>'+medium['progress_message']+'</i></p>')
				ret.append('''<table border="0" cellpadding="0" cellspacing="12pt"><tr><td>''')
				ret.append(self._html_command('pause:',medium['media_id']) + "</td><td>")
				ret.append(self._html_command('stop:',medium['media_id'])+"</td></tr></table>")
			elif self._mm.has_downloader(medium['media_id']): #we have a downloader object
				downloader = self._mm.get_downloader(medium['media_id'])
				if downloader.status == Downloader.DOWNLOADING:
					d = {'progress':downloader.progress,
						 'size':utils.format_size(medium['size'])}
					#ret.append('<p><i>'+_("Downloaded %(progress)d%% of %(size)s") % d +'</i> '+
					ret.append('''<table border="0" cellpadding="0" cellspacing="12pt">''')
					ret.append('''<tr><td rowspan="2">''')
					if self._ajax_url is None:
						ret.append('<img src="file://' + os.path.join(utils.get_glade_prefix(), "pixmaps", "throbber.gif") + '"/>')
					else:
						ret.append('<img src="' + self._ajax_url + '/pixmaps/throbber.gif"/>')
					ret.append("</td><td>")
					ret.append(self._html_progress_bar(d['progress'], d['size']) + "</td><td>")
					ret.append(self._html_command('pause:',medium['media_id']) + "</td><td>")
					ret.append(self._html_command('stop:',medium['media_id'])+"</td></tr></table>")
				elif downloader.status == Downloader.QUEUED:
					ret.append('<p><i>'+_("Download queued") +'</i></p>')
					ret.append('''<table border="0" cellpadding="0" cellspacing="12pt"><tr><td>''')
					ret.append(self._html_command('pause:',medium['media_id']) + "</td><td>")
					ret.append(self._html_command('stop:',medium['media_id'])+"</td></tr></table>")
			elif medium.has_key('progress'):       #no custom message, but we have a progress value
				d = {'progress':medium['progress'],
					 'size':utils.format_size(medium['size'])}
				#ret.append('<p><i>'+_("Downloaded %(progress)d%% of %(size)s") % d +'</i> '+
				ret.append('''<table border="0" cellpadding="0" cellspacing="12pt">''')
				ret.append('''<tr><td rowspan="2">''')
				if self._ajax_url is None:
					ret.append('<img src="file://' + os.path.join(utils.get_glade_prefix(), "pixmaps", "throbber.gif") + '"/>')
				else:
					ret.append('<img src="' + self._ajax_url + '/pixmaps/throbber.gif"/>')
				ret.append("</td><td>")
				ret.append(self._html_progress_bar(d['progress'], d['size']) + "</td><td>")
				ret.append(self._html_command('pause:',medium['media_id']) + "</td><td>")
				ret.append(self._html_command('stop:',medium['media_id'])+"</td></tr></table>")
			else:       # we have nothing to go on
				ret.append('<p><i>'+_('Downloading %s...') % utils.format_size(medium['size'])+'</i></p>')
				ret.append('''<table border="0" cellpadding="0" cellspacing="12pt"><tr><td>''')
				ret.append(self._html_command('pause:',medium['media_id']) + "</td><td>")
				ret.append(self._html_command('stop:',medium['media_id'])+"</td></tr></table>")
		elif medium['download_status'] == D_DOWNLOADED:
			if self._mm.has_downloader(medium['media_id']):	
				downloader = self._mm.get_downloader(medium['media_id'])
				ret.append('<p>'+ str(downloader.message)+'</p>')
			filename = medium['file'][medium['file'].rfind("/")+1:]
			if utils.is_known_media(medium['file']): #we have a handler
				if os.path.isdir(medium['file']) and medium['file'][-1]!='/':
					medium['file']=medium['file']+'/'
				ret.append('''<table border="0" cellpadding="0" cellspacing="12pt"><tr><td>''')
				ret.append(self._html_command('play:',medium['media_id']) + "</td><td>")
				ret.append(self._html_command('redownload',medium['media_id']) + "</td><td>")
				ret.append(self._html_command('delete:',medium['media_id'])+"</td></tr>")
				ret.append('<tr><td colspan="3"><font size="3">(<a href="reveal://%s">%s</a>: %s)</font></td></tr></table>' % (medium['file'], filename, utils.format_size(medium['size'])))
			elif os.path.isdir(medium['file']): #it's a folder
				ret.append('''<table border="0" cellpadding="0" cellspacing="12pt"><tr><td>''')
				ret.append(self._html_command('file://',medium['file']) + "</td><td>")
				ret.append(self._html_command('redownload',medium['media_id']) + "</td><td>")
				ret.append(self._html_command('delete:',medium['media_id'])+"</td></tr></table>")
			else:                               #we have no idea what this is
				ret.append('''<table border="0" cellpadding="0" cellspacing="12pt"><tr><td>''')
				ret.append(self._html_command('file://',medium['file']) + "</td><td>")
				ret.append(self._html_command('redownload',medium['media_id']) + "</td><td>")
				ret.append(self._html_command('delete:',medium['media_id'])+"</td></tr>")
				ret.append('<tr><td colspan="3"><font size="3">(<a href="reveal://%s">%s</a>: %s)</font></td></tr></table>' % (medium['file'], filename, utils.format_size(medium['size'])))
		elif medium['download_status'] == D_RESUMABLE:
			ret.append('''<table border="0" cellpadding="0" cellspacing="12pt"><tr><td>''')
			ret.append(self._html_command('resume:',medium['media_id']) + "</td><td>")
			ret.append(self._html_command('redownload',medium['media_id']) + "</td><td>")
			ret.append(self._html_command('delete:',medium['media_id'])+"</td></tr><tr><td>")
			ret.append('(%s)</td></tr></table>' % (utils.format_size(medium['size']),))	
		elif medium['download_status'] == D_ERROR:
			if self._mm.has_downloader(medium['media_id']):	
				downloader = self._mm.get_downloader(medium['media_id'])
				error_msg = downloader.message
			else:
				error_msg = _("There was an error downloading the file.")
			ret.append('''<table border="0" cellpadding="0" cellspacing="12pt"><tr><td>''')
			ret.append(medium['url'][medium['url'].rfind('/')+1:]+': '+str(error_msg) + "</td><td>")
			ret.append(self._html_command('retry',medium['media_id']) + "</td><td>")
			ret.append(self._html_command('tryresume:',medium['media_id']) + "</td><td>")
			ret.append(self._html_command('cancel:',medium['media_id'])+"</td></tr><tr><td>")
			ret.append('(%s)</td></tr></table>' % (utils.format_size(medium['size']),))
		ret.append('</div>')
		return ret
		
	commands={	'play:': (_("Open with PenguinTV"), "gtk-media-play-ltr"), #FIXME: detect rtl ltr i18n
			'download:': (_("Download"), "gtk-go-down"),
			'downloadqueue:': (_("Download And Open"), "gtk-go-down"),
			'pause:': (_("Pause"), "gtk-media-pause"),
			'cancel:': (_("Cancel"), "gtk-cancel"),
			'file://': (_("Open File"), "gtk-open"),
			'delete:': (_("Delete"), "gtk-delete"),
			'resume:': (_("Resume"), "gtk-go-down"),
			'clear:': (_("Cancel"), "gtk-cancel"),
			'stop:': (_("Stop"), "gtk-stop"),
			'tryresume:': (("Try Resume"),	"gtk-go-down")}
			
	if utils.RUNNING_HILDON:
		commands['play:'] = (_("Open with Media Player"), "gtk-media-play-ltr")
	
	def _html_command(self, command,arg):
		"""returns something like '<a href="play:%s">Open</a>' for all the commands I have.
		Dictionary has keys of commands, and returns located strings.  If ajax_url is given,
		return the icon name appended to it.  Otherwise return a file:/// version"""
	
		theme = gtk.icon_theme_get_default()
	
		def _get_img_html(icon_name, ajax_url=None):
			if self._ajax_url is not None:
				return '<img src="' + self._ajax_url + "/icon/" + icon_name + '"/>'
			else:
				iconinfo = theme.lookup_icon(icon_name, 16, gtk.ICON_LOOKUP_NO_SVG)
				icon_markup = ""
				if iconinfo is not None:
					icon_filename = iconinfo.get_filename()
					return '<img src="file://' + icon_filename + '"/>'
				return ""
	
		#a couple special cases
		if command == "redownload":
			return ' <a href="download:'+str(arg)+'">'+_get_img_html(self.commands['download:'][1], self._ajax_url)+_("Re-Download")+"</a>"
		
		if command == "retry":
			return ' <a href="download:'+str(arg)+'">'+_get_img_html(self.commands['download:'][1], self._ajax_url)+_("Retry")+'</a>'
	
		return ' <a href="'+command+str(arg)+'">'+_get_img_html(self.commands[command][1], self._ajax_url)+self.commands[command][0]+'</a>'

		
	def _html_progress_bar(self, percent, size):
		ret = []
		
		width = 200
		height = 15
		bar_color = "#333333"
		
		ret.append('''<table style="text-align: left; padding:0px;" border="0" cellpadding="0" cellspacing="10px"><tr><td>''')
		ret.append("""<div id="empty" style="background-color:#cccccc;border:1px solid black;height:%ipx;width:%ipx;padding:0px;" align="left">""" % (height, width))
		#ret.append("""<div id="d1" style="position:relative;top:0px;left:0px;color:#f0ffff;height:%ipx;text-align:center;font:bold;font-size:%ipxpadding:0px;padding-top:0px;">%i%%""" % (height, height * 0.8, percent))
		ret.append("""<div id="d2" style="position:relative;top:0px;left:0px;background-color:%s;height:%ipx;width:%ipx;padding-top:5px;padding:0px;">""" % (bar_color, height, percent * (width / 100)))
		ret.append("""</div></div></td><td>""")
		ret.append(""" (%s)""" % (size,))
		ret.append("""</td></tr></table>""")
		return "\n".join(ret)

class HTMLimgParser(htmllib.HTMLParser):
	def __init__(self):
		htmllib.HTMLParser.__init__(self, formatter.NullFormatter())
		self.images=[]
		
	def do_img(self, attributes):
		for name, value in attributes:
			if name == 'src':
				new_image = value
				self.images.append(new_image)
				
class HTMLHighlightParser(HTMLParser.HTMLParser):
	def __init__(self, highlight_terms):
		HTMLParser.HTMLParser.__init__(self)
		highlight_terms = highlight_terms.replace('"','')
		highlight_terms = highlight_terms.replace("'",'')
		self.terms = [a.upper() for a in highlight_terms.split() if len(a)>2]
		self.new_data = ""
		self.style_start="""<span style="background-color: #ffff00">"""
		self.style_end  ="</span>"
		self.tag_stack = []
		
	def handle_starttag(self, tag, attrs):
		if len(attrs)>0:
			self.new_data+="<"+str(tag)+" "+" ".join([i[0]+"=\""+i[1]+"\"" for i in attrs])+">"
		else:
			self.new_data+="<"+str(tag)+">"
		self.tag_stack.append(tag)
			
	def handle_startendtag(self, tag, attrs):
		if len(attrs)>0:
			self.new_data+="<"+str(tag)+" "+" ".join([i[0]+"=\""+i[1]+"\"" for i in attrs])+"/>"
		else:
			self.new_data+="<"+str(tag)+"/>"
		self.tag_stack.pop(-1)
			
	def handle_endtag(self, tag):
		self.new_data+="</"+str(tag)+">"
	
	def handle_data(self, data):
		data_u = data.upper()
		if self.tag_stack[-1] != "style":
			for term in self.terms:
				l = len(term)
				place = 0
				while place != -1:
					#we will never match on the replacement style because the replacement is all 
					#lowercase and the terms are all uppercase
					place = data_u.find(term, place)
					if place == -1:
						break
					data   = data  [:place] + self.style_start + data  [place:place+l] + self.style_end + data  [place+l:]
					data_u = data_u[:place] + self.style_start + data_u[place:place+l] + self.style_end + data_u[place+l:]
					place+=len(self.style_start)+len(term)+len(self.style_end)
		self.new_data+=data
		
class HTMLImgAuthParser(HTMLParser.HTMLParser):
	def __init__(self, domain, userpass):
		HTMLParser.HTMLParser.__init__(self)
		self._domain = domain
		self._userpass = userpass
		self.new_data = ""
		
	def handle_starttag(self, tag, attrs):
		new_attrs = []
		if tag.upper() != "A":
			for a in attrs:
				if a[1] is not None:
					attr = (a[0], a[1].replace(self._domain, self._userpass+"@"+self._domain))
				else:
					attr = (a[0], "")
				new_attrs.append(attr)
			attrs = new_attrs
		else:
			pass# "not doing link tag"
		if len(attrs)>0:
			self.new_data+="<"+str(tag)+" "+" ".join([i[0]+"=\""+i[1]+"\"" for i in attrs])+">"
		else:
			self.new_data+="<"+str(tag)+">"
		
	def handle_endtag(self, tag):
		self.new_data+="</"+str(tag)+">"
		
	def handle_startendtag(self, tag, attrs):
		new_attrs = []
		for a in attrs:
			if a[1] is not None:
				attr = (a[0], a[1].replace(self._domain, self._userpass+"@"+self._domain))
			else:
				attr = (a[0], "")
			new_attrs.append(attr)
		attrs = new_attrs
		if len(attrs)>0:
			self.new_data+="<"+str(tag)+" "+" ".join([i[0]+"=\""+i[1]+"\"" for i in attrs])+">"
		else:
			self.new_data+="<"+str(tag)+">"
		
	def handle_data(self, data):
		self.new_data+=data

