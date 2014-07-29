#!/usr/bin/env python
# coding=utf-8

import argparse
import codecs
import datetime
import io
import os
import pycurl
import re
import string
import sys

from BeautifulSoup import BeautifulSoup
from StringIO import StringIO

TARGET="http://www.fanfiction.net/s/%s/%s/"
URLFORMAT="fanfiction\.net/s/([0-9]+)(?:$|/.*)"


class ParagraphCleaner:
    def clean(self, p):
        # Recurse through, changing quotes. Look for blockquote indicators (centered + italics).
        self.last_quote = None
        self.quote_count = 0
        self.is_blockquote = False
        self.search_through(p)

    def search_through(self, node):
        try:
            kids = node.contents
        except AttributeError:
            kids = []
        if kids:
            for kid in kids:
                self.search_through(kid)
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
                    s += self.requote(orig, i, '&lsquo;', '&rsquo;')
                elif c == '"':
                    s += self.requote(orig, i, '&ldquo;', '&rdquo;')
                else:
                    s += c
            node.replaceWith(s)

    def requote(self, orig, i, lquo, rquo):
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


class FFNetMunger:
    def __init__(
            self,
            story_id,
            marker=None,
            formats=["epub", "mobi"],
            clean=False,
            mote_it_not=True,
            pretty=True):
        try:
            self.story_id = int(story_id)
        except:
            match = re.search(URLFORMAT, story_id)
            if match:
                self.story_id = int(match.group(1))
            else:
                raise ValueError("story id should be either a URL or a story id")
        self.marker = marker
        self.clean_html = clean
        self.formats = formats
        self.mote_it_not = mote_it_not
        self.pretty = pretty

        self.div_re = re.compile('<div.*?</div>', re.DOTALL)
        self.min_chapters = 0
        self.filename = None
        self.author = None
        self.cover = None

    def process(self):
        self.content, self.name = self.retrieve()
        if self.filename is None or self.filename is "":
            self.filename = self.name
        self.write()
        self.convert()
        self.clean()

    def find_count(self, c):
        count = 0
        regex = re.compile("SELECT[^>]*title=['\"]chapter navigation['\"]", re.I)
        if len(regex.split(c)) == 1:
            count = 1
        else:
            kernel = regex.split(c)[-1]
            kernel, a, b = kernel.partition("</select>")
            f = re.compile("option\\s*value=\"{0,1}([0-9]*)")
            for match in f.finditer(kernel):
                g, = match.groups(1)
                current = int(g)
                if count < current:
                    count = current
        print "total of %s chapters" % count
        return count


    def guts(self, c):
        kernel = re.split("<div[^>]*class='storytext\\b.*?>", c, 1)[1]
        while True:
            kernel, n = self.div_re.subn('', kernel)
            if n == 0:
                break
        kernel, a, b = kernel.partition("</div>")
        if self.mote_it_not:
            return (kernel
                    .replace('o mote it be', 'o be it')
                    .replace('o Mote It Be', 'o Be It')
                    .replace('O MOTE IT BE', 'O BE IT')
                    )
        else:
            return kernel

    def get_author(self, chapter):
        a, b, kernel = chapter.partition(" href='/u")
        kernel, a, b = kernel.partition("</a>")
        a, b, kernel = kernel.partition(">")
        return kernel.strip()

    def get_name(self, chapter, count):
        a, b, kernel = chapter.partition("<title>")
        if count > 1:
            kernel, a, b = kernel.partition("Chapter")
        else:
            kernel, a, b = kernel.partition("</title>")
            kernel, a, b = kernel.rpartition("| FanFiction")
            kernel, a, b = kernel.rpartition(", a ")
        return kernel.strip()

    def title(self, c):
        a, b, kernel = c.partition("<title>")
        kernel, a, b = kernel.partition("</title>")
        a, b, kernel = kernel.partition("Chapter ")
        kernel, a, b = kernel.rpartition(",")
        return "Chapter " + kernel # calibre needs 'chapter' to help its chapter detection

    def download(self, chapter):
        print "retrieving chapter %s" % chapter
        # TODO this doesn't like non-ascii characters
        buf = io.BytesIO()
        c = pycurl.Curl()
        c.setopt(pycurl.USERAGENT,
                'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:8.0) Gecko/20100101 Firefox/8.0')
        c.setopt(pycurl.URL, TARGET % (self.story_id, chapter))
        c.setopt(pycurl.WRITEFUNCTION, buf.write)
        c.setopt(pycurl.FOLLOWLOCATION, 1)
        c.perform()
        raw_content = buf.getvalue()
        buf.close()
        return codecs.decode(raw_content, 'utf8')

    def wrong_story(self, c):
        if self.marker is None:
            return False
        a, b, kernel = c.partition("<title>")
        kernel, a, b = kernel.partition("</title>")
        return string.find(kernel, self.marker) == -1

    def retrieve(self):
        chapters = []
        titles = []

        first = self.download(1)
        count = self.find_count(first)
        if count < self.min_chapters:
            raise Exception('Expected at least %s chapters, only found %s' % (self.min_chapters, count))
        name = self.get_name(first, count)
        if not self.author:
            self.author = self.get_author(first)
        chapters.append(first)
        titles.append('')

        # grab the items:
        for i in range(2, count + 1):
            chapters.append(self.download(i))
            titles.append('')


        # extract the essential bits from each chapter:
        for i in range(len(chapters)):
            print "munging chapter %s" % (i + 1)
            c = chapters[i]
            if self.wrong_story(c):
                sys.stderr.write("chapter %d came from wrong fic" % i)
                chapters[i] = self.download(i)
            chapters[i] = self.clean_chapter(self.guts(c))
            titles[i] = self.title(c)
            print titles[i]

        # jam it into one string, with appropriate header and footer:
        contents = StringIO()
        contents.write(u"""<html>
        <head>
            <title>%s</title>
        </head>
        <body>
    """ % name)
        for i in range(len(chapters)):
            contents.write(
                u"<h1 class='chapter'>%s</h1>\n<div>%s</div>\n" % (titles[i], chapters[i]))

        contents.write(u"</body></html>")

        return contents, name

    def clean_chapter(self, chapter_contents):
      if not self.pretty:
        return chapter_contents
      soup = BeautifulSoup(chapter_contents)
      for p in soup.findAll('p'):
        self.clean_paragraph(p)
      s = unicode(soup)
      return s

    def clean_paragraph(self, p):
        ParagraphCleaner().clean(p)

    def write(self):
        self.write_to(self.filename)
        now = datetime.datetime.now()
        date = now.strftime("%Y-%m-%d")
        if not self.clean:
            self.write_to("%s-%s" % (self.filename, date))

    def clean(self):
        if self.clean_html:
            os.remove("%s.html" % self.filename)

    def write_to(self, filename):
        print 'writing story to %s.html' % filename
        f = io.open(filename + ".html", "wb")
        c = self.content.getvalue()
        f.write(codecs.encode(c, 'utf8'))
        f.flush()
        f.close()

    def args(self, outtype):
        std_args = ["", self.filename + ".html", outtype]

        if self.author != None:
            std_args += ["--authors", self.author]

        if self.cover != None:
            std_args += ["--cover", self.cover]
        return std_args

    def convert(self):
        # Prioritize low resource usage over speediness
        for format in self.formats:
            pid = os.fork()
            if pid == 0:
                os.execvp("ebook-convert", self.args(".%s" % format))
                return
            os.waitpid(pid, 0)

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
        formats = args.formats.split(",")
    elif args.epub and args.mobi:
        pass  # default
    elif args.epub:
        formats = ["epub"]
    elif args.mobi:
        formats = ["mobi"]
    if not args.stories:
        sys.stderr.write("Usage: %s [story id|url]\n")
        exit(1)
    for story in args.stories:
        munger = FFNetMunger(
                story,
                formats=formats,
                clean=args.clean,
                mote_it_not=not args.somoteitbe,
                pretty=not args.raw)
        munger.process()

if __name__ == "__main__":
    main()
