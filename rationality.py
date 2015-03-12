#!/usr/bin/env python
from ffnet import *

munger = Munger(
  "https://www.fanfiction.net/s/5782108/1/Harry-Potter-and-the-Methods-of-Rationality",
  FFNetAdapter(),
  afternote=u'Problems with the ebook? Contact dhasenan@gmail.com.',
  filename="rationality")
munger.cover = "methods_of_rationality_cover.jpg"
story = munger.DownloadStory()
if len(story.chapters) < 100:
  raise Exception('Too few chapters detected; aborting')
story.author = "Eliezer Yudkowsky"
story.cover = "methods_of_rationality_cover.jpg"
munger.CreateEbook(story)

