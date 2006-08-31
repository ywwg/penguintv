from PyLucene import *
import os
import utils
from pysqlite2 import dbapi2 as sqlite
from threading import Lock
import HTMLParser

"""
This class does the searching for PenguinTV.  It has full access to its own database object.
"""

ENTRY_LIMIT=100

class Lucene:
	def __init__(self):
		try:
			self.home=os.getenv('HOME')
			os.stat(self.home+"/.penguintv")
		except:
			try:
				os.mkdir(self.home+"/.penguintv")
			except:
				raise DBError, "error creating directories: "+self.home+"/.penguintv"
		self.storeDir = self.home+"/.penguintv/search_store"
		self.needs_index = False
		if not os.path.exists(self.storeDir):
			os.mkdir(self.storeDir)
			self.needs_index = True
			
		self.index_lock = Lock()
		
	def _get_db(self):
		try:	
			if os.path.isfile(self.home+"/.penguintv/penguintv3.db") == False:
				raise DBError,"database file missing"
			db=sqlite.connect(self.home+"/.penguintv/penguintv3.db", timeout=10	)
			db.isolation_level="DEFERRED"
			return db
		except:
			raise DBError, "Error connecting to database in Lucene module"
		
	def Do_Index_Threaded(self, callback):
		PythonThread(target=self.Do_Index, args=(callback,)).start()
		
	def Do_Index(self, callback=None):
		"""loop through all feeds and entries and feed them to the beast"""
		self.index_lock.acquire()
		db = self._get_db()
		c = db.cursor()
		
		analyzer = StandardAnalyzer()
		store = FSDirectory.getDirectory(self.storeDir, True)
		writer = IndexWriter(store, analyzer, True)
				
		c.execute(u"""SELECT id, title, description FROM feeds""")
		feeds = c.fetchall()
		c.execute(u"""SELECT id, feed_id, title, description,fakedate FROM entries""")
		entries = c.fetchall()
		c.close()
		db.close()
		
		print "indexing feeds"
		for feed_id, title, description in feeds:
			try:
				doc = Document()
				doc.add(Field("feed_id", str(feed_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))
				doc.add(Field("title", title,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))   
				doc.add(Field("description", description,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))       
				writer.addDocument(doc)  
			except Exception, e:
				print "Failed in indexDocs:", e                      
		
		print  "indexing entries"
		
		for entry_id, feed_id, title, description, fakedate in entries:
			try:
				doc = Document()
				p = HTMLDataParser()
				p.feed(description)
				description = p.data
				doc.add(Field("entry_id", str(entry_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))
				doc.add(Field("feed_id", str(feed_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))	                                           
				doc.add(Field("fakedate", str(fakedate), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))	                                           
				doc.add(Field("title",title,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))   
				doc.add(Field("description", description,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))       
				writer.addDocument(doc)  
			except Exception, e:
				print "Failed in indexDocs:", e    
				
		print "optimizing"
		writer.optimize()
		writer.close()
		print "done indexing"
		self.index_lock.release()
		if callback is not None:
			callback()
		
	def Re_Index_Threaded(self,feedlist=[], entrylist=[]):
		PythonThread(target=self.Re_Index, args=(feedlist,entrylist)).start()
		
	def Re_Index(self, feedlist=[], entrylist=[]):
		if len(feedlist)==0 and len(entrylist)==0:
			return
		self.index_lock.acquire()
		db = self._get_db()
		c = db.cursor()
					
		analyzer = StandardAnalyzer()
		indexModifier = IndexModifier(self.storeDir, analyzer, False)
		
		feed_addition = []
		entry_addition = []
	
		feeds = c.execute(u"""SELECT id FROM feeds""")
		
		for feed_id in feedlist:
			try:
				c.execute(u"""SELECT title, description FROM feeds WHERE id=?""",(feed_id,))
				title, description = c.fetchone()
				feed_addition.append((feed_id, title, description))
			except TypeError:
				pass #it won't be readded.  Assumption is we have deleted this feed

		for entry_id in entrylist:
			try:
				c.execute(u"""SELECT feed_id, title, description, fakedate FROM entries WHERE id=?""",(entry_id,))
				feed_id, title, description, fakedate = c.fetchone()
				entry_addition.append((entry_id, feed_id, title, description, fakedate))
			except TypeError:
				pass
				
		c.close()
		db.close()
				
		#first delete anything deleted or changed
		for feed_id in feedlist:
			try:
				indexModifier.deleteDocuments(Term("id","feed "+str(feed_id)))
			except Exception, e:
				print "Failed deleting feed:", e
				
		for entry_id in entrylist:
			try:
				indexModifier.deleteDocuments(Term("id","entry "+str(entry_id)))
			except Exception, e:
				print "Failed deleting entry:", e
			
		#now add back the changes
		for feed_id, title, description in feed_addition:
			try:
				doc = Document()
				doc.add(Field("feed_id", str(feed_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))
				doc.add(Field("title",title,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))   
				doc.add(Field("description", description,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))
				indexModifier.addDocument(doc)
			except Exception, e:
				print "Failed adding feed:", e
		
		for entry_id, feed_id, title, description, fakedate in entry_addition:
			try:
				doc = Document()
				p = HTMLDataParser()
				p.feed(description)
				description = p.data
				doc.add(Field("entry_id", str(entry_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))
				doc.add(Field("feed_id", str(feed_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))	
				doc.add(Field("fakedate", str(fakedate), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))	
				doc.add(Field("title",title,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))   
				doc.add(Field("description", description,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))
				indexModifier.addDocument(doc)
			except Exception, e:
				print "Failed adding entry:", e
				
		indexModifier.flush()
		indexModifier.close()
		self.index_lock.release()
						
	def Search(self, command, blacklist=[]):
		"""returns two lists, one of search results in feeds, and one for results in entries.  It
		is sorted so that title results are first, description results are second"""
		analyzer = StandardAnalyzer()
		directory = FSDirectory.getDirectory(self.storeDir, False)
		searcher = IndexSearcher(directory)
		
		feed_results=[]
		entry_results=[]
		
		#MultiFiendQuery has a bug in 2.0.0... for now don't use
		#queryparser = MultiFieldQueryParser(['title','description'], self.analyzer)
		#query = MultiFiendQueryParser.parse(command, ['title','description'], self.analyzer)

		#query TITLES
		queryparser = QueryParser("title", analyzer)
		query = QueryParser.parse(queryparser, command)
		
		def build_results(hits):
			"""we use this twice, so save some typing"""
			for i, doc in hits:
				feed_id  = int(doc.get("feed_id"))
				try:
					if feed_id not in blacklist:
						entry_id = doc.get("entry_id")
						if entry_id is None: #meaning this is actually a feed
							feed_results.append(int(feed_id))
						else: #               meaning "entry"
							if len(entry_results) < ENTRY_LIMIT:
								title    = doc.get("title")
								desc     = doc.get("description")
								fakedate = float(doc.get("fakedate"))
								entry_results.append((int(entry_id),title, fakedate, feed_id))
					#else:
					#	print "excluding:"+doc.get("title")
				except Exception, e:
					print e
					print feed_id
					print self.blacklist
		
		hits = searcher.search(query)
		build_results(hits)
		#print "%s total matching document titles." % hits.length()
		
		for entry in entry_results: #also add feed results so that they show up in the feed list too
			feed_results.append(entry[1])
			
		#query DESCRIPTIONS		
		queryparser = QueryParser("description", analyzer)
		query = QueryParser.parse(queryparser, command)
		hits = searcher.search(query)
		#print "%s total matching document descriptions." % hits.length()
		build_results(hits)
		
		for entry in entry_results:
			feed_results.append(entry[3]) #this redoes the stuff at the top, but I 
										  #don't care because we are going to pare down the list
		feed_results = utils.uniquer(feed_results)
		entry_results = utils.uniquer(entry_results)	
		#sort by date:
		#entry_results.sort(lambda x,y: int(y[2]-x[2]))
		searcher.close()    
		return (feed_results, entry_results)
		
	def get_popular_terms(self, max_terms=100, junkWords=[], fields=[]):
		#ported from http://www.getopt.org/luke/ HighFreqTerms.java
		self.index_lock.acquire()
		def insert(l, val):
			i=-1
			for item in l:
				i+=1
				if val[1]>item[1]:
					l.insert(i, val)
					return
			l.append(val)
			
		
		reader = IndexReader.open(self.storeDir)
		terms = reader.terms()
		pop_terms = []
           
		minFreq = 0
		while terms.next():
			term = terms.term()
			field = term.field()
			if len(fields)>0:
				if field not in fields:
					continue
			if term.text() in junkWords:
				continue
			try:
				i = float(term.text())
				continue
			except:
				pass
			if terms.docFreq() > minFreq:
				insert(pop_terms, (term.text(), terms.docFreq()))
				if max_terms>0 and len(pop_terms) >= max_terms:
					pop_terms.pop(-1)
					minFreq = pop_terms[-1][1]
	
		self.index_lock.release()
		return pop_terms
		
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
