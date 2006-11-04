from PyLucene import *
import os, os.path
import utils
from pysqlite2 import dbapi2 as sqlite
from threading import Lock
import HTMLParser
from time import sleep

"""
This class does the searching for PenguinTV.  It has full access to its own database object.
"""

ENTRY_LIMIT=100

class Lucene:
	def __init__(self):
		if utils.RUNNING_SUGAR:
			import sugar.env
			self.home = os.path.join(sugar.env.get_profile_path(), 'penguintv')
		else:
			self.home = os.path.join(os.getenv('HOME'), ".penguintv")
		try:
			os.stat(self.home)
		except:
			try:
				os.mkdir(self.home)
			except:
				raise DBError, "error creating directories: "+self.home
		self._storeDir = os.path.join(self.home,"search_store")
		
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
				print "Error removing NEEDSREINDEX... check permisions inside %s" % (self.home)
		
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
			if os.path.isfile(os.path.join(self.home,"penguintv3.db")) == False:
				raise DBError,"database file missing"
			db=sqlite.connect(os.path.join(self.home,"penguintv3.db"), timeout=10	)
			db.isolation_level="DEFERRED"
			return db
		except:
			raise DBError, "Error connecting to database in Lucene module"
		
	def Do_Index_Threaded(self, callback):
		PythonThread(target=self.Do_Index, args=(callback,)).start()
		
	def Do_Index(self, callback=None):
		"""loop through all feeds and entries and feed them to the beast"""
		
		def index_interrupt():
			writer.close()
			self._index_lock.release()
			if callback is not None:
				callback()
			self._interrupt()
			return
			
		self._index_lock.acquire()
		db = self._get_db()
		c = db.cursor()
		
		analyzer = StandardAnalyzer()
		store = FSDirectory.getDirectory(self._storeDir, True)
		writer = IndexWriter(store, analyzer, True)
				
		c.execute(u"""SELECT id, title, description FROM feeds""")
		feeds = c.fetchall()
		c.execute(u"""SELECT id, feed_id, title, description,fakedate FROM entries""")
		entries = c.fetchall()
		c.close()
		db.close()
		
		print "indexing feeds"
		for feed_id, title, description in feeds:
			if self._quitting:
				return index_interrupt()
			try:
				doc = Document()
				 
				doc.add(Field("feed_id", str(feed_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))
				doc.add(Field("feed_title", title,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))   
				doc.add(Field("feed_description", description,
	                                           Field.Store.NO,
	                                           Field.Index.TOKENIZED))       
				writer.addDocument(doc)  
			except Exception, e:
				print "Failed in indexDocs:", e      
			sleep(0)   #http://twistedmatrix.com/pipermail/twisted-python/2005-July/011052.html           
		
		print  "indexing entries"
		
		for entry_id, feed_id, title, description, fakedate in entries:
			if self._quitting:
				return index_interrupt()
			try:
				doc = Document()
				p = HTMLDataParser()
				p.feed(description)
				description = p.data
				doc.add(Field("entry_id", str(entry_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))
				doc.add(Field("entry_feed_id", str(feed_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))	                                           
				
				time = DateTools.timeToString(long(fakedate)*1000, DateTools.Resolution.HOUR)
				doc.add(Field("date", time, 
											   Field.Store.YES,
	                                          Field.Index.UN_TOKENIZED))	                                           
	            
				doc.add(Field("entry_title",title,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))   
				doc.add(Field("entry_description", description,
	                                           Field.Store.NO,
	                                           Field.Index.TOKENIZED))       
				writer.addDocument(doc)  
			except Exception, e:
				print "Failed in indexDocs:", e    
			sleep(0)
				
		print "optimizing"
		writer.optimize()
		writer.close()
		print "done indexing"
		self._index_lock.release()
		if callback is not None:
			callback()
		
	def Re_Index_Threaded(self,feedlist=[], entrylist=[]):
		PythonThread(target=self.Re_Index, args=(feedlist,entrylist)).start()
		
	def Re_Index(self, feedlist=[], entrylist=[]):
		if len(feedlist)==0 and len(entrylist)==0:
			return
			
		def reindex_interrupt():
			indexModifier.close()
			self._index_lock.release()
			self._interrupt()
			return
			
		print "reindexing"
		self._index_lock.acquire()
		db = self._get_db()
		c = db.cursor()
					
		analyzer = StandardAnalyzer()
		indexModifier = IndexModifier(self._storeDir, analyzer, False)
		#let it fail
		#except Exception, e:
		#	print "index modifier error (probably lock)",e,type(e)
		#	return
		
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
				#c.execute(u"""SELECT id, title, description, fakedate FROM entries WHERE feed_id=?""",(feed_id,))
				#results = c.fetchall()
				#if results:
				#	for entry_id, title, description, fakedate in results:
				#		entry_addition.append((entry_id, feed_id, title, description, fakedate))
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
				indexModifier.deleteDocuments(Term("feed_id",str(feed_id)))
			except Exception, e:
				print "Failed deleting feed:", e
				
		for entry_id in entrylist:
			try:
				indexModifier.deleteDocuments(Term("entry_id",str(entry_id)))
			except Exception, e:
				print "Failed deleting entry:", e
			
		#now add back the changes
		#print [f[0] for f in feed_addition]
		for feed_id, title, description in feed_addition:
			if self._quitting:
				return reindex_interrupt()
			try:
				doc = Document()
				doc.add(Field("feed_id", str(feed_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))
				doc.add(Field("feed_title",title,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))   
				doc.add(Field("feed_description", description,
	                                           Field.Store.NO,
	                                           Field.Index.TOKENIZED))
				indexModifier.addDocument(doc)
			except Exception, e:
				print "Failed adding feed:", e
		
		#print [(e[0],e[1]) for e in entry_addition]
		for entry_id, feed_id, title, description, fakedate in entry_addition:
			if self._quitting:
				return reindex_interrupt()
			try:
				doc = Document()
				p = HTMLDataParser()
				p.feed(description)
				description = p.data
				doc.add(Field("entry_id", str(entry_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))
				doc.add(Field("entry_feed_id", str(feed_id), 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))	
	                                           
				time = DateTools.timeToString(long(fakedate)*1000, DateTools.Resolution.HOUR)
				doc.add(Field("date", time, 
											   Field.Store.YES,
	                                           Field.Index.UN_TOKENIZED))	
				doc.add(Field("entry_title",title,
	                                           Field.Store.YES,
	                                           Field.Index.TOKENIZED))   
				doc.add(Field("entry_description", description,
	                                           Field.Store.NO,
	                                           Field.Index.TOKENIZED))
				indexModifier.addDocument(doc)
			except Exception, e:
				print "Failed adding entry:", e
				
		indexModifier.flush()
		indexModifier.close()
		self._index_lock.release()
		print "reindex done"
						
	def Search(self, command, blacklist=[], include=['feeds','entries'], since=0):
		"""returns two lists, one of search results in feeds, and one for results in entries.  It
		is sorted so that title results are first, description results are second"""
		
		if not self._index_lock.acquire(False):
			#if we are indexing, don't try to search
			#print "wouldn't get lock"
			return ([],[])
		self._index_lock.release()
		
		analyzer = StandardAnalyzer()
		directory = FSDirectory.getDirectory(self._storeDir, False)
		searcher = IndexSearcher(directory)
		sort = Sort("date", True) #sort by fake date, reversed
		
		feed_results=[]
		entry_results=[]
		
		#MultiFindQuery has a bug in 2.0.0... for now don't use
		#queryparser = MultiFieldQueryParser(['title','description'], self.analyzer)
		#query = MultiFiendQueryParser.parse(command, ['title','description'], self.analyzer)

		def build_results(hits):
			"""we use this four times, so save some typing"""
			for i, doc in hits:
				feed_id  = doc.get("feed_id")
				if feed_id is None:
					feed_id  = doc.get("entry_feed_id")
				feed_id = int(feed_id)
				try:
					if feed_id not in blacklist:
						entry_id = doc.get("entry_id")
						if entry_id is None: #meaning this is actually a feed (we could know that from above, but eh)
							feed_results.append(int(feed_id))
						else: #               meaning "entry"
							if len(entry_results) < ENTRY_LIMIT:
								title    = doc.get("entry_title")
								fakedate = DateTools.stringToTime(doc.get("date")) / 1000.0
								if fakedate > since:
									entry_results.append((int(entry_id),title, fakedate, feed_id))
					#else:
					#	print "excluding:"+doc.get("title")
				except Exception, e:
					print e
					print feed_id
					print blacklist

		#query FEED TITLES
		if 'feeds' in include:
			queryparser = QueryParser("feed_title", analyzer)
			query = QueryParser.parse(queryparser, command)
			hits = searcher.search(query)
			build_results(hits)
				
			#query FEED DESCRIPTIONS		
			queryparser = QueryParser("feed_description", analyzer)
			query = QueryParser.parse(queryparser, command)
			hits = searcher.search(query)
			build_results(hits)
		
		if 'entries' in include:
			#ENTRY TITLES
			queryparser = QueryParser("entry_title", analyzer)
			query = QueryParser.parse(queryparser, command)
			hits = searcher.search(query, sort)
			build_results(hits)
				
			#ENTRY DESCRIPTIONS		
			queryparser = QueryParser("entry_description", analyzer)
			query = QueryParser.parse(queryparser, command)
			hits = searcher.search(query, sort)
			build_results(hits)
			
		for entry in entry_results:
			feed_results.append(entry[3])
			
		feed_results = utils.uniquer(feed_results)
		entry_results = utils.uniquer(entry_results)	
		#need to resort because we merged two lists together
		entry_results.sort(lambda x,y: int(y[2] - x[2]))
		searcher.close()    
		#for e in entry_results:
		#	print e[2],e[1]
		return (feed_results, entry_results)
		
	def get_popular_terms(self, max_terms=100, junkWords=[], fields=[]):
		#ported from http://www.getopt.org/luke/ HighFreqTerms.java
		self._index_lock.acquire()
		def insert(l, val):
			#for item in l:
			#	
			#try:
			#	print val[0]
			#	print l.index(val
			#	l[l.index(val[0])]=(val[0], l[l.index(val[0])][1]+val[1])
			#	print "updating",l[l.index(val[0])]
			#except:
			#	pass
			insert_at = -1
			i=-1
			for item in l:
				i+=1
				if item[0] == val[0]:
					l[i] = (item[0], item[1]+val[1])
					return
				if val[1]>item[1] and insert_at==-1:
					insert_at = i
			if insert_at >= 0:	
				l.insert(insert_at, val)
			else:
				l.append(val)
			
		
		reader = IndexReader.open(self._storeDir)
		terms = reader.terms()
		pop_terms = {}
		#minFreq = 0
		seen=[]
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
			text = term.text()
			#if text in seen:
			#	print "exists"
			#	i = seen.index(text)
			#	pop_terms[i][1] = pop_terms[i][1] + terms.docFreq()
			#else:
			if not pop_terms.has_key(field):
				pop_terms[field]=[]
			pop_terms[field].append((text, terms.docFreq()))
			#	seen.append(term.text())
			#if terms.docFreq() > minFreq:
			#	insert(pop_terms, (term.text(), terms.docFreq()))
			#	if max_terms>0 and len(pop_terms) >= max_terms:
			#		pop_terms.pop(-1)
			#		minFreq = pop_terms[-1][1]
			
		def merge(l1, l2):
			if len(l1)>len(l2):
				l3 = l1
				l2 = l1
				l1 = l3
				del l3
			i=-1
			for term,freq in l1:
				i+=1
				while term < l2[i][0] and i<len(l2):
					i+=1
				if i >= len(l2):
					l2.append((term,freq))
					break
				if term == l2[i]:
					l2[i] = (l2[i][0], l2[i][1] + freq)
				if term > l2[i]:
					l2.insert(i,(term,freq))
			
		field_rank = []
		for key in pop_terms.keys():
			field_rank.append((len(pop_terms[key]), key))
		field_rank.sort()
		field_rank.reverse()
		for rank,key in field_rank[1:]:
			pop_terms[field_rank[0][1]] = self.merge(pop_terms[field_rank[0][1]],pop_terms[key])
			#j=-1
			#for term in pop_terms[field_rank[0][1]]:
			#	j+=1
			#	if term in pop_terms[key]:					
			#		pop_terms[field_rank[0][1]][j] = (term, pop_terms[field_rank[0][1]][j][1] + pop_terms[key][pop_terms[key].index(term)][1])
		pop_terms=pop_terms[field_rank[0][1]]
		#pop_terms.sort(lambda x,y: y[1]-x[1])
		if max_terms>0:
			pop_terms = pop_terms[:max_terms]
		self._index_lock.release()
		return pop_terms

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


