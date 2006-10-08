#!/usr/bin/env python

# example helloworld.py

import pygtk
pygtk.require('2.0')
import gtk
import gtkmozembed
import gobject
import os

import gtk.glade

class HelloWorld:

    # This is a callback function. The data arguments are ignored
    # in this example. More on callbacks below.
    def hello(self, widget, data=None):
        print "Hello World"

    def delete_event(self, widget, event, data=None):
        # If you return FALSE in the "delete_event" signal handler,
        # GTK will emit the "destroy" signal. Returning TRUE means
        # you don't want the window to be destroyed.
        # This is useful for popping up 'are you sure you want to quit?'
        # type dialogs.
        print "delete event occurred"

        # Change FALSE to TRUE and the main window will not be destroyed
        # with a "delete_event".
        return False

    def destroy(self, widget, data=None):
        print "destroy signal occurred"
        gtk.main_quit()

    def __init__(self):
        # create a new window
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
    
        # When the window is given the "delete_event" signal (this is given
        # by the window manager, usually by the "close" option, or on the
        # titlebar), we ask it to call the delete_event () function
        # as defined above. The data passed to the callback
        # function is NULL and is ignored in the callback function.
        self.window.connect("delete_event", self.delete_event)
    
        # Here we connect the "destroy" event to a signal handler.  
        # This event occurs when we call gtk_widget_destroy() on the window,
        # or if we return FALSE in the "delete_event" callback.
        self.window.connect("destroy", self.destroy)
    
        # Sets the border width of the window.
        self.window.set_border_width(10)
    
        # Creates a new button with the label "Hello World".
        self.button = gtk.Button("Hello World")
    
        # When the button receives the "clicked" signal, it will call the
        # function hello() passing it None as its argument.  The hello()
        # function is defined above.
        self.button.connect("clicked", self.hello, None)
    
        # This will cause the window to be destroyed by calling
        # gtk_widget_destroy(window) when "clicked".  Again, the destroy
        # signal could come from here, or the window manager.
        self.button.connect_object("clicked", gtk.Widget.destroy, self.window)
    
        # This packs the button into the window (a GTK container).
        #self.window.add(self.button)
    
        # The final step is to display this newly created widget.
        #self.button.show()
        self.first = False    
        gtkmozembed.set_profile_path(os.path.join(os.getenv('HOME'),".penguintv"), 'gecko')
        self._embed = gtkmozembed.MozEmbed()
        #self._embed.connect("title", self.__title_cb)
        #self._embed.connect("open-uri", self.__open_uri)
        self.window.add(self._embed)		
        self._embed.show()
        self._embed.load_url('http://www.google.com')
        
        
    
    
        # and the window
        self.window.show()
        self.window.resize(200,200)
        #self.count = 0
        #self.go_glade()
        gobject.timeout_add(1000, self.go)
        
    def go(self):
    	
    	html = """<html><head>
            <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
                        <style type="text/css">
            body { background-color: #ffffff;; color: #000000;; font-family: 'Arial','Arial 12',Arial; font-size: 16; }
            dd { 
        padding-left: 20pt; 
}  

q { font-style: italic;}

.heading { 
        background-color: #f0f0ff; 
        border-width:1px; 
        border-style: solid; 
        padding:12pt; 
        margin:12pt; 
}

blockquote { 
        display: block; 
        color: #444444; 
        background-color:#EEEEFF; 
        border-color:#DDDDDD; 
        border-width:2px; 
        border-style: solid; 
        padding:12pt; 
        margin:12pt;
}

.stitle {
        font-size:14pt; 
        font-weight:bold; 
        font-family: 'Lucida Grande', Verdana, Arial, Sans-Serif; 
        padding-bottom:20pt;
}

.sdate {
        font-size:8pt; 
        color: #777777
}

.content {
        padding-left:20pt;
        margin-top:12pt;
}

.media {
        background-color:#EEEEEE; 
        border-color:#000000; 
        border-width:2px; 
        border-style: solid; 
        padding:8pt; 
        margin:8pt; 
}

            </style>
            <title>title</title></head><body><span id="errorMsg"></span><br><table
                                        style="width: 100%; text-align: left; margin-left: auto; margin-right: auto;"
                                        border="0" cellpadding="2" cellspacing="0">
                                        <tbody>
                                        <tr><td><a href="planet:up">Newer Entries</a></td><td style="text-align: right;"><a href="planet:down">Older Entries</a></td></tr></tbody></table><div align="center">
                                        
                                        
                                        
                                        <h1>Henry Jenkins</h1>
                                        
                                        
                                        
                                        
                                        
                                       <div class="stitle">What DOPA Means for Education</div>By Henry Jenkins<br/><div class="sdate">Wed Aug 16, 2006 03:45:28 AM</div><br/><div class="content"><br/><p>A little while ago, I got the following comments in an e-mail from one of the Comparative Media Studies graduate students Ravi Purushotma about the news that the Deleting Online Predators Act has now passed the U.S. House of Representatives:</p>

<blockquote>Some of my friends commented on how bitter, angry and depressed I seemed when DOPA passed. It's really painful spending 5 years searching for a new paradigm by which this planet could communicate among itself, coming to an actual sense of what needs to happen, then the week before it culminates into a thesis it becomes illegal because some bonehead in Alaska has his neural tubes clogged.</blockquote>

<p>For those of you who have not been following this story, there's some very <a href="http://www.technologyreview.com/read_article.aspx?id=17266&ch=infotech">good reporting </a>by Wade Rough of <em>Technology Review</em> about the debate surrounding DOPA. The Senator from Alaska is question is Senator Ted Stevens who has been a major backer of this legislation and who seems to know very little about how digital media works.</p>

<p>This exchange came as I was signing off on Purushotma's outstanding thesis which centers on the ways that various forms of new media and popular culture could be used to enhance foreign language teaching and learning. His project got some attention a year or so back when the <a href="http://news.bbc.co.uk/1/hi/technology/4182023.stm">BBC</a> picked up on a report he had done describing his efforts to modify <em>The Sims </em>to support the teaching of foreign languages. Essentially, the commercial games ship with all of the relevant language tracks on the disc and a simply code determines which language is displayed as they reach a particular national market.  It is a pretty trivial matter to unlock the code for a different language and play the game in Spanish, German, or what have you. The game's content closely resembles the focus on domestic life found in most first or second year language textbooks -- with one exception. Most of us are apt to put in more time playing the game than we are to spending studying our textbooks or filling in our workbooks.</p>

<p>This is a very rich and interesting approach but it is only one of a number of ideas that Ravi proposes in his thesis. Ravi has done more research than anyone I know about into how teachers are using this technology now and what purposes it might serve in the future. He has prepared his thesis as a <a href="http://www.lingualgamers.com/thesis">multimedia web document</a> that mixes sound, video, and text in ways that really puts his ideas into practice. </p>

<p>There has been lots of <a href="http://www.danah.org/papers/MySpaceDOPA.html">discussion </a>here and elsewhere about the potentially devastating effect of DOPA on the lives of young people -- especially those for whom schools and public libraries represent their only point of access onto the digital world. I have made the argument that if supporters of DOPA really wanted to protect young people from online predators, they would teach social networking in the classroom, modeling safe and responsible practices, rather than lock it outside the school and thus beyond the supervision of informed librarians and caring teachers.  The advocates of the law have implied that MySpace is at best a distraction from legitimate research activities, at worst a threat to childhood innocence.</p>

<p>But Ravi's thesis suggests something more -- we are closing off powerful technologies that could be used effectively to engage young people with authentic materials and real world cultural processes.  Here, social networking functions not as a media literacy skill but as a tool for engaging with traditional school subjects in a fresh new way.</p> </div><br/><a href="http://www.henryjenkins.org/2006/08/what_dopa_means_for_education_1.html">Full Entry...</a><br /></p><hr>
<div class="stitle">Response to Bogost (Part Three)</div>By Henry Jenkins<br/><div class="sdate">Tue Aug 15, 2006 03:38:18 AM</div><br/><div class="content"><br/><p><em>When Ian Bogost wrote me earlier today to say that his response to the first installment hadn't appeared on my site, I was confused. I went back to my spam filter and discovered that more than 30 substantive comments to this site from a variety of sources had gone missing. I had been trying to be as inclusive as possible and make sure all of the reader's comments were posted, cutting out only obvious spam and purely personal invective. I feel really bad to discover so many of you fell prey to the spam catcher. Now that I know it is an issue, I will be checking regularly. I have now reposted everything that got blocked -- for archival purposes if nothing else. Sorry for the mixup. All I can say is that I am new at this.</em></p>

<p>Over the past two installments, I have been responding to Ian Bogost's thoughtful yet challenging <a href="http://www.watercoolergames.org/archives/000590.shtml">review</a> of my new book, <em>Convergence Culture: Where Old and New Media Collide</em>, over at Water Cooler Games. In <a href="http://www.henryjenkins.org/2006/08/hmm_buttery_a_response_to_ian.html#more">part one</a>, I addressed some issues surrounding the emotional dynamics of contemporary advertising. <a href="http://www.henryjenkins.org/2006/08/response_to_bogost_part_two.html#more">Last time,</a> I addressed some questions around transmedia entertainment and fan culture. Today, I will wrap up with some thoughts on the commercialization of culture and the relationship between technology and culture, among other topics.</p>

<p>For those who might be interested in hearing me speak more about the ways convergence culture is impacting the games industry, check out my appearance on a <a href="http://www.escapistmagazine.com/radio/view/63962">podcast</a> organized by the editors of The Escapist.</p>

<p><br />
<em>Noncommercial Media</em></p>

<blockquote>Tthe omission of convergence communities that opt for more historically-entrenched creative practices in lieu of outright commercial commodities seems to reflect Jenkins's own preference for contemporary popular culture, and perhaps his own libertarian politics. The subversive undertones in <em>Convergence Culture</em> remain squarely on the side of mass market global capitalism. While Jenkins admits that many corporations are pushing convergence as a strategy of control, he frames consumer resistance as a struggle to get media companies to be more responsive to consumer tastes and interests.</blockquote>

<p>Hmm. Where do I start? I see my book as describing a particular aspect of contemporary culture which has to do with the intersection between commercial and grassroots media. I am very clear from the start that no one can describe the full picture and that all I can offer are a limited number of snapshots of cultural change in practice. There is much about the culture which this book doesn't address, though I would hope that its insights help others to begin to explore these implications for their respected areas. I know that <a href="http://deuze.blogspot.com/">Mark Deuze</a>, for example, has been applying some of these ideas to the study of news and journalism; I have myself done some writing lately about the implications of participatory culture for education and for participation in the arts; and so forth. I would have said that the book tries to show how trends in popular culture are relevent to the political process, to education, to religion, and to the military at various points along the way, which is more than what most books on popular entertainment have tried to do.</p>

<p>My own particular background as a scholar -- and my own particular interest as a fan -- lies in the area of popular culture. It doesn't mean I don't see value in other forms of cultural production. I do. But there are plenty of others in the academia who know those areas better, write about them more knowledgibly, and make better contributions to them. I find myself drawn to popular culture in part because it requires me to defend what some see as the indefensible and in the process, to try to complicate the easy hierarchies that too often operate within our culture.</p>

<p>Some of what my book doesn't discuss  is addressed very well by Yochai Benkler's <em>Wealth of Networks</em>, a book that I really wish I could have read while I was writing my own book. He's making an argument that we need to discuss the present moment in terms of the shifting relationship between commercial, amateur, civic, and nonprofit sectors, each involved in the production and circulation of media, and each meeting each other on somewhat different terms because of the leveling influence of the web.  Man, I wish I had said that. My book really focuses on the two extremes there -- the commercial on the one hand and the amateur on the other.  I do think it could have said more about these other players in the middle -- various nonprofit groups, educational and cultural institutions, etc. and the role they play in reshaping the media landscape. </p> </div><br/><a href="http://www.henryjenkins.org/2006/08/response_to_bogost_part_three.html">Full Entry...</a><br /></p><hr>
<div class="stitle">Response to Bogost (Part Two)</div>By Henry Jenkins<br/><div class="sdate">Mon Aug 14, 2006 06:44:10 PM</div><br/><div class="content"><br/><p>On Friday, I began <a href="http://www.henryjenkins.org/2006/11/hmm_buttery_a_response_to_ian.html#more">the first </a>of a three part response to Ian Bogost's thoughtful, engaging, and provocative review of my new book, <em>Convergence Culture: Where Old and New Media Collide</em>. Bogost's <a href="http://www.watercoolergames.org/archives/000590.shtml">discussion </a>of the book at Water Cooler Games allows me to respond to some anticipated challenges to the book's content and approach.  It also seems that many of you are relishing a good debate in the dog days of the summer so far be it for me to deny you your entertainment. All of this will make more sense if you've read both the book and the review. </p>

<p>Last time, I mostly addressed some questions Bogost raised about the affective economics chapter of the book. Today, I take up some issues about transmedia storytelling/entertainment and about fan culture more generally. </p>

<p>Keep in mind two things: Bogost's review was primarily positive and I have enormous respect for Bogost's contribution to the game studies world. This is an intellectual debate, not a blood feud. </p>

<p><u><br />
Ludology vs. Narratology<br />
</u><br />
<blockquote>As the sonic boom of the so-called ludology vs. narratology debate dissipates, I find it interesting that Jenkins continues to insist on the terms "narrative" and "storytelling" as the principle units of cultural expression. Even though Jenkins admits that "storytelling has become the art of world building," where artists create environments and situations for a multitude of consumer intersections, he still does not reimagine such a craft separate from the particularity of narrative. Following Roger Shanck and others, Jenkins argues that "stories are basic to all human cultures, the primary means by which we structure, share, and make sense of our common experiences." Yet, the examples he cites, from the rich worlds of <em>The Matrix</em>, and <em>Star Wars</em> to transmedial experiments like Dawson's Desktop, readily elude the narrative frame, offering representations of behaviors, fragments, and environments. Michael Mateas and Gonzalo Frasca have called the privileging of narrative expression narrativism, and I have argued that narrativist gestures like Jenkins's occlude representational gestures based on logics and behaviors. <em>Convergence Culture </em>continues Jenkins' narrativist practice.</blockquote><br />
<blockquote><br />
Given the propensity for such non-narrative interpretations of media properties, it is curious that Jenkins did not choose the more general term transmedia authorship over transmedia storytelling</blockquote></p>

<p><br />
My first response upon reading this was to gasp, "not again." The last thing any of us wants is to reopen the trumped up feud between the self-proclaimed ludologists and the so-called narratologists. The argument is, in my opinion, based on a false set of distinctions that are getting imposed on a hybrid medium at a highly transitional moment. (Anytime someone accuses you of "occluding" something, you know you are in trouble.)  More seriously, I think the ludology/narratology debate was based on misidentifications across cultural and language differences. When Espen Aarseth and I sat down together a few years ago at the HumLab, we found that there was relatively little to debate. We were involved in disagreements in emphasis but not in a substantive dispute about the future of game studies.</p> </div><br/><a href="http://www.henryjenkins.org/2006/08/response_to_bogost_part_two.html">Full Entry...</a><br /></p><hr>
<div class="stitle">A Response to Ian Bogost (Part One)</div>By Henry Jenkins<br/><div class="sdate">Mon Aug 14, 2006 03:04:10 AM</div><br/><div class="content"><br/><p>Ian Bogost wins the award for being first to market with a thorough, thoughtful <a href="http://www.watercoolergames.org/archives/000590.shtml">critique </a>of my new book, <em>Convergence Culture: Where Old and New Media Collide</em>. </p>

<p>The review is worth reading in its entirity because it really does set a high bar for debate and discussion around this book. Bogost does all of us a great service in taking on this task: the review is helpful to me in identifying some of the battlegrounds that are apt to emerge around this book. As I wrote to him, there are some points of real disagreement here, some points where we place different emphasis, and some points where we agree more than his summary of the book suggests. Some of his criticisms made me wince; some left me scratching my head. I wish I had read some of them before the book went to press.</p>

<p>It seems the most constructive thing one can do at this point is to respond to some of his questions publically in the hopes of getting a larger conversation going around the issues he raises.  Because I wanted to respond fully to a range of interesting questions Bogost raised, I am going to be running my response over my next three posts.</p>

<p><br />
<u>I Can't Belive It's Margarine!</u></p>

<p>Bogost's review begins promisingly enough from my perspective with the following lines:</p>

<blockquote>The book is a short, smart, buttery read on a hot topic, and it is sure to draw both popular and academic interest.</blockquote>

<p>I cite this passage here -- other than my amusement over the buttery metaphor -- just to show that he really does seem to like the book. (Bless you, Ian, for calling the book "short." It has to be the first time in human history I haven't been accused of being long winded.) Hinceforth, I am going to generally ignore the many nice things he says about the book in order to address points of disagreement. I am not trying to pick a fight with Bogost, who I admire, simply trying to respond to the issues that seem most urgent here and I have told Bogost I am planning to do this. My hope is that I can coax him to respond to my response and keep the exchange going.</p> </div><br/><a href="http://www.henryjenkins.org/2006/08/hmm_buttery_a_response_to_ian.html">Full Entry...</a><br /></p><hr>
<div class="stitle">E3: End of an Era?</div>By Henry Jenkins<br/><div class="sdate">Thu Aug 10, 2006 08:04:43 AM</div><br/><div class="content"><br/><p>Those of us who follow the games industry have reacted with various degrees of shock and surprise by the <a href="http://www.next-gen.biz/index.php?option=com_content&task=view&id=3538&Itemid=2">announcement </a>a few weeks ago that E3, the Electronic Entertainment Expo, the major trade show of the games industry, will no longer be held.  As <em>Next Generation</em> has reported, several of the major companies whose support was key for funding an event on this scale had pulled their support from the event: </p>

<blockquote>When I spoke to some people about E3's collapse, the general response was one of disbelief. How could something so big fall apart so quickly? Perhaps this is why so many news outlets simply refused to believe the news. The fact is that all it took were a very small number of company presidents to talk with each other, and figure out that if they all decided to pass, none of them would need to be there. Once Nintendo, Microsoft, SCEA and EA had stepped out, E3 was history. It was multilateral disarmament.</blockquote>

<p>The <em>Next Generation</em> <a href="http://www.next-gen.biz/index.php?option=com_content&task=view&id=3548&Itemid=2">writer</a> went on to identify a range of other factors that contributed to the collapse of this industry institution, including a sense that it had not achieved its goals in attracting media coverage to anything other than the violence issue or the release of new hardware as well as the degree to which other and better publicity mechanisms had emerged which made it possible for companies to maintain greater control over their messages and reach their intended audience at lower costs. The Next Generation coverage stressed the degree to which organizing for E3 had taken on a life of its own, often at the expense of other goals within the industry:</p>

<blockquote>E3 isn't just measured in terms of the cost of the booth, the floor-space, the party, the hotel, the flights etc. There's also the incredible amount of effort that goes into preparing for the show. Marketing teams are focused on E3 for a good six months of the year. Developers are whipped along as they try to get games ready for what is, essentially, an artificial deadline. It could be argued that this adds focus to development as projects near their conclusion, or it could be argued that it's an unnecessary diversion and a big pain in the ass. Publishers that focus on company-specific events are not under so much pressure to compete with the rest of the market for column inches, months before the real battle of competing for consumer dollars.</blockquote>
        <p>In a <a href="http://www.next-gen.biz/index.php?option=com_content&task=view&id=3546&Itemid=2">public statement</a>, Doug Lowenstein, the head of the Entertainment Software Association, explained:</p>

<blockquote>E3Expo 2007 will not feature the large trade show environment of previous years. It is no longer necessary or efficient to have a single industry 'mega-show.' By refocusing on a highly-targeted event, we think we can do a better job serving our members and the industry as a whole, and our members are energized about creating this new E3.</blockquote>
<u>
They Cancelled What?</u>

<p>Something of the shock waves this announcement has sent through the games sector is suggested by this pithy comment from <a href="http://www.penny-arcade.com/2006/07/31">Tycho</a> over at <em>Penny Arcade</em>:<br />
<blockquote><br />
There must have been a time before there was an E3, but that's not really a part of my experience. Hearing that it's cancelled, or at any rate will be altered in "format and scale" (read: cancelled) is like hearing that Australia has been cancelled, or that the weak gravitational force is being temporarily suspended.</blockquote></p>

<p>Some have wondered how a thriving entertainment industry might survive without a high profile trade show. E3 is most often compared to ShowWest which is the place where film exhibitors learn about the new releases for the year or Comicon, which as we have been reporting, functions as the interface between the comics industry and its fans. But already to draw those comparisons in such terms suggests the difference between E3 and these other events. E3 was trying to be too many things for too many people -- a showcase for major publisher's releases, a marketplace for products hoping for distribution and for international games hoping to find a way into the American market, a press event to showcase the industry, a training ground and recruitment ground for future professionals. Other groups have started to use E3 as a base for their own work: we did two Education Arcade conferences in the LA Convention Center during E3 trying to build interest in games and education and UCLA piggybacked off E3 this year for its conference on gender and games. The one function E3 did not play was to provide an interface between the games industry and its fans. </p>

<p>There was always a tension, though, between the lavish spectacle and parties required to woo reps from the major retail outlets and the more sober face that the industry wanted to adopt for talking to the press (and through them, to the general public). In many ways, the collapse of E3 signals the growth of the games industry -- as something larger within our culture -- rather than its diminishment. </p>

<p><u><br />
Why E3 Hurt Games</u><br />
Some of you know that Kurt Squire and I co-author the "Applied Game Theory" column at Computer Games Magazine every month. Several years ago, we penned one describing why we thought that at least aspects of E3 culture might be bad for the games industry. I don't want to see reposting this text here now as piling onto Lowenstein and my other friends at the ESA. They do great work on behalf of the games industry and they don't get enough credit. I am sure that they are experiencing the end of E3 with profoundly mixed feelings.  But I did think what we said then would help shed some light on the current issues and might help us think through together what the next incarnation of a games industry gathering might look like. (The specific titles referenced here will have dated but otherwise this would still have described the 2006 event.)</p>

<p><br />
<blockquote>Perhaps you are at the convention now, reading this column over the thundering noise and flashing lights which turn that same showroom into something akin to the streets of Hong Kong at midnight. Scantly-clad floor babes beckon to you with promises of easy access and cheap loot. Dancers in leotards demonstrate the wonders of motion capture technology. Highly skilled game girls are challenging all comers. The noise you are hearing is the sound of a thousand computer games all being played at the same time. Most people stagger out after only a few minutes, so overwhelmed that they can no longer focus on any one screen. We've seen people  passed out in the corner, their friends trying to coax them back to consciousness by upping their caffeine intake. Everyone should see E3 once to experience the adrenaline rush.</p>

<p>E3's economic function is well understood by anyone who has spent more than a few minutes thinking about the games industry. This is where buyers from Wal-Mart, Electronic Boutique, and the other chain stores first encounter the coming year's product. The major game companies are hyping their hottest new titles, smaller companies are trying to break into the market. Both are involved in a life and death struggle for the attention of the middlemen who<br />
will determine how much shelf space a title will get and how long it remains there. In E3 2001 for example, the disappointing Xbox showing sent the Microsoft  PR machine scrambling for months to convince retailers that<br />
platform was ready to ship.</p>

<p>Yet, the consequences of E3 on the look and feel of contemporary games have been less often discussed. For starters, many game designers talk about the importance of designing memorable moments into their new releases -- features which leave vivid impressions after the bulk of what we saw on the floor has blurred together in our sleep-deprived, alcohol-addled, and sensorial-overloaded minds. Producers push designers to come up with a preview reel which grabs attention on the huge monitors which dot the display room and often, the result is an over-emphasis on cinematics over game play. The disparity between those massive screens, which would not seem out of place at your average multiplex, and the much smaller monitors on which most of us play games tells us why so many games look like bad action movies rather than exploring the interactive potentials of this medium or why game soundtracks so often emphasize noisy explosions rather than emotionally enhancing music. What would happen if every movie to be release next year got shown all at the same time in the same auditorium? Which films would stand out? Which films would get buried? For those of us who want to promote greater innovation and diversity in game design, the E3 floor may be the biggest obstacle in our path.</p>

<p>Smaller scale games get little or no floor space. The Sims, for example, got swallowed up by the chaos of the E3 showroom. Games like Rez or Majestic which really stretch the limits of our understanding of what the medium can do are more often displayed in private rooms off the main floor. Some of the most interesting games are literally relegated to the basement, the Kentia Hall, where foreign and independent game developers fight over the cheap space with discount distributors and peripheral manufacturers. You might find an interesting title squeezed between the new video game glove and an online Korean dating game, but these quirky titles have little chance at being heard above the marketing din upstairs.</p>

<p>After even a few minutes on the floor, all of the games start to look the same. Is it any wonder that distributors and retailers are drawn towards recognizable franchises in such an hyperbolic environment? </p>

<p>Is it any surprise that retailers make decisions based on eye candy and glitz?</p>

<p>There's nothing wrong with the industry throwing itself a party at an E3. Wouldn't it be great, though, if like film and music, we had other outlets as well: independent gatherings, grassroots festivals, a real awards show.</p>

<p>As the games industry matures, it may not be able to contain all of its economic and social functions within one or two gatherings. The Indie Games Jam at the Game Developer's Conference is one approach, we hope that other similar efforts will emerge in the upcoming years as well. Consider, by comparison, how important the Sundance Film Festival has been for creating visibility and providing economic opportunities for independent filmmakers.</blockquote></p>

<p><u>Where Do We Go From Here?</u></p>

<p>One step is to separate out the various functions which E3 served and see whether they should be combined or remain separate.  Clearly, the industry will need some ways to introduce its new products to retailers and there's some danger that the next step will be to fragment this process -- allowing the major companies to have their own shows (as <em>Next Generation</em> suggests) but leaving the smaller publishers out in the cold. I don't think that would be a very good thing for the games industry.  A second key function would be to inform the public about the current state of the games industry.  For example, the Penny Arcade Expo may function more like San Diego Comiccon in providing a space where industry figures communicate more directly with their fans, while there are moves underway to develop an independent games festival that functions more like Sundance does within the film industry, offering a place to showcase work by smaller publishers or games that fall further outside the commercial mainstream. We are seeing a growing number of gatherings with more specialized focuses, such as those centering on casual games, mobile games, serious games, even religious games, each of which serves a specific niche as compared to the general interest focus of E3. The Game Developers Conference may absorb more of the training and recruitment functions that were associated with E3. And so forth. </p>

<p>Here's the paradoxl: E3 was bad because the major developers dominated and they overwhelmed smaller producers, contributing to the loss of diversity within the games industry. But when E3 goes away, smaller publishers will have to struggle that much harder to get the attention of the marketplace and they may be the ones who have the most to lose during the transitions that are ahead.</p> </div><br/><a href="http://www.henryjenkins.org/2006/08/why_ending_e3_benefits_the_gam.html">Full Entry...</a><br /></p><hr>
<div class="stitle">ComicCon &amp; The Power of the Devoted Niche</div>By Henry Jenkins<br/><div class="sdate">Wed Aug 09, 2006 02:27:04 AM</div><br/><div class="content"><br/><p>This is the third guest post written by Comparative Media Studies graduate student and media analyst Ivan Askwith about his observations at Comicon. Askwith is beginning work now on a thesis which centers around transmedia and participatory aspects of <em>Lost</em> and <em>Veronica Mars</em>.</p>

<p>In my second dispatch from ComicCon, I tried to illustrate how the studios and networks are already beginning to understand the importance of fan support in the era of convergence culture.  And while some executives have a better grasp on the core principles than others, it's fair to say that the entertainment industry are starting to think more seriously about  how fans power new business models.</p>

<p>Savvy executives, however, will also realize that ComicCon still has a lot to teach them about the significance of fan support, particularly in economic terms. </p>

<p>While recent entries both here and in the <a href="http://www.convergenceculture.org/weblog">C3 Weblog</a> tempt me to describe what I saw at ComicCon as a living illustration of Chris Anderson's Long Tail.  After all, the merchandise selections available at ComicCon range from the super-mainstream to the ultra-obscure, which suggests that there is a market for even the most esoteric and specialized collectibles. If the exhibitors at the Con have chosen to use some of their floor space to offer less mainstream product, should we assume that they've embraced the "we can sell less-of-more" ideology?  Most of these sellers have been attending the Con for years, which gives me ample reason to believe that if they didn't think they could sell off their more obscure inventory, they wouldn't bother bringing it.</p>

<p>For all of its strengths, however, I don't think the Long Tail is designed to explain the lesson that I would encourage the entertainment industry to take away from their time at ComicCon: that a small audience of super-committed fans can be worth more, in economic terms, than a massive audience of casual viewers and readers.  </p>

<p>This isn't an entirely new observation, of course.   Recent literature suggests that viewer involvement has a direct correlation to awareness and retention of advertising messages, and more networks are starting to see the merit of offering niche product through on-demand services.</p>

<p>At ComicCon, however, there is ample evidence to suggest that the industry still hasn't realized just how valuable these niche audiences can be.  This became particularly clear during a brief conversation that I had with Allan Caplan, the founder of <a href="http://www.inkworkscards.com">InkWorks</a>, a company specializing in the creation of trading cards and collectibles tied to popular cult television programs.  Their current lineup includes <em>Lost, Veronica Mars, The 4400,</em> and <em>Naruto</em>, as well as such discontinued shows as<em> Buffy: The Vampire Slayer, Charmed, Firefly, Alias </em>and <em>The X-Files</em>.  InkWorks might not be operating on Anderson's Long Tail, but they benefit from a similar principle: that small audiences still have big purchasing power if you cater to their interests.  </p>

<p>Case in point: InkWorks is preparing to release their seventh line of collectible cards for <em>Buffy The Vampire Slayer</em>, a show that has ended three years ago.  One visitor, walking past the stand, asked: "How could there possibly still be a market for new content about a cancelled series?" </p>

<p>(In retrospect, this is an especially odd question to ask in a room where fans are ready and willing to pay well in excess of $1000 for an original out-of-print comic featuring their favorite character.)</p>

<p>Caplan's answer?  That every line of <em>Buffy</em> cards InkWorks makes has sold out rapidly, and fans continue to ask them for more.  The same is true of other cancelled series, especially Joss Whedon's post-<em>Buffy</em> endeavor, <em>Firefly</em>.  Caplan told me that even he had been hesitant to invest in the development of <em>Firefly</em>-affiliated merchandise, until he saw that fans were willing to pay -- and pay well -- for anything connected to the show.  </p>

<p>While trading cards aren't an especially new niche business, Inkworks has demonstrated a particularly keen understanding of the fan/collector mentality: in addition to the basic set of cards in each line, there are a number of "bonus cards" distributed at random through the line.  The specific content of these cards varies from show to show, but generally includes "Autograph Cards," with actual signatures from cast members and "Pieceworks Cards," which contain tiny pieces of actual costumes worn on-screen during the show.  (Other interesting show-specific offerings include invisible ink messages on select cards tied into the spy-fi show <em>Alias</em>, which can only be seen when the card is placed under a black light.)  </p>

<p>For reference, a single pack of 6 trading cards costs $2.50.</p>

<p>While I didn't have the presence of mind to record my conversation with Caplan, it was clear to me that he understood (a) the power of creating limited quantities, and (b) that a small, engaged audience can be far more lucrative, especially to niche marketers, than a massive casual audience.  After all, as he pointed out to me, there's no market for <em>CSI: Miami</em> trading cards, even if it is <a href="http://news.bbc.co.uk/1/hi/entertainment/5231334.stm">the number one show in the world</a>.  </p>

<p>     One question worth considering: can collectible product lines like this be used as a barometer for the relative popularity of various franchises?</p>

<p>     (At some point in the future, I'll be interviewing Caplan, and will post any interesting results that come from that discussion either here or in the C3 Weblog.)</p> </div><br/><a href="http://www.henryjenkins.org/2006/08/comiccon_the_power_of_the_devo.html">Full Entry...</a><br /></p><hr>
<div class="stitle">Building Popular Buzz: What To Do, What Not To Do</div>By Henry Jenkins<br/><div class="sdate">Tue Aug 08, 2006 10:34:23 AM</div><br/><div class="content"><br/><p>This is the second of a series of guest blogs written by Comparative Media Studies graduate student and media analyst Ivan Askwith about his observations at this year's Comicon. </p>

<p>Based on the evidence from this year's ComicCon, the entertainment industry is slowly starting to understand just how important a vocal fandom can be in the success of a new brand or franchise.  As I indicated at the end of my <a href="http://www.henryjenkins.org/2006/08/ivan_from_comicon.html#more">last post</a>, this growing comprehension is most evident in the largest "panel events" -- on the ComicCon schedule, this generally means those events held in Ballroom 20, Hall 6CDEF, and Hall H, which can seat anywhere from 2000-6500 spectators.  Or, as the industry is learning to think of them, potential advertisers and advocates.  Some presentations were more overt than others, but almost all of the largest scheduled events were closer in tone to a high-powered sales pitch than an intimate discussion between fans and creators.</p>

<p>     That said, some presenters seem to have a more nuanced understanding of fan behavior than others.  As Henry has already discussed on<a href="http://www.henryjenkins.org/2006/06/the_snakes_on_a_plane_phenomen.html#more"> this blog</a>, no one is currently cultivating fan participation more effectively, or respectfully, than New Line Cinema, in promotion for <em>Snakes on a Plane.</em>  The panel for <em>SoaP</em> came at the end of a longer presentation from New Line, which featured previews of the <em>Final Destination 3</em> DVD  -- interesting insofar as it leverages the rarely-used interactive capabilities of DVD systems to let viewers determine the course of events at pivotal moments -- and the forthcoming Jack Black film, <em>Tenacious D in 'The Pick of Destiny'</em>.  But the audience and presenters both knew that these were diversions from the main attraction: as the discussion about <em>Tenacious D</em> wrapped up, the energy in the crowd became palpable, and when panel host Kenan Thompson finally spoke the words -- "Snakes On A Plane" -- the audience erupted with enthusiasm and applause.</p>

<p>     The entire presentation that followed demonstrated the same respectful appreciation of the internet fandom that has characterized the film's marketing campaign over the last several months.  The presentation began with a video which flashed the words "Thanks to you.... <em>Snakes on a Plane</em>.... is already the summer's most talked about movie.... and it's not even out yet."  This was followed with a several-minute montage collecting some of the best fan-generated content (spoofs, advertisements, posters, images, viral memes, etc), and used the winning entry from a fan-generated-soundtrack contest as the musical track.  The video ended with another sequence of titles, which declared "Thanks to you, <em>Snakes on a Plane</em> is one of the most anticipated movies.... ever."</p>
        <p>Based on the audience reaction, this isn't too far from the mark: the 6,500 seat Hall H was packed, with plenty of people standing in the back and even more turned away at the door, and the crowd responded enthusiastically to pretty much everything that was shown, said, or asked.  Most of the audience "questions" consisted of variations on a theme -- the theme, in this case, being what a bad-ass motherfucker Samuel L. Jackson is.  </p>

<p>In fact, one audience member straight out asked:<br />
<blockquote><br />
        "What's it like, always being such a bad-ass mother fucker?"</blockquote></p>

<p>To which Jackson replied:<br />
<blockquote><br />
        "It's great to be able to live that out on screen, but, you know, I don't walk around   every day thinkin' I'm a bad ass mother fucker.  I'm just trying to make it through the day, most days, but I thank you for feelin' that way about it... You're a bad mother fucker, man, thank you.  Thank you, thank you."  </blockquote></p>

<p>This was more or less the tone for the entire panel.  However, one audience member did ask an interesting, albeit predictable question:</p>

<p>     <blockquote>"Do you think that this movie will have a lasting effect on the way that the industry looks at internet hype?"<br />
</blockquote><br />
To which Jackson replied:</p>

<p>     <blockquote>I hope that people in studios are looking and paying attention and trying to figure out how and why this phenomenon took place.  I hope that there's some young filmmaker somewhere that knows, that understands that now they could put a premise on the internet -- 'my premise for this film is... boom... who has a scene?' -- and people will start writing the first scene for that particular film, and then they'll choose that scene.  Somebody'll write the next scene, and they'll choose that particular scene, until they end up with a whole film, and then somebody will say, 'Who do you think should be in this film?', and then they go through that, and they come up with a whole cast list of people, and if everybody sends a dollar in, we can hire these particular people and shoot this particular film, and we'll have a film that's all-inclusive, that's something that a lot of people came together on, and had a collaborative passion about.  And I think that would be kind of a wonderful thing to see happen.  And hopefully that will be somewhere down the line... [audience applauds]</blockquote></p>

<p>And while Jackson's scenario might be a little utopian for the near future, it suggests that he (and I suspect this carries over to many of the individuals working on this film) is beginning to recognize and respect the changing role of the audience, and the relatively awe-inspiring possibilities that emerge from the collective intelligence and energy of online fan communities.  A collaborative online movie might still be some way off, but as to the more immediate question that was posed, it seems clear that this movie has already had a significant effect on how the industry looks at internet hype.  Will it have a lasting effect? My guess is "Yes", in that it represents a substantial advance on the learning curve, as studios start to realize that there are right and wrong ways to engage with fan cultures.</p>

<p>     Speaking of "wrong ways," I feel obligated to report that some presentations demonstrated far less tact in their attempts to engage would-be fans.  During the World Premiere of NBC's forthcoming serial drama <em>Heroes</em>, which Henry has also discussed on <a href="http://www.henryjenkins.org/2006/07/sneak_preview_nbcs_heroes.html#more">this blog</a>, Executive Producer Jeph Loeb (a comics legend in his own right for his work on Batman and Superman) instructed the audience that their job was to go home after the screening, get on the internet, and talk to everyone they know, as much and as often as they could, about how much they loved the show.  While there's some room to encourage fans to be vocal in responding to a new show, I think it's a dangerous -- and potentially offensive -- move to instruct them to talk about how great a show is, especially before they've even seen it.  (Of course, Loeb repeated the instructions at least twice more during the post-screening discussion, and closed with them as well.)  But the guy sitting next to me gave a low, dismissive whistle during Loeb's first round of encouragement, muttering "Bad move", and (personal opinions of <em>Heroes</em> aside) I think he was absolutely right.</p>

<p>     The fact is that studios don't need, and perhaps can't, instruct fans to be fans, you just need to be responsive and encouraging once they express appreciation for your work.  If fans like what they see, they're going to talk about it -- it's part of the pleasure of being a fan.  And if they don't like what they see, odds are they're still going to talk about it, but you're better off if they don't.</p> </div><br/><a href="http://www.henryjenkins.org/2006/08/building_popular_buzz_what_to.html">Full Entry...</a><br /></p><hr>
<div class="stitle">Comic Book Foreign Policy? Part Four</div>By Henry Jenkins<br/><div class="sdate">Mon Aug 07, 2006 03:59:43 AM</div><br/><div class="content"><br/><p>This is the final installment (at least for the time being) of a series I have been doing about how the comic book world has responded to September 11 and the politics of Homeland Security. I wrote it in response to several recent essays that have offered somewhat stereotypical versions of how comic book superheroes relate to the current policies of the Bush administration. I wanted to show that comic books have, in general, avoided jingoism in favor of a more thoughtful engagement with the ways what happen at the World Trade Center have changed the society we live in.</p>

<p>In Part Three, I discussed three contemporary comic books --<em> DMZ </em>(published by DC's Vertigo imprint), <em>Ex Machina </em>(published by Wildstorm) and <em>Squadron Supreme</em> (published by Marvel) -- which suggest the lasting impact of September 11 on comics culture. The three books take somewhat different strategies for dealing with the current political landscape-- <em>DMZ </em>is speculative fiction about a future American Civil War that results in part from over-extending U.S. military presence overseas;<em> Ex Machina</em> offers us a political drama where the Mayor of New York City happens to be a superhero; and <em>Squadron Supreme </em>represents a team of superheroes whose pursuit of American foreign policy objectives pose a series of ethical concerns.</p>

<p>What these three books have in common is a refusal to offer easy answers or paint black and white pictures. All three suggest that there are multiple sides for any issue and try to constantly force readers to rethink our own assumptions. These books are hard to classify in left or right terms -- they are certainly critical of many aspects of current policies, especially those that involve violations of civil liberties, but then, only about 30 something percent of the American public might be described as enthusiastic about those policies on any given week. A large number of libertarians and traditional conservatives are raising serious concern about our current Homeland Security policies along similar lines. Each of these books tap  the genre conventions of popular culture but use them to focus attention on crucial social and political concerns. </p>

<p>Near the end of <em>Convergence Culture</em>, I speculate that popular culture may provide a common ground for us to explore important policy issue precisely because we are often willing to suspend fixed ideological categories in order to explore its fantasies; because we don't define our relationship to popular culture exclusively or primarily in partisan terms; because it offers a shared set of metaphors to talk about things that matter to us; and because it brings together a community that cuts across party lines. As Barrack Obama might have said, we watch <em>West Wing</em> in the red states and we watch<em> 24</em> in the blue states, and if we can talk together as fans, maybe we can rebuild a basis for communications on other levels. In this context, popular culture has a vital role to play as civic media. As a comics fan, I am proud to see the comics industry rise to the occasion perhaps better than any other entertainment medium (well, excluding the fine work going on over at Comedy Central.)</p>

<p>That's why I am so excited about Marvel's <em>Civil War </em>project this summer. </p>
        <p><u>Civil War</u></p>

<p>For one thing, the comics I discussed above, though released by major publishers who have good distribution, still represent relative niche products. They don't involve any of the major franchises at DC or Marvel that account for the overwhelming majority of sales of American published comics in this country (I phrase it this way to separate out the huge success of manga which is a separate story for another day.) <em>Civil War</em>, by contrast, involves Spiderman, Iron Man, Captain America, The Fantastic Four, and every major figure in the Marvel universe.  And it is an epic story that is going to occupy much of the Marvel universe for the better part of six months.</p>

<p>Here's how the core premise of the series gets described in a recent recap:</p>

<blockquote>After Stamford, Connecticut is destroyed during a televised fight between the New Warriors and a group of dangerous villains, public sentiment turns against super heroes. Johnny Storm, the Human Torch, is attacked outside a nightclub and beaten into a coma. Advocates call for reform and a Superhuman Registration Act is debated, which would require all those possessing paranormal abilities to register with the government, divulge their true identities to the authorities and submit to training and sanctioning in the manner of federal agents. One week later, the Act is passed. Any person with superhuman powers who refuses to register is now a criminal. Some heroes, such as Iron Man, see this as a natural evolution of the role of superheroes in society, and a reasonable request. Others view the Act as an assault on their civil liberties. After being called upon to hunt down heroes in defiance of the Registration Act, Captain America goes underground and begins to form  a resistance movement.</blockquote>
<u>
Across the Marvel Universe</u>

<p>Normally, I am skeptical about these large scale events that cut across the entire universe of a particularly publishing company which often represent a better marketing strategy than they do storytelling practice.  The goal is to get readers buying more books in a given month by dribbling out bits of the story across as many different titles as possible. Yet, <em>Civil War</em> demonstrates to me the power of this mode of expanded  storytelling. For one thing, the issues raised by this book are big and they demand a large amount of development if they are not going to be dismissed with some simplistic swat of the hand (this could still happen before everything is over with). But seeing them unfold across close to a hundred issues allows them to be explored with a depth and scope that few other media systems could accommodate. </p>

<p>For another, <em>Civil War</em> exploits this transmedia system's ability to show the same events from multiple characters' points of view and thus to invite us to reread it from conflicting (and self-conflicted) political perspectives. In one book, we may see what an incident means for those, such as Iron Man or Spider-Man or Mr. Fantastic, who are supporting the registration act. In another, we may see it from the perspective of Captain America and the others who are resisting it. in another we may see it from the perspective of the X-Men who are trying to remain neutral or the Thing who seems to be really struggling to do the right thing without any strongly developed political sense. New titles such as <em>Civil War</em> and <em>Frontline</em> have been created to bring together the conflicting perspectives within a single issue. <em>Frontline</em> shows the story from the perspective of two reporters -- Ben Ulrich whose editor wants him to improve their readership by stirring up anger against unregistered superheroes and Sally Floyd whose publisher sees the act as the latest intrusion of the state into the lives of its citizens and who thus has special access to the underground resistance movement. This storyline suggests the degree to which news agencies are shaped by the agendas of their editors and construct different representations of the news -- starting from whom they talk to, what questions they ask, and what ends up getting into print. Marvel has even published a special newsprint edition of the <em>Daily Bugle </em>that shows us how these events play themselves out across all of the different beats in a major newspaper.</p>

<p><br />
This ability to spread the story across all of these different vantage points also increases the likelihood that for at least some readers, their favorite hero ends up on an ideological side different from their own, opening them to listening more closely to the arguments being formed out of sympathy for a character they have invested in for years and years. Finally, given the ways comics publishing works with different books appearing each week, this strategy insures that we live with the <em>Civil War </em>storyline every week for months on end, where-as if it were contained in only one series, we would reconnect with it once a month. (DC has solved this problem with 52, a series that comes out every week but this is regarded as a special event in its own right.)  All of this uses the potential of a publisher-wide event to intensify debate and discussion about core issues, such as liberty, privacy, civil disobedience, and the power of the state, that could not be timelier in our current political context.</p>

<p><u>Comic Books Meet Political Reality</u></p>

<p>Of course, comic book superheroes, per necessity, deal with these issues at one level removed from our actual political reality -- so much the better if it breaks us out of fixed and partisan categories of analysis and opens us to explore these issues from new points of view.  Keep in mind though that Marvel uses many real world references to anchor the stories in our reality so Jonas Jameson is seen getting ready for an appearance on O'Reilly where he will speak out in support of the law and Luke Cage compares the threat of political violence directed against superheroes to what happen to blacks in Mississippi during the civil rights era. Each issue of <em>Civil War</em> ends with a short segment that introduces readers to one or another political debate from world history that offers some parallels to the concerns being discussed -- including one discussion of the relocation of Japanese-Americans during World War II. </p>

<p>And, as reader Tama Leaver notes at <a href="http://ponderance.blogspot.com/2006/07/marvel-comics-civil-war-and-war-on.html">his bog</a>,  there are strong parallels drawn between what happens to Speedball, one of the young superheroes most centrally involved in the incident, as "an unregistered combatant" and the various prisoners at Gitmo, who have neither been accused of crimes nor treated as war prisoners:<br />
<blockquote><br />
Speedball's experiences have marked similarities with the experiences of 'enemy combatants' (as opposed to prisoners of war) held (illegally) in the US "facilities" in Guantanamo. As Robert Baldwin is carted off to jail, he's told that a purpose-built prison is being constructed to indefinitely hold superhumans who refuse to register and follow government directives, a plot point echoing the 2002 construction of the Camp Delta detainment facility in Guantanamo Bay. While the Civil War story isn't completely black and white--Peter Parker's own deliberations certainly give the pro-registration side a humane voice--the critique of many aspects of the current War on Terror and the illegal detention and torture of untried 'enemy combatants' is bold and blatant on the part of Marvel's storytellers. Personally, I'm heartened by Marvel's stance and hope empathy with their comic book heroes will give readers a moment to think further about politics in the wider world.</blockquote></p>

<p><br />
Of course, comic book superheroes deal with these issues in somewhat broad strokes -- often through fisticuffs -- and after all, this series, which pits superhero against superhero on every page, is an adolescent fan's wet dream. Comic books have long sought pretexts which allow us to find out (or usually leave unresolved) whether the Thing or the Hulk is stronger. And this series has had some amazing showdowns between Captain America and long-time allies such as Iron Man or Spider-Man. But, the heart of the series has not been about physical violence but about political debates that the characters have had with each other and with themselves.  The slugfests include not the usual quips or monologues but an open debate about public policy issues in between hurling the mighty shield or spraying spider gunk. The various members of the Fantastic Four, for example, have been split asunder by these issues -- all the more so since Johnny Storm was a victim of anti-cape violence while Reed Richards has ended up using his simulation models to build the case for the registration act.  As Sue Storm Richards protests, this act will mean jail time for "half of our Christmas card list" and creates a series of ethical challenges that make the McCarthy era seem like child's play as the protagonists not only decide whether to reveal their own identities but also whether to name names of their associates and even whether to use force -- even deadly force -- to bring them to jail when they resist the controversial law.<br />
<u><br />
Complicating Our Positions</u><br />
The book's refusal to offer simple feel-good perspectives on these issues is suggested by these comments by Mark Millar, one of the author's involved, during an interview at<a href="http://www.comicbookresources.com/news/newsitem.cgi?id=7088"> Comic Book Resources</a>:<br />
<blockquote><br />
Some readers might be incorrectly try to frame the ideological split in Civil War as Conservative versus Liberal. It's really lazy writing to make everything black and white. I'm a politics buff and I really hate seeing America divided into red and blue states because I know people in red states who have blue opinions. And we're all very complex. No one person can really even be described as a liberal or a conservative. I'm a liberal but I totally believe in the death penalty on occasions. People are more complex than you think and I wanted to do the same thing with superheroes....</p>

<p>The most obvious thing to do would have been to have Captain America as a lap dog of the government. So, I've played around with everyone's personalities a little and really just tried to get in under their skin and have them feeling very confused about it, too. Some of them actually end up changing their minds and crossing sides because it's a very complex issue.</p>

<p>So, to polarize it in terms of Conservative and Liberal would have been a big mistake. And I think you don't want to think of your superheroes as being Liberal or Conservative. I think those guys should be above that. What I've done is made everyone sympathetic, but everyone pretty passionate about what they believe in.</blockquote></p>

<p>As Millar continues, he makes clear that it would be too neat to read Captain America and his allies as either freedom fighters or terrorists. There is enough moral ambiguity to go around (and we see even some of the most partisan characters -- Spiderman for example -- anguish over the choices they are being forced to make.)<br />
<blockquote><br />
They will be a combination of both reactive and proactive. I didn't want to just have these guys in, say, like a terrorist cell or anything because fundamentally Cap's guys are superheroes. So, the rationale for the Marvel Universe shouldn't be that they're just underground guys who are constantly fighting the forces of the status quo. They've got to be superheroes. They've got to go out and actually fight super villains and, unfortunately, SHIELD and the other superheroes are after them when they're doing so. It's an added tension to the whole thing.</blockquote></p>

<p>At the end of the day, the book isn't so much taking positions as raising questions that we as a society need to be debating. There has been a tendency in recent years to depict questioning government authorities as somehow unpatriotic or assuming that questions lead inevitably towards one or another partisan conclusion. But I think we are well served when our popular culture asks hard questions and I rejoice when it forces me to rethink my own political investments. </p>

<p>There's so much more that one could say about this series. I had planned to run a whole lot of examples of the political reflections of various partisans here to suggest the range of perspectives we encounter -- including the use of non-American characters like Black Panther or Namor to give us some sense of how the world sees America's political turmoil. But at the end of the day, the power of these speeches lies in their contexts. They mean more if you've read these characters for years, know their personalities and backstories, and can anticipate what some of this means for the future of their series. They mean more if you see them on the pages of a comic book coming out of the mouths of brightly colored superhero characters and realize what a statement it is for Marvel to be telling this particular story in the Summer of 2006.  <br />
</p> </div><br/><a href="http://www.henryjenkins.org/2006/08/comic_book_foreign_policy_part_3.html">Full Entry...</a><br /></p><hr>
<div class="stitle">Comic Book Foreign Policy? Part Three</div>By Henry Jenkins<br/><div class="sdate">Fri Aug 04, 2006 02:58:14 AM</div><br/><div class="content"><br/><p>Sorry for the wait, oh loyal readers of this here blog. But today, I am finally able to sit down and plow out the third installment of my series about how the comic book world has responded to 9/11 and the on-going War on Terror. </p>

<p>Some of you will know that this was inspired by Michael Dean's "The New Patriotism" which was serialized in recent issues of <em>Comics Journal </em>and argued that comics were "circling the wagons" in response to the perceived threat to national security. As Dean puts it, "Now, some 60 years after the height of WWII and some 30 years after the end of the Vietnam War, mainstream comics seem to be making tentative gestures toward recreating the glory days of the wartime propaganda comic." </p>
ations of the current debates that also might seem very relevant to this discussion, such as Rick Veith's <em>Can't Get No </em>(which I haven't gotten any of yet), Joe Sacco's various projects in using comics to report on life in the middle east, Ted Rall's book on his trip to Afghanistan, cultural theorist Douglas Rushkoff's strange fusion of politics and religion in <em>Testament</em> or Art Spigelman's <em>In the Shadows of No Towers</em> which used imagery for early comic strips to reflect on his own conflicting feelings at 9/11. </p>

<p>Part of what I want to suggest here is that individually, comic book writers and artists -- both mainstream and niche -- have used their work to encourage their readers to ask hard questions about contemporary society and that collectively, they have provided a more diverse range of perspectives on these issues than can be found within the mainstream media. <br />
</p>
        <p></p>

<p><u><br />
DMZ</u></p>

<p><em>DMZ</em>, published by Vertigo, is the work of writer Brain Wood and artist Riccardo Burchelli. Regular readers of this blog will note that this is the third shout out to Wood in the past month -- reflecting on three very different projects, his superhero series (<em>Demo</em>), his reflections on local culture <em>(Local</em>) and now his book depicting a domestic civil war (<em>DMZ</em>). Frankly, I regard Wood to be one of the best writers working in comics today -- someone who has found a way to infuse popular narratives with alternative narrative and political perspectives.  <em>DMZ </em>drops a young reporter in training from Liberty Network behind the lines in a war-torn Manhattan. As Wood explains in a <em>Comic Book Resource </em><a href="http://www.comicbookresources.com/news/newsitem.cgi?id=6168">interview</a>:<blockquote></p>

<p> Middle America, literally, has risen up out of frustration, anger, and poverty to challenge the government's position of preemptive war and police action throughout the world. It's left America neglected and unattended, and also unprotected, at least from a major threat within its own borders. Then isolationist and religious militias get involved and arm the people, and then it's suddenly the Second American Civil War. They push to the coasts where they're stopped, creating a no-man's-land in Manhattan, with the 'Free Armies' in Jersey facing off against the US Army in Brooklyn....The politics of such a conflict are a little weird," Wood continued. "Initial reactions to the news of this book have made attempts to paint it as a 'liberal ranting against the conservatives,' but that's not actually possible in this scenario. Democrats can be and are every bit as hawkish as Republicans in times of war, and anyway, the two warring groups in 'DMZ' are just extremists fighting extremists. Homegrown insurgents fighting an extremist government regime, and it's the sane, normal people of all political affiliations that are caught in the middle.</blockquote></p>

<p>Matty, a young journalist in training --raised in sheltered Long Island in a wealthy family, interned with Liberty Networks -- finds himself stranded in the demilitarized zone where he has access to partisans and insurgents of all stripes and becomes their only means of communicating their perspectives to the country at large. The result is a classic story of political awakening.  At first, he clings to the simplified version of the war that has been communicated through the national news media but increasingly, what he sees and experiences forces him to rethink the propaganda machine which has shaped public understanding of the conflict. </p>

<p>Wood has described the world he is traveling through as equal parts <em>Escape From New York</em>, Falluja, and New Orleans right after Katrina." He adds:</p>

<table
                                        style="width: 100%; text-align: left; margin-left: auto; margin-right: auto;"
                                        border="0" cellpadding="2" cellspacing="0">
                                        <tbody>
                                        <tr><td><a href="planet:up">Newer Entries</a></td><td style="text-align: right;"><a href="planet:down">Older Entries</a></td></tr></tbody></table></body></html>"""
			
			
        print len(html)
        print long(len(html))
        self._embed.open_stream("http://www.boingboing.net/","text/html")
        while len(html) > 60000:
        	self._embed.append_data(html, long(len(html[0:60000])))
        	html = html[60000:]
        self._embed.append_data(html, long(len(html)))	
        self._embed.close_stream()
        self.count += 1
        return True
        
     
    def __open_uri(self, thing1, thing2):
    	print thing1, thing2
        if self.first == False:
            self.first = True
            return False
        return True

    def main(self):
        # All PyGTK applications must have a gtk.main(). Control ends here
        # and waits for an event to occur (like a key press or mouse event).
        gtk.main()
        

# If the program is run directly or passed as an argument to the python
# interpreter then create a HelloWorld instance and show it
if __name__ == "__main__":
    hello = HelloWorld()
    hello.main()
