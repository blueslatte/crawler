import requests
from lxml import etree
from threading import Thread
from queue import Queue
import time
import redis
import re
from bs4 import BeautifulSoup
import tqdm
import os


pool = redis.ConnectionPool(host='localhost', port=6379, db=3,password="1234")
redis = redis.StrictRedis(connection_pool=pool)

class get_lzlqc_page():

    def __init__(self):
        # self.base_url = "http://10.10.2.16/"
        self.index_urls = set()
        self.two_index_urls = set()
        self.url_title = {}
        self.base_url = 'http://www.lzlqc.com/'

    
    def get_head_index_url(self):
        url = self.base_url
        response = requests.get(url)
        html = response.text
        page = etree.HTML(html)

        contents = page.xpath('//a[contains(@href,"Category_")]/@href')

        for i in contents:
            self.index_urls.add(i)

    def get_two_index_url(self):
        for i in self.index_urls:
            url = self.base_url + i
            response = requests.get(url)
            html = response.text
            page = etree.HTML(html)

            contents = page.xpath('//a[contains(@href,"Category_")]/@href')
            for i in contents:
                self.two_index_urls.add(i)
        self.index_urls |= self.two_index_urls

    def get_all_url_title_redis(self):
        for i in self.index_urls:
            url = self.base_url[:-1] + i
            try:
                response = requests.get(url, timeout=5)
                time.sleep(0.5)
                html = response.text
                page = etree.HTML(html)
                title = page.xpath('//em/a/text()')
                redis.hset("url_title",url, str(title))
                print(url, 'over ')

            except Exception as e:
                print(e)
                print("{}  get wrong!".format(url))

    def get_all_url_from_redis_set(self):
        urls = redis.hkeys("url_title")
        for i in urls:
            if len(redis.hget("url_title", i)) != 2:
                redis.hset("can_use_urls", i.decode("utf8"), redis.hget("url_title", i))
                print("set {} ok!".format(i.decode("utf8")))

    def get_all_split_url_to_redis(self):
        all_page_num = 0
        for i in redis.hkeys("can_use_urls"):
            all_page_num += 1
            head_url = i.decode('utf8')
            print(head_url)
            base_url = head_url[:len(head_url) - len('Index.aspx')]
            modol_url = base_url + "Index_{}" + ".aspx"
            response = requests.get(head_url, timeout=5)
            time.sleep(0.5)
            html = response.text
            page = etree.HTML(html)
            url_details = page.xpath('//span[@class="disabled"]/text()')
            if not url_details:
                continue
            max_page = re.search("/共(.*?)页", str(url_details)).group(1)
            urls = [head_url]
            for i in range(2, int(max_page) + 1):
                urls.append(modol_url.format(i))
                all_page_num +=1
            redis.hset("all_urls", head_url, str(urls))
        print("all page :{}".format(all_page_num))

    def get_all_pag_url_to_redis(self):
        values = redis.hkeys("all_urls")
        urls = set()
        page_num = 0
        urls_num = 0
        for url in values:
            url = url.decode("utf8")
            split_urls = redis.hget("all_urls", url).decode("utf8")
            for i in eval(split_urls):
                try:
                    response = requests.get(i, timeout=5)
                    time.sleep(0.5)
                    html = response.text
                    page = etree.HTML(html)
                    page_urls = page.xpath("//li/a[contains(@href,'Item')]/@href")
                    for page_url in page_urls:
                        urls.add(page_url)
                        print("{} add over".format(page_url))
                        urls_num +=1
                    print("{} already get all url".format(i))

                except Exception as e:
                    print(e)
                    print(i)
                    print(url)
                    continue
                page_num += 1

        print("{} page get!".format(page_num))
        print("{} url get!".format(urls_num))
        url_s = ''
        for i in urls:
            url_s +=','+i
            print(i)
        redis.hset('all_splite_url', str(urls), url_s)

    def get_all_conten(self):
        urls = redis.hvals("all_splite_url")
        urls = urls[0].decode('utf8').split(',')
        base_url = 'http://www.lzlqc.com'
        all_page = 0
        get_page = 0
        for ur in tqdm.tqdm(urls):
            url = base_url+ur
            try:
                response = requests.get(url, timeout=5)
                time.sleep(0.5)
                html = response.text
                page = etree.HTML(html)
                path = page.xpath('//em/a/text()|//em/text()')
                clict_num = 0
                path_s = '\\'
                path_s += ''.join([i + '\\' for i in path])
                soup = BeautifulSoup(html, "html.parser")
                title = soup.find(name='div', attrs={'class': "article_infoTitle"}).find(name='span').find(
                    name='font').string
                author = soup.find(name='div', attrs={'class': 'article_info'}).find(
                    name='span').find(name='font')
                author = str(author)
                release_time = re.search('发布时间：(.*?日)', author).group(1)
                author = re.search('>(.*?点击数:)', author).group(1)
                content = soup.find(name='div', attrs='article_content_list')
                content = re.sub('<[^>]+>', '', str(content))
                clict = requests.get(
                    base_url + page.xpath('//div[@class="article_info"]/span/font/script/@src')[0]).text
                clict_num = re.findall("'(.*?)'", clict)[0]
                author += clict_num
                abspath = os.getcwd()
                abspath_s = abspath +'\gets'+ path_s
                # print(abspath_s[:-1])
                if os.path.isdir(abspath_s[:-1]):
                    pass
                    # print(abspath_s[:-1])
                else:
                    os.makedirs(abspath_s[:-1])
                # print(path_s)
                file_name = release_time + '-----' + title
                with open(abspath_s + file_name + '.txt', 'a', encoding='utf8') as p:
                    p.write(title + "\n")
                    p.write(author)
                    p.write(content)
                    p.write("Chang Time：{}".format(time.asctime()))
                redis.hset("contents", str(url), title+author+content)
                get_page += 1
                # print(abspath_s + title)
            except Exception as e:
                print(e)
                print("url :{} get some wrong!!!!!!!!".format(url))
                with open("wrong.txt",'a',encoding='utf8') as P:
                    P.write(url+"\n")
                all_page += 1
                continue
        print("{} all page num".format(all_page))
        print("{} get page num".format(get_page))

    def run(self):
        self.get_head_index_url()
        self.get_two_index_url()
        self.get_all_url_title_redis()
        self.get_all_url_from_redis_set()
        self.get_all_split_url_to_redis()




get_url = get_lzlqc_page()

get_url.get_all_conten()