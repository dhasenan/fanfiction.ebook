#!/usr/bin/env python
from pycurl import *
from StringIO import StringIO
import io
import os
import re
import sys

TARGET="http://www.fanfiction.net/s/5782108/%s/Harry_Potter_and_the_Methods_of_Rationality"

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

def title(c):
	a, b, kernel = c.partition("<title>")
	kernel, a, b = kernel.partition("</title>")
	a, b, kernel = kernel.partition("Rationality ")
	kernel, a, b = kernel.rpartition(",")
	print kernel
	return kernel

def download(chapter):
	print "retrieving chapter %s" % chapter
	b = StringIO()
	c = Curl()
	c.setopt(URL, TARGET % chapter)
	c.setopt(WRITEFUNCTION, b.write)
	c.perform()
	c.close()
	return b.getvalue()

def retrieve():
	chapters = []
	titles = []

	first = download(1)
	count = find_count(first)
	chapters.append(first)
	titles.append('')

	# grab the items:
	for i in range(2, count + 1):
		chapters.append(download(i))
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
		<title>Harry Potter and the Methods of Rationality</title>
	</head>
	<body>
""")
	for i in range(len(chapters)):
		contents.write("<h1>" + titles[i] + "</h1>\n<div>" + chapters[i] + "</div>\n")

	contents.write("</body></html>")

	return contents

def write(contents):
	f = io.open("rationality.html", "w", encoding = "utf-8")
	f.write(unicode(contents.getvalue(), errors = "replace"))
	f.flush()
	f.close()

def convert():
	pid1 = os.fork()
	if pid1 == 0:
		os.execlp("ebook-convert", "/usr/bin/ebook-convert", "rationality.html", ".epub", "--cover", "methods_of_rationality_cover.jpg", "--authors", "Less Wrong")

	pid2 = os.fork()
	if pid2 == 0:
		os.execlp("ebook-convert", "/usr/bin/ebook-convert", "rationality.html", ".mobi", "--cover", "methods_of_rationality_cover.jpg", "--authors", "Less Wrong")

	os.waitpid(pid1, 0)
	os.waitpid(pid2, 0)

def post():
	pass
#    print "posting mobi..."
#    os.execlp("scp", "rationality.mobi", "ikeran.org:ikeran.org/")
#    print "posting epub..."
#    os.execlp("scp", "rationality.epub", "ikeran.org:ikeran.org/")
#    print "done"

grab = True
if len(sys.argv) > 1:
	if sys.argv[1] == "-c" or sys.argv[1] == "--convert-only":
		grab = False
if grab:
	write(retrieve())
convert()
post()
