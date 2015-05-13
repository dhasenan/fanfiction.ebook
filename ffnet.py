#!/usr/bin/env python
# coding=utf-8

# TODO: image support

import argparse
import codecs
import datetime
import io
import os
import pycurl
import re
import string
import sys
import time

from bs4 import BeautifulSoup
from bs4 import UnicodeDammit
from StringIO import StringIO

class PortkeyAdapter:
    ReportRegex = re.compile('http.*portkey.*act=report.*')
    AuthorProfileRegex = re.compile('/profile/.*')

    def CanHandle(self, url):
        return 'portkey.org/' in url

    def StoryUrl(self, raw_url):
        if not raw_url.endswith('/'):
            return raw_url + '/'
        return raw_url

    def Title(self, first_page_soup):
        # PORTKEYORG >> Foobar and the Rackinfrats - Chapter 1
        title = unicode(first_page_soup.find('title').contents[0])
        title = title.replace('PORTKEY.ORG >> ', '')
        title = title.replace('PORTKEY.ORG &gt;&gt;', '')
        title = title[0:title.rfind(' - Chapter')]
        return title.strip()

    def Author(self, page_soup):
        link = page_soup.find('a', href=PortkeyAdapter.AuthorProfileRegex)
        return unicode(link.string)

    def ChapterTitle(self, page_soup):
        title = unicode(page_soup.find('title').contents[0])
        title = title[title.rfind('- Chapter:'):]
        title = title[len('- Chapter:'):]
        title = 'Chapter' + title
        return title

    def ChapterContents(self, page_soup):
        outer_tds = page_soup.findAll('td')
        outer_td = None
        for td in outer_tds:
            for k, v in td.attrs:
                if k == 'class' and v == 'story':
                    outer_td = td
                    break
            if outer_td:
                break
        if not outer_td:
            return None
        # This contains a "report to admins" link and the show-ads javascript. We'll excise that.
        map(lambda x: x.decompose(), outer_td.findAll('script'))
        map(lambda x: x.decompose(), outer_td.findAll('noscript'))
        map(lambda x: x.decompose(), outer_td.findAll('img'))
        map(lambda x: x.decompose(), outer_td.findAll('a', href=PortkeyAdapter.ReportRegex))
        for center in outer_td.findAll('center'):
            if not center.string:
                center.decompose()
        return outer_td

    def ChapterCount(self, page_soup):
        select = self._FindChapterSelect(page_soup)
        if select:
            return len(select.findAll('option'))
        return 1

    def _FindChapterSelect(self, page_soup):
        selects = page_soup.findAll('select')
        for s in selects:
            for k, v in s.attrs:
                if k == 'class' and v == 'boxedsmall':
                    return s

    def ChapterUrl(self, story_url, chapter):
        return story_url + unicode(chapter)


class FFNetAdapter:
    UrlRegex = re.compile('fanfiction\.net/s/([0-9]+)(?:$|/.*)')
    AuthorProfileRegex = re.compile('/u/.*')

    def CanHandle(self, url):
        return 'fanfiction.net/' in url

    def StoryUrl(self, raw_url):
        match = FFNetAdapter.UrlRegex.search(raw_url)
        if match:
            story_id = int(match.group(1))
        else:
            raise ValueError("story id should be either a URL or a story id")
        return 'http://www.fanfiction.net/s/%s/' % story_id

    def Title(self, page_soup):
        # PORTKEYORG >> Foobar and the Rackinfrats - Chapter 1
        chapter_title = self.ChapterTitle(page_soup)
        title = unicode(page_soup.find('title').contents[0])
        if chapter_title and chapter_title in title:
            title = title[0:title.rfind(chapter_title)]
        else:
            title = title[0:title.rfind(',')]
            title = title[0:title.rfind('Chapter')]
        title = title[0:title.rfind('|')].strip()
        return title.strip()

    def Author(self, page_soup):
        top = page_soup.find('div', id='profile_top')
        link = top.find('a', href=FFNetAdapter.AuthorProfileRegex)
        return unicode(link.string)

    def ChapterTitle(self, page_soup):
        select = page_soup.find('select', id='chap_select')
        if not select:
            return ''
        for s in select.findAll('option'):
            for k, v in s.attrs:
                if k == 'selected':
                    return u'Chapter ' + unicode(s.string)
        return 'Missing chapter title'

    def ChapterContents(self, page_soup):
        return page_soup.find('div', id='storytext')

    def ChapterCount(self, page_soup):
        select = page_soup.find('select', id='chap_select')
        if not select:
            return 1
        return len(select.findAll('option'))

    def ChapterUrl(self, story_url, chapter):
        return story_url + unicode(chapter)


class BbForumAdapter:
    def CanHandle(self, url):
        # TODO: examine content to see if it's a BB forum thread
        return 'forums.spacebattles.com' in url

    def StoryUrl(self, raw_url):
        if re.match('page-[:digit:]+', raw_url.rsplit('/', 2)[1]):
            return raw_url.rsplit('-', 2)[0]
        if raw_url.endswith('/'):
            return raw_url + 'page-'

    def ChapterUrl(self, story_url, chapter):
        return story_url + unicode(chapter)
    
    def Title(self, page_soup):
        h1 = page_soup.find('h1')
        return unicode(h1.contents[0])

    def Author(self, page_soup):
        return page_soup.select('li.message')[0]['data-author']

    def ChapterCount(self, page_soup):
        pagenav = page_soup.select('div.PageNav')[0]
        if 'threadmarksSinglePage' in pagenav['class']:
            return 1
        return int(pagenav['data-last'])

    def ChapterTitle(self, page_soup):
        return None

    def ChapterContents(self, page_soup):
        fixup = BeautifulSoup()
        for a in page_soup.findAll('article'):
            fixup.append(a)
            fixup.append(fixup.new_tag('hr'))
        return fixup


class ParagraphCleaner:
    def Clean(self, p):
        # Recurse through, changing quotes. Look for blockquote indicators (centered + italics).
        self.last_quote = None
        self.quote_count = 0
        self.is_blockquote = False
        self.SearchThrough(p)

    def SearchThrough(self, node):
        try:
            kids = node.contents
        except AttributeError:
            kids = []
        if kids:
            for kid in kids:
                self.SearchThrough(kid)
        elif node.string:
            # String node.
            # I can replace [non-letter]'[letter] with \1&lsquo;\2 and [letter]' with &lsquo;\1.
            # Mostly.
            # People can nest quotes in terrible arbitrary ways.
            # But '[letter] is always a left quote and [letter]' is always a right quote.
            # And [letter]'[letter] is always an apostrophe, which should be rendered as a right quote
            s = ''
            orig = node.string              \
                .replace(u'--', u'&mdash;')   \
                .replace(u'...', u'&hellip;') \
                .replace(u'â€”', u'&mdash;')
            for i in range(len(orig)):
                c = orig[i]
                if c == '\'':
                    s += self.Requote(orig, i, '&lsquo;', '&rsquo;')
                elif c == '"':
                    s += self.Requote(orig, i, '&ldquo;', '&rdquo;')
                else:
                    s += c
            node.replaceWith(s)

    def Requote(self, orig, i, lquo, rquo):
        sign = orig[i]
        other = '"' if sign == '\'' else '\''
        # Apostrophe or quote.
        left_letter = i > 0 and orig[i - 1] in string.ascii_letters
        right_letter = i < len(orig) - 1 and orig[i + 1] in string.ascii_letters
        if left_letter and right_letter:
            # Apostrophe! (Or terrible formatting.)
            return rquo
        # Quote or dropped letters.
        # The punctuation list isn't exhaustive; we're doing best effort here.
        if left_letter or (i > 0 and orig[i - 1] in ',.!?;-:'):
            if self.last_quote == sign:
                self.quote_count -= 1
                self.last_quote = other
            return rquo
        if right_letter:
            self.last_quote = sign
            self.quote_count += 1
            return lquo
        if self.last_quote == sign:
            self.quote_count -= 1
            if self.quote_count > 0:
                self.last_quote = other
            return rquo
        else:
            self.last_quote = sign
            self.quote_count += 1
            return lquo

class Story:
    def __init__(self, title, author, chapters):
        self.title = title
        if type(self.title) != unicode:
            print('Unexpected title type %s' % type(self.title))
        self.author = author
        if type(self.author) != unicode:
            print('Unexpected author type %s' % type(self.author))
        self.chapters = chapters
        self.cover = None
        self.filename = None

    def Filename(self, ext):
        if not self.filename:
            if type(self.title) != unicode:
                print('Unexpected title type %s' % type(self.title))
            base = self.title.replace(':', '_').replace('?', '_')
            if type(base) != unicode:
                print('Unexpected title type %s' % type(base))
            self.filename = self.title.replace(':', '_').replace('?', '_')
        return '%s.%s' % (self.filename, ext)

    def ToHtml(self):
        soup = BeautifulSoup('<html><head><title></title></head><body></body></html>')
        soup.head.title.append(self.title)
        for chapter in self.chapters:
            soup.body.append(chapter.ToHtml(soup))
        return soup

class Chapter:
    def __init__(self, title, contents, soup):
        """Initialize this chapter.
        
        Args:
          title: The title of the chapter.
          contents: The contents of the chapter as a BeautifulSoup object.
        """
        self.title = title
        self.contents = contents
        self.soup = soup

    def ToHtml(self, soup):
        if self.title:
            chapter = BeautifulSoup('<div><h1 class="chapter"></h1></div>')
            chapter.h1.append(self.title)
            chapter.append(self.contents)
            return chapter
        return self.contents


class Munger:
    def __init__(
            self,
            story_url,
            adapter,
            formats=['epub', 'mobi'],
            clean=False,
            mote_it_not=True,
            pretty=True,
            afternote=None,
            filename=None):
        self.story_url = adapter.StoryUrl(story_url)
        self.adapter = adapter
        self.formats = formats
        self.clean = clean
        self.pretty = pretty
        self.afternote = afternote
        self.filename = filename
        self.cover = None

        self._cleaner = ParagraphCleaner()

    def DownloadAndConvert(self):
        story = self.DownloadStory()
        self.CreateEbook(story)

    def DownloadStory(self):
        chapter1 = self.DownloadChapter(1)
        title = self.adapter.Title(chapter1)
        print title
        author = self.adapter.Author(chapter1)
        chapter_count = self.adapter.ChapterCount(chapter1)
        chapters = [self.ToChapter(chapter1)]
        for i in range(2, chapter_count + 1):
            time.sleep(2)
            raw = self.DownloadChapter(i)
            chapters.append(self.ToChapter(raw))
        # TODO put this into rationality.py instead -- it can deal.
        if self.afternote:
            final = chapters[-1].contents
            after = Tag(chapters[-1].soup, 'div')
            after.insert(0, NavigableString(self.afternote))
            final.insert(len(final.contents), after)
        return Story(title, author, chapters)


    def ToChapter(self, raw):
        contents = self.adapter.ChapterContents(raw)
        title = self.adapter.ChapterTitle(raw)
        chapter = Chapter(title, contents, raw)
        self.CleanChapter(chapter)
        return chapter


    def CreateEbook(self, story):
        html = story.ToHtml()
        print 'writing story to %s.html' % story.Filename('html')
        filename = self.filename or story.Filename('html')
        if not filename.endswith(".html"):
          filename = filename + ".html"
        f = io.open(filename, 'w')
        f.write(unicode(html))
        f.flush()
        f.close()

        for outtype in self.formats:
            pid = os.fork()
            if pid == 0:
                os.execvp('ebook-convert', self._Args(story, outtype, filename))
                return
            os.waitpid(pid, 0)

    def _Args(self, story, outtype, filename):
        convertedFilename = filename.replace('.html', '.' + outtype)
        std_args = ['', filename, convertedFilename]

        if story.author != None:
            std_args += ['--authors', story.author]

        if story.cover != None:
            std_args += ['--cover', story.cover]
        return std_args

    def CleanChapter(self, chapter):
        if not self.pretty:
            return
        for p in chapter.contents.findAll('p'):
            self._cleaner.Clean(p)

    def DownloadChapter(self, chapter):
        print 'retrieving chapter %s' % chapter
        url = self.adapter.ChapterUrl(self.story_url, chapter)
        buf = io.BytesIO()
        c = pycurl.Curl()
        c.setopt(pycurl.USERAGENT,
                'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:8.0) Gecko/20100101 Firefox/8.0')
        c.setopt(pycurl.URL, url)
        c.setopt(pycurl.WRITEFUNCTION, buf.write)
        c.setopt(pycurl.FOLLOWLOCATION, 1)
        c.perform()
        raw_content = buf.getvalue()
        buf.close()
        text = UnicodeDammit(raw_content, smart_quotes_to="html").unicode_markup
        return BeautifulSoup(text)


def main():
    parser = argparse.ArgumentParser(description="Convert fanfiction.net stories to ebooks")
    parser.add_argument("stories", help="links or story ids for stories to convert", nargs="+",
            type=str, metavar="story")
    parser.add_argument("--epub", "-e", dest="epub", action="store_true",
            help="produce epub (nook) output only")
    parser.add_argument("--mobi", "-m", dest="mobi", action="store_true",
            help="produce mobi (kindle) output only")
    parser.add_argument("--formats", "-f", dest="formats", nargs=1,
            help="comma-separated list of formats (eg epub, mobi)")
    parser.add_argument("--clean", "-c", dest="clean", action="store_true",
            help="remove intermediate files")
    parser.add_argument("--raw", "-r", dest="raw", action="store_true",
            help="don't prettify text (curly quotes, nicer blockquotes, etc as in original)")
    parser.add_argument("--somoteitbe", "-s", dest="somoteitbe", action="store_true",
            help="allow an egregiously overused and terrible phrase to be used")
    args = parser.parse_args()
    formats = ["mobi", "epub"]
    if args.formats:
        formats = args.formats
    elif args.epub and args.mobi:
        pass  # default
    elif args.epub:
        formats = ["epub"]
    elif args.mobi:
        formats = ["mobi"]
    if not args.stories:
        sys.stderr.write("Usage: %s [story id|url]\n")
        exit(1)

    adapters = [PortkeyAdapter(), FFNetAdapter(), BbForumAdapter()]
    for story in args.stories:
        for adapter in adapters:
            if not adapter.CanHandle(story):
                continue
            munger = Munger(
                    story,
                    adapter,
                    formats=formats,
                    clean=args.clean,
                    mote_it_not=not args.somoteitbe,
                    pretty=not args.raw)
            munger.DownloadAndConvert()

if __name__ == "__main__":
    main()
