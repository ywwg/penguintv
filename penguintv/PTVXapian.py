import os, os.path
import utils
import logging
from threading import Lock, Thread
from time import sleep
import HTMLParser

import xapian

try:
	import sqlite3 as sqlite
except:
	from pysqlite2 import dbapi2 as sqlite


"""
This class does the searching for PenguinTV.  It has full access to its own database object.
"""

ENTRY_LIMIT=100

DATE = 0
FEED_ID = 1
ENTRY_ID = 2
ENTRY_TITLE = 3

class PTVXapian:
	def __init__(self):
		self.home = utils.get_home()
		try:
			os.stat(self.home)
		except:
			try:
				os.mkdir(self.home)
			except:
				raise DBError, "error creating directories: "+self.home
		self._storeDir = os.path.join(self.home, "xapian_store")
		
		self.needs_index = False
		
		try:
			os.stat(os.path.join(self._storeDir,"NEEDSREINDEX"))
			#if that exists, we need to reindex
			self.needs_index = True
		except:
			pass
		if self.needs_index:
			try:
				os.remove(os.path.join(self._storeDir,"NEEDSREINDEX"))
			except:
				logging.error("Error removing NEEDSREINDEX... check permisions inside %s" % self.home)
		
		if not os.path.exists(self._storeDir):
			os.mkdir(self._storeDir)
			self.needs_index = True
			
		self._index_lock = Lock()
		self._quitting = False
		
	def finish(self, needs_index=False):
		if needs_index:
			self._interrupt()
		self._quitting = True
		

	def _interrupt(self):
		f = open(os.path.join(self._storeDir,"NEEDSREINDEX"),"w")
		f.close()
		
	def _get_db(self):
		try:	
			if os.path.isfile(os.path.join(self.home,"penguintv4.db")) == False:
				raise DBError,"database file missing"
			db=sqlite.connect(os.path.join(self.home,"penguintv4.db"), timeout=10)
			db.isolation_level="DEFERRED"
			return db
		except:
			raise DBError, "Error connecting to database in Xapian module"
		
	def Do_Index_Threaded(self, callback):
		Thread(target=self.Do_Index, args=(callback,)).start()
		
	def Do_Index(self, callback=None):
		"""loop through all feeds and entries and feed them to the beast"""
		
		def index_interrupt():
			writer.close()
			self._index_lock.release()
			if callback is not None:
				callback()
			self._interrupt()
			return
			
		if not self._index_lock.acquire(False):
			logging.info("already indexing, not trying to reindex again")
			return
			
		db = self._get_db()
		c = db.cursor()
		
		#remove existing DB
		utils.deltree(self._storeDir)
		
		database = xapian.WritableDatabase(self._storeDir, xapian.DB_CREATE_OR_OPEN)
		indexer = xapian.TermGenerator()
		stemmer = xapian.Stem("english")
		indexer.set_stemmer(stemmer)
		
		c.execute(u"""SELECT id, title, description FROM feeds""")
		feeds = c.fetchall()
		c.execute(u"""SELECT id, feed_id, title, description,fakedate FROM entries ORDER BY fakedate""")
		entries = c.fetchall()
		c.close()
		db.close()
		
		logging.info("indexing feeds")
		
		def feed_index_generator(feeds):			
			for feed_id, title, description in feeds:
				try:
					doc = xapian.Document() 
					
					forindex = title+" "+description
					
					#eh?  we can only remove docs by term, but we can only
					#get values.  so we need both it seems
					doc.add_term("f"+str(feed_id))
					doc.add_value(FEED_ID, str(feed_id))
					doc.add_value(DATE, "")
					
					doc.set_data(forindex)
					indexer.set_document(doc)
					indexer.index_text(forindex)
					
					database.add_document(doc)
				except Exception, e:
					logging.error("Failed in indexDocs, feeds: %s" % str(e))
				#sleep(0)   #http://twistedmatrix.com/pipermail/twisted-python/2005-July/011052.html           
				yield None
		
		for i in feed_index_generator(feeds):
			if self._quitting:
				return index_interrupt()

		logging.info("indexing entries")
		
		def entry_index_generator(entries):
			for entry_id, feed_id, title, description, fakedate in entries:
				try:
					doc = xapian.Document()
					p = HTMLDataParser()
					p.feed(description)
					description = p.data
					
					forindex = title+" "+description
					
					doc.add_term("e"+str(entry_id))
					doc.add_term("f"+str(feed_id))
					doc.add_value(FEED_ID, str(feed_id))
					doc.add_value(ENTRY_ID, str(entry_id))
					doc.add_value(ENTRY_TITLE, title)
					doc.add_value(DATE, str(fakedate))
					
					doc.set_data(forindex)
					indexer.set_document(doc)
					indexer.index_text(forindex)
					
					database.add_document(doc)
				except Exception, e:
					logging.error("Failed in indexDocs, entries:" + str(e))
				#sleep(.005)
				yield None
				
		for i in entry_index_generator(entries):
			if self._quitting:
				return index_interrupt()
				
		self._index_lock.release()
		if callback is not None:
			callback()
		
	def Re_Index_Threaded(self,feedlist=[], entrylist=[]):
		PythonThread(target=self.Re_Index, args=(feedlist,entrylist)).start()
		
	def Re_Index(self, feedlist=[], entrylist=[]):
		if len(feedlist) == 0 and len(entrylist) == 0:
			return
			
		def reindex_interrupt():
			indexModifier.close()
			self._index_lock.release()
			self._interrupt()
			return
			
		self._index_lock.acquire()
		db = self._get_db()
		c = db.cursor()
					
		database = xapian.WritableDatabase(self._storeDir, xapian.DB_CREATE_OR_OPEN)
		indexer = xapian.TermGenerator()
		stemmer = xapian.Stem("english")
		indexer.set_stemmer(stemmer)
		
		feedlist = utils.uniquer(feedlist)
		entrylist = utils.uniquer(entrylist)
		
		feed_addition = []
		entry_addition = []
	
		for feed_id in feedlist:
			if self._quitting:
				return reindex_interrupt()
			try:
				c.execute(u"""SELECT title, description FROM feeds WHERE id=?""",(feed_id,))
				title, description = c.fetchone()
				feed_addition.append((feed_id, title, description))
			except TypeError:
				pass #it won't be readded.  Assumption is we have deleted this feed

		for entry_id in entrylist:
			if self._quitting:
				return reindex_interrupt()
			try:
				c.execute(u"""SELECT feed_id, title, description, fakedate FROM entries WHERE id=?""",(entry_id,))
				feed_id, title, description, fakedate = c.fetchone()
				entry_addition.append((entry_id, feed_id, title, description, fakedate))
			except TypeError:
				pass
				
		c.close()
		db.close()
		
		entry_addition = utils.uniquer(entry_addition)
				
		if self._quitting:
			return reindex_interrupt()
		#first delete anything deleted or changed
		for feed_id in feedlist:
			try:
				database.delete_document("f"+str(feed_id))
			except Exception, e:
				logging.error("Failed deleting feed: %s" % str(e))
				
		for entry_id in entrylist:
			try:
				database.delete_document("e"+str(entry_id))
			except Exception, e:
				logging.error("Failed deleting entry: %s" % str(e))
			
		#now add back the changes
		#print [f[0] for f in feed_addition]
		for feed_id, title, description in feed_addition:
			if self._quitting:
				return reindex_interrupt()
			try:
				doc = xapian.Document() 
					
				forindex = title+" "+description
				
				doc.add_term("f"+str(feed_id))
				doc.add_value(FEED_ID, str(feed_id))
				doc.add_value(DATE, "")
				
				doc.set_data(forindex)
				indexer.set_document(doc)
				indexer.index_text(forindex)
				
				database.add_document(doc)
			except Exception, e:
				logging.error("Failed adding feed: %s" % str(e))
		
		#print [(e[0],e[1]) for e in entry_addition]
		for entry_id, feed_id, title, description, fakedate in entry_addition:
			if self._quitting:
				return reindex_interrupt()
			try:
				doc = xapian.Document()
				p = HTMLDataParser()
				p.feed(description)
				description = p.data
				
				forindex = title+" "+description
				
				doc.add_term("e"+str(entry_id))
				doc.add_term("f"+str(feed_id))
				doc.add_value(FEED_ID, str(feed_id))
				doc.add_value(ENTRY_ID, str(entry_id))
				doc.add_value(ENTRY_TITLE, title)
				doc.add_value(DATE, str(fakedate))
				
				doc.set_data(forindex)
				indexer.set_document(doc)
				indexer.index_text(forindex)
				
				database.add_document(doc)
			except Exception, e:
				logging.error("Failed adding entry: %s" % str(e))
				
		self._index_lock.release()
						
	def Search(self, command, blacklist=[], include=['feeds','entries'], since=0):
		"""returns two lists, one of search results in feeds, and one for results in entries.  It
		is sorted so that title results are first, description results are second"""
		
		if not self._index_lock.acquire(False):
			#if we are indexing, don't try to search
			#print "wouldn't get lock"
			return ([],[])
		self._index_lock.release()
		
		
		database = xapian.Database(self._storeDir)
		enquire = xapian.Enquire(database)
		
		qp = xapian.QueryParser()
		stemmer = xapian.Stem("english")
		qp.set_stemmer(stemmer)
		qp.set_database(database)
		qp.set_stemming_strategy(xapian.QueryParser.STEM_SOME)
		
		enquire.set_docid_order(xapian.Enquire.DESCENDING)
		enquire.set_weighting_scheme(xapian.BoolWeight())

		# Display the results.
		#print "%i results found." % matches.get_matches_estimated()
		#print "Results 1-%i:" % matches.size()

		#for m in matches:
		#    print "%i: %i%% docid=%i [%s] %s %s %s" % (m.rank + 1, m.percent, m.docid, m.document.get_data()[0:100], m.document.get_value(0), m.document.get_value(1), m.document.get_value(2))
		
		feed_results=[]
		entry_results=[]
		
		query = qp.parse_query(command)
		enquire.set_query(query)		
		matches = enquire.get_mset(0, 100)
		for m in matches:
			doc = m.document
			feed_id = doc.get_value(FEED_ID)
			feed_id = int(feed_id)
			try:
				if feed_id not in blacklist:
					entry_id = doc.get_value(ENTRY_ID)
					if entry_id is '': # meaning this is actually a feed (we could know that from above, but eh)
						feed_results.append(int(feed_id))
					else: # meaning "entry"
						title    = doc.get_value(ENTRY_TITLE)
						fakedate = float(doc.get_value(DATE)) / 1000.0
						if fakedate > since:
							entry_results.append((int(entry_id),title, fakedate, feed_id))
				#else:
				#	print "excluding:"+doc.get("title")
			except Exception, e:
				print e
				print feed_id
				print blacklist

		for entry in entry_results:
			feed_results.append(entry[3])
			
		feed_results = utils.uniquer(feed_results)
		entry_results = utils.uniquer(entry_results)	
		#need to resort because we merged two lists together
		entry_results.sort(lambda x,y: int(y[2] - x[2]))
		#for e in entry_results:
		#	print e[2],e[1]
		return (feed_results, entry_results)
		
	def merge(self, l1, l2):
		"""merges two sorted lists"""
		if len(l1)>len(l2):
			l3 = l1
			l1 = l2
			l2 = l3
			del l3
		i=-1
		for term,freq in l1:
			i+=1
			while term > l2[i][0]:
				i+=1
				if i>=len(l2):break
			if i >= len(l2):
				l2.append((term,freq))
				break
			if term == l2[i][0]:
				l2[i] = (l2[i][0], l2[i][1] + freq)
			if term < l2[i][0]:
				l2.insert(i,(term,freq))
		return l2

		
class DBError(Exception):
	def __init__(self,error):
		self.error = error
	def __str__(self):
		return self.error		
		
class HTMLDataParser(HTMLParser.HTMLParser):
	def __init__(self):
		HTMLParser.HTMLParser.__init__(self)
		self.data = ""
	def handle_data(self, data):
		self.data+=data

