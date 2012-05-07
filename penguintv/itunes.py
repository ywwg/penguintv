# itunes.py
# Written by Owen Williams, (c) 2007
# see LICENSE for license information
#
# iTunes has very strange weblinks, but they are not that hard to read.
# A "viewPodcast" link returns a gzipped web page that contains a link that
# iTunes can load.  Although the protocol of this link is itms://, we can
# load it with http.  This time we get a gzipped xml file, and toward the
# bottom of the file is a simple key / value pair for episodeURL.  This
# url is what the podcast author has told itunes to use, and it'll be regular
# RSS (we hope).


import sys
import gzip
import urllib
import logging

class iTunesURLopener(urllib.FancyURLopener):
    version = "iTunes/9.1.1"
    
def get_itunes_podcast_id(url):
    p_id = ""
    started_numbers = False
    for c in url[url.find("id"):]:
        if c in ("01234568790"):
            started_numbers = True
            p_id += c
        elif started_numbers:
            break
            
    return p_id

def is_itunes_url(url):
    """ Two simple checks to see if this is a valid itunes url:
        (ie, http://phobos.apple.com/WebObjects/MZStore.woa/wa/viewPodcast?id=207870198)
        * does it contain "phobos.apple.com", and
        * does it contain "viewPodcast" 
        
        There's also another form, as in http://www.itunes.com/podcast?id=207870198"""
    
    if url.lower().startswith("itms://"):
        return True    
    if "apple.com/" in url.lower() and "podcast" in url.lower():
        return True
    if "itunes.com/podcast" in url.lower():
        return True
    return False

def get_rss_from_itunes(url):
    url.replace("itms:","http:")
    
    if not is_itunes_url(url):
        raise ItunesError, "not an itunes url"
        
    p_id = get_itunes_podcast_id(url)
        
    return get_podcast_url(p_id)
        
def get_podcast_url(p_id):
    old_opener = urllib._urlopener
    urllib._urlopener = iTunesURLopener()
    
    # Part 2, find the actual rss link in the itunes "webpage"
    itunes_page = urllib.urlopen("http://itunes.apple.com/podcast/id"+p_id)
    urllib._urlopener = old_opener #this probably isn't necessary
    
    rss_url = None
    try:
        for line in itunes_page.readlines():
            if "feed-url" in line:
                rss_url = line[line.find("feed-url"):].split("\"")[1]
                break
    except Exception, e:
        raise ItunesError, "Problem parsing itunes page for podcast url"                
            
    if rss_url is None:
        raise ItunesError, "error finding podcast url"
        
    return rss_url

class ItunesError(Exception):
    def __init__(self, m):
        self.m = m
    def __str__(self):
        return self.m



