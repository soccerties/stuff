#!/usr/bin/env python3

#The MIT License (MIT)
#
#Copyright (c) 2015 Joel Donahue
#
#Permission is hereby granted, free of charge, to any person obtaining a copy
#of this software and associated documentation files (the "Software"), to deal
#in the Software without restriction, including without limitation the rights
#to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#copies of the Software, and to permit persons to whom the Software is
#furnished to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be included in all
#copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#SOFTWARE.

import sys, re, time, os, random, smtplib, argparse, json, logging, logging.handlers
from datetime import date
import requests as r
from bs4 import BeautifulSoup as bs
from random import randrange
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

arg_parser = argparse.ArgumentParser(description="This script searches craigslist and can send posts that contain certain keywords to your gmail address.")

arg_parser.add_argument('-f', '--fast', help='do NOT delay http requests', default=False, action='store_true')
arg_parser.add_argument('-e', '--email', help='send email of results', default=False, action='store_true')
arg_parser.add_argument('-g', '--gmail', help='gmail address')
arg_parser.add_argument('-p', '--password', help='gmail password')
arg_parser.add_argument('-m', '--max', help='maximum results to process on each page', default=15, type=int)
arg_parser.add_argument('-v', '--verbose', help='verbose output', action='store_true')
args = arg_parser.parse_args()

if args.email \
    and (args.gmail is None \
        or args.password is None):
    arg_parser.error('Gmail address and password arguments must be used to send email.')


# Craigslist hostnames to search
site_roots = ["http://denver.craigslist.org",
              "http://fortcollins.craigslist.org",
              "http://cosprings.craigslist.org",
              "http://boulder.craigslist.org"]
# pages to check on each hostname defined above
pages = ["cpg","web","tch","sad","sof","eng"]
# used when concatenating site_roots and pages
url_prefix = '/search/'

##### Change these to your liking #####
# keywords are defined as string literals in regex form
keyword_regex = r'mysql|database|ETL|aws|ec2|s3| rds |automate|devops|linux|php|python|web developer|web dev'
title_blacklist_regex = r'java|junior|jr|entry level|oracle|ruby|manager'
keyword_blacklist_regex = r'equity|entry level|pro bono|.net|helpdesk|java'

# add multiple user agents to avoid detection by craigslist scraper blocking
user_agents = ['Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; WOW64; Trident/6.0)']
headers = {'User-Agent': random.choice(user_agents)}

# used to validate URL built from links in HTML
url_regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
        r'localhost|' #localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

if args.verbose:
    log_level = logging.DEBUG
else:
    log_level = logging.INFO

logger = logging.getLogger()
logger.setLevel(log_level)
o_h = logging.StreamHandler(sys.stdout)
logger.addHandler(o_h)

def delayer():
    delay = randrange(2,4) if not args.fast else 0
    time.sleep(delay)

def email_post(p):
    logger.debug("sending email for {}".format(p.title))

    html = "<html><body>"\
           +"<h3>"\
            +"<a href='"+p.url+"'>"+p.date_posted+"</a>"\
           +"</h3>"\
           +p.description_html\
           +"</body></html>"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = p.title
    msg['From'] = args.gmail
    msg['To'] = args.gmail

    html_msg = MIMEText(html, 'html')
    msg.attach(html_msg)

    s = smtplib.SMTP('smtp.gmail.com:587')
    s.starttls()
    s.login(args.gmail,args.password)
    s.sendmail(args.gmail, args.gmail, msg.as_string())
    s.quit()

class cl_post():
    def __init__(self, post_url):
        post = r.get(post_url, headers=headers)
        self.p = bs(post.content, "html.parser")
        setattr(self, 'url', post_url)

    @property
    def id(self):
        id = 'unkown'
        for e in self.p.find('div', {'class':'postinginfos'}).find_all('p'):
            if 'post id' in e.text:
                id = re.sub("\D","", e.text)
        return id

    @property
    def date_posted(self):
        date = 'unkown'
        post_info = self.p.find('div', {'class':'postinginfos'})
        if post_info is not None:
            for e in post_info.find_all('p'):
                if 'posted' in e.text:
                    date = e.time.text
        return date if date is not None else ''

    @property
    def description(self):
        description = self.p.find('section',{"id":"postingbody"})
        return description.text if description is not None else ''

    @property
    def description_html(self):
        html = self.p.find('section',{"id":"postingbody"})
        return html.prettify() if html is not None else ''

    @property
    def title(self):
        title = self.p.find('span',{'class','postingtitletext'})
        return title.text if title is not None else ''

    @property
    def is_interesting(self):
        title_blacklist = re.search(title_blacklist_regex, self.title, re.IGNORECASE)
        keyword_match = re.search(keyword_regex, self.description, re.IGNORECASE)
        keyword_blacklist = re.search(keyword_blacklist_regex, self.description, re.IGNORECASE)
        if keyword_match is not None \
          and title_blacklist is None \
          and keyword_blacklist is None:
            return True
        return False

for site_root in site_roots:
    for page in pages:
        full_url = site_root+url_prefix+page
        logger.debug('checking {}'.format(full_url))
        result = r.get(full_url, headers=headers)
        if result.status_code == 200:
            delayer()
            s = bs(result.content)
            counter = 0
            for row in s.find_all('p',{"class":"row"}):
                counter += 1
                post_link = row.a.get('href')
                url = site_root+post_link
                good_url = url_regex.match(url)
                if good_url is None:
                    logger.error("bad URL: {}".format(url))
                    continue
                logger.info(url)
                p = cl_post(url)
                if p.is_interesting:
                    logger.info(full_url)
                    logger.info("++++ {}".format(p.title))
                    if args.email:
                        email_post(p)
                else:
                    logger.debug("---- {}".format(p.title))
                logger.info("-")
                delayer()
                if (counter > args.max):
                    break
        else:
            logger.warn("Error: {}".format(result.status_code))