import importlib.util, pathlib, unittest
s=importlib.util.spec_from_file_location('news',pathlib.Path(__file__).resolve().parents[1]/'tools/sync_news.py');n=importlib.util.module_from_spec(s);s.loader.exec_module(n)
class Tests(unittest.TestCase):
 def clean(self,s):
  c=n.Cleaner();c.feed(s);c.close();return c,c.result()
 def test_script(self):
  _,s=self.clean('<p onclick="alert(1)">ok<script>alert(1)</script></p>');self.assertEqual(s,'<p>ok</p>')
 def test_links(self):
  _,s=self.clean('<a href="javascript:alert(1)">x</a>');self.assertNotIn('javascript',s)
 def test_iframe(self):
  c,s=self.clean('<iframe src="https://evil.test">x</iframe><p>y</p>');self.assertEqual(s,'<p>y</p>');self.assertIn('iframe',c.unsupported)
 def test_images(self):
  c,s=self.clean('<img src="https://webusstatic.yo-star.com/x.png" onerror="x()" srcset="x">');self.assertEqual(len(c.images),1);self.assertNotIn('onerror',s);self.assertNotIn('srcset',s)
 def test_download_scope(self):
  for u in ['https://evil.test/x','http://arknights.jp/x','https://arknights.jp@evil.test/x','https://arknights.jp:8888/x']:
   with self.assertRaises(ValueError):n.allowed_url(u)
 def test_reject_html_image(self):
  with self.assertRaises(ValueError):n.image_type(b'<html>error</html>')
 def test_schema(self):
  with self.assertRaises(ValueError):n.validate({'code':3,'data':{'rows':[],'count':0}})
 def test_article(self):
  a=n.transform({'id':1,'publishTime':123456,'title':'A','content':'<p>hello</p>','type':'イベント'});self.assertEqual(a['bodyHtml'],'<p>hello</p>');self.assertEqual(a['url'],'https://arknights.jp/news/1')
if __name__=='__main__':unittest.main()
