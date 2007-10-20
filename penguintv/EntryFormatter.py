import os, os.path
import htmllib, HTMLParser
import time

from ptvDB import D_NOT_DOWNLOADED, D_DOWNLOADING, D_DOWNLOADED, D_RESUMABLE, \
				  D_ERROR, D_WARNING
import Downloader
import utils

GTKHTML=0
MOZILLA=1

class EntryFormatter:
	def __init__(self, mm=None, with_feed_titles=False, indicate_new=False, basic_progress=False, auto_mark=True):
		self._mm = mm
		self._with_feed_titles = with_feed_titles
		self._indicate_new = indicate_new
		self._basic_progress = basic_progress
		self._auto_mark = auto_mark
		
	def htmlify_item(self, item, convert_newlines=False):
		""" Take an item as returned from ptvDB and turn it into an HTML page.  Very messy at times,
			but there are lots of alternate designs depending on the status of media. """

		#global download_status
		ret = []
		#ret.append('<div class="heading">')
		if self._indicate_new:
			if item['new']:
				ret.append('<div class="entry_new">')
			else:
				ret.append('<div class="entry_old">')
		else:
			ret.append('<div class="entry">')

		ret.append('''<table style="text-align: left; width: 100%;" border="0" cellpadding="0" cellspacing="0"><tr><td>''')

		if self._with_feed_titles:
			if item.has_key('title') and item.has_key('feed_title'):
				ret.append('<div class="stitle">%s<br/>%s</div>' % (item['feed_title'],item['title']))
		else:
			if item.has_key('title'):
				if self._indicate_new and item['new']:
					ret.append('<div class="stitle"><a href="#%s"></a>&#10036;%s</div>' % (item['entry_id'],item['title']))
				else:
					ret.append('<div class="stitle"><a href="#%s"></a>%s</div>' % (item['entry_id'],item['title']))

		ret.append('</td><td style="text-align: right;">')

		cb_status = item['read'] and "CHECKED" or "UNCHECKED"
		cb_function = item['read'] and "unread" or "read"

		ret.append('''<form id="read"> <input type="checkbox" id="read" name="read" class="radio" onclick="parent.location='%s:%i'" %s>%s</form>''' % (cb_function, item['entry_id'], cb_status, _('Read')))

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
			ret.append('<p>'+utils.html_command('download:',medium['media_id'])+' '+
							 utils.html_command('downloadqueue:',medium['media_id'])+
						     ' (%s)</p>' % (utils.format_size(medium['size'],)))
		elif medium['download_status'] == D_DOWNLOADING: 
			if self._basic_progress:
				ret.append('<p><i>'+_('Downloading %s...') % utils.format_size(medium['size'])+'</i> '+utils.html_command('pause:',medium['media_id'])+' '+utils.html_command('stop:',medium['media_id'])+'</p>')
			elif medium.has_key('progress_message'): #downloading and we have a custom message
				ret.append('<p><i>'+medium['progress_message']+'</i> '+
					                utils.html_command('pause:',medium['media_id'])+' '+
					                utils.html_command('stop:',medium['media_id'])+'</p>')
			elif self._mm.has_downloader(medium['media_id']): #we have a downloader object
				downloader = self._mm.get_downloader(medium['media_id'])
				if downloader.status == Downloader.DOWNLOADING:
					d = {'progress':downloader.progress,
						 'size':utils.format_size(medium['size'])}
					ret.append('<p><i>'+_("Downloaded %(progress)d%% of %(size)s") % d +'</i> '+
						        utils.html_command('pause:',medium['media_id'])+' '+
						        utils.html_command('stop:',medium['media_id'])+'</p>')
				elif downloader.status == Downloader.QUEUED:
					ret.append('<p><i>'+_("Download queued") +'</i> '+
						        utils.html_command('pause:',medium['media_id'])+' '+
						        utils.html_command('stop:',medium['media_id'])+'</p>')
			elif medium.has_key('progress'):       #no custom message, but we have a progress value
				d = {'progress':medium['progress'],
					 'size':utils.format_size(medium['size'])}
				ret.append('<p><i>'+_("Downloaded %(progress)d%% of %(size)s") % d +'</i> '+
					        utils.html_command('pause:',medium['media_id'])+' '+
					        utils.html_command('stop:',medium['media_id'])+'</p>')
			else:       # we have nothing to go on
				ret.append('<p><i>'+_('Downloading %s...') % utils.format_size(medium['size'])+'</i> '+utils.html_command('pause:',medium['media_id'])+' '+utils.html_command('stop:',medium['media_id'])+'</p>')
		elif medium['download_status'] == D_DOWNLOADED:
			if self._mm.has_downloader(medium['media_id']):	
				downloader = self._mm.get_downloader(medium['media_id'])
				ret.append('<p>'+ str(downloader.message)+'</p>')
			filename = medium['file'][medium['file'].rfind("/")+1:]
			if utils.is_known_media(medium['file']): #we have a handler
				if os.path.isdir(medium['file']) and medium['file'][-1]!='/':
					medium['file']=medium['file']+'/'
				ret.append('<p>'+utils.html_command('play:',medium['media_id'])+' '+
								 utils.html_command('redownload',medium['media_id'])+' '+
								 utils.html_command('delete:',medium['media_id'])+' <br/><font size="3">(<a href="reveal://%s">%s</a>: %s)</font></p>' % (medium['file'], filename, utils.format_size(medium['size'])))
			elif os.path.isdir(medium['file']): #it's a folder
				ret.append('<p>'+utils.html_command('file://',medium['file'])+' '+
								 utils.html_command('redownload',medium['media_id'])+' '+
								 utils.html_command('delete:',medium['media_id'])+'</p>')
			else:                               #we have no idea what this is
				ret.append('<p>'+utils.html_command('file://',medium['file'])+' '+
								 utils.html_command('redownload',medium['media_id'])+' '+
								 utils.html_command('delete:',medium['media_id'])+' <br/><font size="3">(<a href="reveal://%s">%s</a>: %s)</font></p>' % (medium['file'], filename, utils.format_size(medium['size'])))
		elif medium['download_status'] == D_RESUMABLE:
			ret.append('<p>'+utils.html_command('resume:',medium['media_id'])+' '+
							 utils.html_command('redownload',medium['media_id'])+' '+
							 utils.html_command('delete:',medium['media_id'])+'(%s)</p>' % (utils.format_size(medium['size']),))	
		elif medium['download_status'] == D_ERROR:
			if self._mm.has_downloader(medium['media_id']):	
				downloader = self._mm.get_downloader(medium['media_id'])
				error_msg = downloader.message
			else:
				error_msg = _("There was an error downloading the file.")
			ret.append('<p>'+medium['url'][medium['url'].rfind('/')+1:]+': '+str(error_msg)+'  '+
									 utils.html_command('retry',medium['media_id'])+' '+
									 utils.html_command('tryresume:',medium['media_id'])+' '+
									 utils.html_command('cancel:',medium['media_id'])+'(%s)</p>' % (utils.format_size(medium['size']),))
		ret.append('</div>')
		return ret

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
		self.terms = [a.upper() for a in highlight_terms.split() if len(a)>3]
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
				attr = (a[0], a[1].replace(self._domain, self._userpass+"@"+self._domain))
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
			attr = (a[0], a[1].replace(self._domain, self._userpass+"@"+self._domain))
			new_attrs.append(attr)
		attrs = new_attrs
		if len(attrs)>0:
			self.new_data+="<"+str(tag)+" "+" ".join([i[0]+"=\""+i[1]+"\"" for i in attrs])+">"
		else:
			self.new_data+="<"+str(tag)+">"
		
	def handle_data(self, data):
		self.new_data+=data

