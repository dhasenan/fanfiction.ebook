#!/usr/bin/env python
from pycurl import *
from StringIO import StringIO
import urllib2
import io
import os
import re
import sys

TARGET="http://www.fanfiction.net/s/%s/%s/"

def find_count(c):
	count = 0
	a, b, kernel = c.partition("SELECT title='chapter navigation'")
	kernel, a, b = kernel.partition("</select>")
	f = re.compile("option\\s*value=([0-9]*)")
	for match in f.finditer(kernel):
		g, = match.groups(1)
		current = int(g)
		if count < current:
			count = current
	print "total of %s chapters" % count
	return count


def guts(c):
	kernel = re.split("<div[^>]*class=storytext\\b.*?>", c, 1)[1]
	while True:
		kernel, n = re.subn('<div.*?</div>', '', kernel, flags=re.DOTALL)
		if n == 0:
			break
	kernel, a, b = kernel.partition("</div>")
	return kernel

def get_name(chapter):
	a, b, kernel = chapter.partition("<title>")
	kernel, a, b = kernel.partition("Chapter")
	return kernel.strip()

def title(c):
	a, b, kernel = c.partition("<title>")
	kernel, a, b = kernel.partition("</title>")
	a, b, kernel = kernel.partition("Rationality ")
	kernel, a, b = kernel.partition(", a Harry Potter")
	return kernel

def download(id, chapter):
	print "retrieving chapter %s" % chapter
	return urllib2.urlopen(TARGET % (id, chapter)).read()
#	b = StringIO()
#	c = Curl()
#	c.setopt(URL, TARGET % (id, chapter))
#	c.setopt(WRITEFUNCTION, b.write)
#	c.perform()
#	c.close()
#	return b.getvalue()

def retrieve(id):
	chapters = []
	titles = []

	first = download(id, 1)
	count = find_count(first)
	name = get_name(first)
	chapters.append(first)
	titles.append('')

	# grab the items:
	for i in range(2, count + 1):
		chapters.append(download(id, i))
		titles.append('')


	# extract the essential bits from each chapter:
	for i in range(len(chapters)):
		print "munging chapter %s" % (i + 1)
		c = chapters[i]
		chapters[i] = guts(c)
		titles[i] = title(c)

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

def write(contents, name):
	f = io.open(name + ".html", "wb")
	f.write(contents.getvalue())
	f.flush()
	f.close()
	return name

def convert(name):
	pid1 = os.fork()
	if pid1 == 0:
		os.execlp("ebook-convert", "/usr/bin/ebook-convert", name + ".html", ".epub")

	pid2 = os.fork()
	if pid2 == 0:
		os.execlp("ebook-convert", "/usr/bin/ebook-convert", name + ".html", ".mobi")

	os.waitpid(pid1, 0)
	os.waitpid(pid2, 0)

def post():
	pass
#    print "posting mobi..."
#    os.execlp("scp", "rationality.mobi", "ikeran.org:ikeran.org/")
#    print "posting epub..."
#    os.execlp("scp", "rationality.epub", "ikeran.org:ikeran.org/")
#    print "done"

if len(sys.argv) == 1:
	print "Usage: %s STORY_ID"
	exit(1)


content, name = retrieve(sys.argv[1])
write(content, name)
convert(name)
post()
