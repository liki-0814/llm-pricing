"""Static opaque-color/state contract only; NOT browser/Lighthouse acceptance."""
import pathlib,re,unittest
CSS=(pathlib.Path(__file__).resolve().parents[1]/'assets/style.css').read_text()
def rule(selector):
 m=re.search(r'(?:^|\n)'+re.escape(selector)+r'\{([^}]+)\}',CSS)
 if not m:raise ValueError('missing selector '+selector)
 return dict((k.strip(),v.strip()) for k,v in re.findall(r'([\w-]+)\s*:\s*([^;]+)(?:;|$)',m[1]))
def tokens(selector):return {k:v for k,v in rule(selector).items() if k.startswith('--')}
def lum(color):
 if not isinstance(color,str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',color):raise ValueError('opaque six-digit color only; blending requires runtime or explicit composition')
 rgb=[int(color[i:i+2],16)/255 for i in (1,3,5)];rgb=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in rgb];return sum(a*b for a,b in zip(rgb,(.2126,.7152,.0722)))
def ratio(a,b):x,y=sorted((lum(a),lum(b)));return (y+.05)/(x+.05)
THEMES={'light':tokens(':root'),'dark':tokens('html[data-theme="dark"]')}
class ContrastTokens(unittest.TestCase):
 def small(self,t):
  for fg in ('--muted','--faint'):
   for bg in ('--bg','--surface','--surface-2','--surface-3','--row-hover'):
    with self.subTest(foreground=fg,background=bg):self.assertGreaterEqual(ratio(t[fg],t[bg]),4.5)
 def test_opaque_base_surfaces_both_themes(self):
  for theme,t in THEMES.items():
   with self.subTest(theme=theme):self.small(t)
 def test_light_brand_soft_opaque_only(self):
  t=THEMES['light']
  for key in ('--muted','--faint'):self.assertGreaterEqual(ratio(t[key],t['--brand-soft']),4.5)
 def test_old_light_muted_and_faint_are_real_negative_controls(self):
  self.assertLess(ratio('#64748b',THEMES['light']['--surface-3']),4.5);self.assertLess(ratio('#94a3b8',THEMES['light']['--surface']),4.5)
 def test_old_dark_faint_is_negative_control(self):self.assertLess(ratio('#5f677a',THEMES['dark']['--surface-3']),4.5)
 def test_tab_selector_semantics_not_flattened(self):
  self.assertEqual(rule('.modality-tabs .tab')['color'],'var(--muted)');self.assertEqual(rule('.modality-tabs .tab:hover')['color'],'var(--ink)');self.assertEqual(rule('.modality-tabs .tab[aria-selected="true"]')['color'],'var(--ink)');self.assertEqual(rule('.modality-tabs .tab .n')['color'],'var(--faint)')
 def test_tabs_static_selected_hover_focus_matrix(self):
  for theme,t in THEMES.items():
   for selected in (False,True):
    for hover in (False,True):
     for focus in (False,True):
      with self.subTest(theme=theme,selected=selected,hover=hover,focus=focus):
       bg=t['--surface' if selected else '--surface-2'];fg=t['--ink' if selected or hover else '--muted'];self.assertGreaterEqual(ratio(fg,bg),4.5);self.assertGreaterEqual(ratio(t['--faint'],bg),4.5)
       if focus:self.assertGreaterEqual(ratio(t['--brand'],bg),3)
 def test_chip_ordinary_and_selected_text_semantics(self):
  self.assertEqual(rule('.chip')['background'],'var(--surface-2)');self.assertEqual(rule('.chip .n')['color'],'var(--faint)');self.assertEqual(rule('.chip[aria-pressed="true"] .n')['color'],'var(--ink-2)')
  for t in THEMES.values():
   for fg in ('--ink-2','--faint'):self.assertGreaterEqual(ratio(t[fg],t['--surface-2']),4.5)
 def test_table_row_hover_currency_na_dates_and_detail(self):
  self.assertEqual(rule('tbody tr:hover')['background'],'var(--row-hover)')
  for selector in ('.price .cur','.na','.src .date'):self.assertEqual(rule(selector)['color'],'var(--faint)')
  self.assertEqual(rule('.dblock')['background'],'var(--surface-2)');self.assertEqual(rule('.dblock h3')['color'],'var(--muted)');self.assertEqual(rule('.dnote')['color'],'var(--muted)')
  for t in THEMES.values():
   for bg in ('--surface','--row-hover','--surface-2','--surface-3'):
    for fg in ('--faint','--muted','--ink-2'):self.assertGreaterEqual(ratio(t[fg],t[bg]),4.5)
 def test_opaque_tab_and_detail_focus_ring_contract(self):
  for selector in (':focus-visible','.modality-tabs .tab:focus-visible','.detail-btn:focus-visible'):
   self.assertEqual(rule(selector)['outline'],'2px solid var(--brand)');self.assertRegex(rule(selector)['outline-offset'],r'^[12]px$')
  for t in THEMES.values():
   for bg in ('--surface','--surface-2','--surface-3'):self.assertGreaterEqual(ratio(t['--brand'],t[bg]),3)
  self.assertNotIn('overflow',rule('.modality-tabs'))
 def test_blended_and_gradient_states_are_explicitly_not_covered(self):
  self.assertIn('color-mix',rule('.chip[aria-pressed="true"]')['background']);self.assertIn('rgba',THEMES['dark']['--brand-soft']);self.assertIn('transparent',rule('.input:focus')['box-shadow'])
  for color in ('rgba(129,140,248,.14)','color-mix(in srgb,red 13%,white)','linear-gradient(red,white)',None,[],'#fff'):
   with self.assertRaises(ValueError):lum(color)
if __name__=='__main__':unittest.main()
