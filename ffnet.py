#!/usr/bin/env python
from pycurl import *
from StringIO import StringIO
import urllib2
import datetime
import io
import os
import re
import string
import sys

TARGET="http://www.fanfiction.net/s/%s/%s/"

class FFNetMunger:
    def __init__(self, story_id, marker):
        self.story_id = story_id
        self.div_re = re.compile('<div.*?</div>', re.DOTALL)
        self.marker = marker
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
        return kernel

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
        return urllib2.urlopen(TARGET % (self.story_id, chapter)).read()

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
            chapters[i] = self.guts(c)
            titles[i] = self.title(c)
            print titles[i]

        # jam it into one string, with appropriate header and footer:
        contents = StringIO()
        contents.write("""<html>
        <head>
            <title>%s</title>
        </head>
        <body>
    """ % name)
        for i in range(len(chapters)):
            contents.write("<h1>" + titles[i] + "</h1>\n<div>" + chapters[i] + "</div>\n")

        contents.write("</body></html>")

        return contents, name

    def write(self):
        self.write_to(self.filename)
        now = datetime.datetime.now()
        date = now.strftime("%Y-%m-%d")
        self.write_to("%s-%s" % (self.filename, date))

    def write_to(self, filename):
        print 'writing story to %s.html' % filename
        f = io.open(filename + ".html", "wb")
        f.write(self.content.getvalue())
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
        pid1 = os.fork()
        if pid1 == 0:
            os.execvp("ebook-convert", self.args(".epub"))
            return
        os.waitpid(pid1, 0)

        pid2 = os.fork()
        if pid2 == 0:
            os.execvp("ebook-convert", self.args(".mobi"))
            return
        os.waitpid(pid2, 0)

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.stderr.write("Usage: %s STORY_ID")
        exit(1)
    munger = FFNetMunger(sys.argv[1], None)
    munger.process()
