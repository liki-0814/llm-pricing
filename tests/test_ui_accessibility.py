"""Source-backed CSS composition + HTML semantics; NOT browser/a11y acceptance."""
import pathlib,re,unittest
from html.parser import HTMLParser
ROOT=pathlib.Path(__file__).resolve().parents[1]

def split_args(value):
 result=[];depth=0;start=0
 for i,ch in enumerate(value):
  depth+= (ch=='(')-(ch==')')
  if ch==',' and depth==0:result.append(value[start:i].strip());start=i+1
 result.append(value[start:].strip());return result
class Styles:
 def __init__(self,text):
  self.rules={}
  text=re.sub(r'/\*.*?\*/','',text,flags=re.S)
  for m in re.finditer(r'([^{}]+)\{([^{}]*)\}',text):
   for selector in m[1].strip().split(','):
    selector=selector.strip()
    if selector.startswith('@'):continue
    props=dict((k.strip(),v.strip()) for k,v in re.findall(r'([\w-]+)\s*:\s*([^;]+)(?:;|$)',m[2]))
    self.rules.setdefault(selector,{}).update(props)
 def color(self,value,variables):
  value=value.strip()
  if value.startswith('var(') and value.endswith(')'):
   args=split_args(value[4:-1]);return self.color(variables.get(args[0],args[1] if len(args)>1 else ''),variables)
  if re.fullmatch(r'#[0-9a-fA-F]{6}',value):return tuple(int(value[i:i+2],16)/255 for i in (1,3,5))+(1.,)
  if value=='transparent':return (0.,0.,0.,0.)
  if value.startswith('color-mix('):
   space,left,right=split_args(value[10:-1])
   if space!='in srgb':raise ValueError('unsupported color space')
   m=re.fullmatch(r'(.*) (\d+(?:\.\d+)?)%',left)
   if not m:raise ValueError('explicit mix weight required')
   weight=float(m[2])/100;a=self.color(m[1],variables);b=self.color(right,variables);alpha=a[3]*weight+b[3]*(1-weight)
   return tuple((a[i]*a[3]*weight+b[i]*b[3]*(1-weight))/alpha if alpha else 0 for i in range(3))+(alpha,)
  raise ValueError('unhandled CSS color '+value)
 def matrix(self,include_fallback=True):
  results=[]
  slugs={x.split('.v-')[-1] for x in self.rules if '--vc' in self.rules[x]}
  if include_fallback:slugs.add('fallback')
  for theme in ['light','dark']:
   base=dict(self.rules[':root'])
   if theme=='dark':base.update(self.rules['html[data-theme="dark"]'])
   for slug in sorted(slugs):
    variables=dict(base);variables.update(self.rules.get('.v-'+slug,{}))
    if theme=='dark':variables.update(self.rules.get('html[data-theme="dark"] .v-'+slug,{}))
    for context,background in [('table',self.rules['.table-card']['background']),('row-hover',self.rules['tbody tr:hover']['background']),('footer',self.rules['.site-footer']['background'])]:
     parent=self.color(background,variables);bg=over(self.color(self.rules['.badge']['background'],variables),parent);fg=over(self.color(self.rules['.badge']['color'],variables),bg)
     results.append((theme,slug,context,contrast(fg,bg)))
  return results

def over(a,b):
 alpha=a[3]+b[3]*(1-a[3]);return tuple((a[i]*a[3]+b[i]*b[3]*(1-a[3]))/alpha for i in range(3))+(alpha,)
def contrast(a,b):
 def luminance(c):return sum(w*(x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4) for w,x in zip((.2126,.7152,.0722),c[:3]))
 x,y=sorted((luminance(a),luminance(b)));return (y+.05)/(x+.05)
class Headings(HTMLParser):
 def __init__(self):super().__init__();self.levels=[];self.bad_links=[]
 def handle_starttag(self,tag,attrs):
  if re.fullmatch('h[1-6]',tag):self.levels.append(int(tag[1]))

class AccessibilitySource(unittest.TestCase):
 def setUp(self):self.css=(ROOT/'assets/style.css').read_text();self.styles=Styles(self.css)
 def test_badge_composition_all_vendors_fallback_themes_and_actual_surfaces(self):
  for theme,vendor,context,ratio in self.styles.matrix():
   with self.subTest(theme=theme,vendor=vendor,context=context):self.assertGreaterEqual(ratio,4.5)
 def test_composition_math_has_known_nonopaque_controls(self):
  self.assertEqual(over((1.,0.,0.,.5),(0.,0.,1.,1.)),(.5,0.,.5,1.))
  mixed=self.styles.color('color-mix(in srgb,#ff0000 12%,transparent)',{})
  self.assertAlmostEqual(mixed[0],1.);self.assertAlmostEqual(mixed[3],.12)
  self.assertAlmostEqual(contrast((0,0,0,1),(1,1,1,1)),21.)
 def test_old_foreground_mix_is_a_semantic_negative_control(self):
  bad=Styles(self.css);bad.rules['.badge']['color']='color-mix(in srgb,var(--vc,var(--brand)) 78%,var(--ink))'
  failures=[x for x in bad.matrix(include_fallback=False) if x[3]<4.5];self.assertTrue(any(x[1]=='qwen' and x[2]=='footer' for x in failures));self.assertTrue(any(x[1]=='google' for x in failures))
 def test_badges_have_vendor_fallback_and_no_group_opacity(self):
  for prop in ['color','background','border']:self.assertIn('var(--vc,var(--brand))',self.styles.rules['.badge'][prop])
  for selector in ['body','.site-footer','.sources','.sources li','.badge']:
   self.assertEqual(float(self.styles.rules.get(selector,{}).get('opacity','1')),1.)
 def test_inline_links_have_persistent_noncolor_cue(self):
  self.assertEqual(self.styles.rules['a']['text-decoration'],'underline');self.assertEqual(self.styles.rules['a']['text-underline-offset'],'3px')
  allowed={'.brand','.brand:hover','.nav a','.nav a:hover','.btn','.btn:hover','.icon-btn','.toc a','.toc a:hover'}
  for selector,props in self.styles.rules.items():
   if props.get('text-decoration')=='none':self.assertIn(selector,allowed)
 def test_static_pages_have_no_skipped_heading_levels_and_footer_is_top_level(self):
  for filename in ['index.html','api.html']:
   text=(ROOT/filename).read_text();p=Headings();p.feed(text);self.assertEqual(p.levels[0],1)
   for a,b in zip(p.levels,p.levels[1:]):self.assertLessEqual(b,a+1,filename)
   self.assertNotIn('<h3>',text.split('<footer class="site-footer">')[1]);self.assertIn('<h2>',text.split('<footer class="site-footer">')[1])
 def test_price_section_is_named_by_real_level_two_heading(self):
  text=(ROOT/'index.html').read_text();self.assertIn('aria-labelledby="pricesHeading"',text);self.assertRegex(text,r'<h2[^>]*id="pricesHeading"[^>]*>价格表</h2>')
 def test_detail_semantics_and_styles_change_together(self):
  app=(ROOT/'assets/app.js').read_text();self.assertIn("<h3>",app);self.assertNotIn('<h4>',app);self.assertIn('.dblock h3',self.styles.rules);self.assertIn('.site-footer h2',self.styles.rules)
