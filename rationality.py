#!/usr/bin/env python
from ffnet import *

munger = FFNetMunger(5782108)
munger.filename = "rationality"
munger.author = "Eliezer Yudkowsky"
munger.cover = "methods_of_rationality_cover.jpg"
munger.process()
