"""Regression checks for the nested HTML preview shown in the reported screenshot."""
from pathlib import Path
from html.parser import HTMLParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin,quote
from urllib.request import urlopen
import json
import threading
import unittest
ROOT=Path(__file__).resolve().parents[1]

class Resources(HTMLParser):
    def __init__(self):super().__init__();self.urls=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='script' and attrs.get('src'):self.urls.append(attrs['src'])
        if tag=='link' and attrs.get('rel')=='stylesheet':self.urls.append(attrs['href'])

class HtmlTests(unittest.TestCase):
    def test_nested_preview_serves_every_required_resource(self):
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self,*args,**kwargs):super().__init__(*args,directory=ROOT.parent,**kwargs)
            def log_message(self,*args):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            page=f'http://127.0.0.1:{server.server_port}/{ROOT.name}/dist/index.html'
            with urlopen(page) as response:html=response.read().decode()
            parser=Resources();parser.feed(html);self.assertGreater(len(parser.urls),5)
            for resource in parser.urls:
                with self.subTest(resource=resource):
                    self.assertTrue(resource.startswith('./'))
                    with urlopen(urljoin(page,resource)) as response:self.assertEqual(response.status,200);self.assertTrue(response.read())
            with urlopen(urljoin(page,'catalog.json')) as response:catalog=json.load(response)
            for item in catalog['gifts']+catalog['cases']:
                with urlopen(quote(urljoin(page,item['image']),safe=':/')) as response:self.assertEqual(response.status,200);self.assertTrue(response.read())
        finally:server.shutdown();server.server_close()
    def test_standalone_has_no_required_external_files(self):
        html=(ROOT/'index.html').read_text();parser=Resources();parser.feed(html)
        self.assertEqual(parser.urls,[]);self.assertNotIn('@import',html)
        self.assertIn('data:image/webp;base64,',html);self.assertIn('"standalone":true',html)

if __name__=='__main__':unittest.main()
