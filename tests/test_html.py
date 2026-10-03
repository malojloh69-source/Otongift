"""Check that the Python app serves HTML and every referenced site resource."""
from pathlib import Path
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from urllib.parse import urljoin,quote
from urllib.request import urlopen
import json
import tempfile
import threading
import unittest
from main import Game, handler_for
ROOT=Path(__file__).resolve().parents[1]

class Resources(HTMLParser):
    def __init__(self):super().__init__();self.urls=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='script' and attrs.get('src'):self.urls.append(attrs['src'])
        if tag=='link' and attrs.get('rel')=='stylesheet':self.urls.append(attrs['href'])

class HtmlTests(unittest.TestCase):
    def test_app_server_serves_every_required_resource(self):
        self.temp = tempfile.TemporaryDirectory()
        server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(Game(database=Path(self.temp.name)/'game.sqlite3',demo=True)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            page=f'http://127.0.0.1:{server.server_port}/'
            with urlopen(page) as response:html=response.read().decode()
            parser=Resources();parser.feed(html);self.assertGreater(len(parser.urls),5)
            for resource in parser.urls:
                with self.subTest(resource=resource):
                    self.assertTrue(resource.startswith('./'))
                    with urlopen(urljoin(page,resource)) as response:self.assertEqual(response.status,200);self.assertTrue(response.read())
            with urlopen(urljoin(page,'catalog.json')) as response:catalog=json.load(response)
            for item in catalog['gifts']+catalog['cases']:
                with urlopen(quote(urljoin(page,item['image']),safe=':/')) as response:self.assertEqual(response.status,200);self.assertTrue(response.read())
            model=catalog['collections'][0]['models'][0]
            with urlopen(urljoin(page,model['image'])) as response:
                self.assertEqual(response.headers.get_content_type(),'image/webp')
                self.assertEqual(response.read(4),b'RIFF')
            with urlopen(urljoin(page,model['animation'].replace('.tgs','.asset.js'))) as response:
                self.assertEqual(response.status,200)
                self.assertIn(b'asset',response.read().lower())
        finally:server.shutdown();server.server_close();self.temp.cleanup()
    def test_standalone_has_no_required_external_files(self):
        html=(ROOT/'index.html').read_text();parser=Resources();parser.feed(html)
        self.assertEqual(parser.urls,[]);self.assertNotIn('@import',html)
        self.assertIn('data:image/webp;base64,',html);self.assertIn('"standalone":true',html)

if __name__=='__main__':unittest.main()
