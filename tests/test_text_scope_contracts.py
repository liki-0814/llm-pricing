"""Bounded source contracts, synthetic HTML/Markdown only; never HTTP."""
import copy,json,pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import discovery_text_contracts as t

DS_SOURCE={'vendor':'DeepSeek','channel':'pay_as_you_go','role':'catalog','modalities':['text'],'url':'https://api-docs.deepseek.com/quick_start/pricing/'}
HY_SOURCE={'vendor':'腾讯混元','channel':'pay_as_you_go','role':'catalog','modalities':['text'],'url':'https://cloud.tencent.com/document/product/1823/130051'}
def ds(ids=('future-flash','future-pro')):
 models=''.join('<td>'+x+('</td>' if i else '<sup>(1)</sup></td>') for i,x in enumerate(ids))
 versions=''.join('<td>Entity-'+x+'</td>' for x in ids)
 return '<html><body><article><h1>Models &amp; Pricing</h1><h2>Model Details</h2><table><tr><td>MODEL</td>'+models+'</tr><tr><td>BASE URL (OpenAI Format)</td><td>https://api.deepseek.com</td></tr><tr><td>MODEL VERSION</td>'+versions+'</tr></table><p>(1) Use <code>'+ids[0]+'</code> as the model name. The legacy names <code>future-old</code> and <code>future-vision</code> are still accepted, but the corresponding models have been retired, their requests are served by the Entity-'+ids[0]+' model and billed at the Flash price.</p><h2>Web Search &amp; Fetch Pricing</h2><h2>File Parsing &amp; OCR Pricing</h2><h2>Speech Pricing</h2><h2>Deduction Rules</h2><p>Product prices may vary and DeepSeek reserves the right to adjust them.</p></article></body></html>'
def hy(new=''):
 table=lambda rows:'<table><tr><td>模型名称</td><td>model（调用参数）</td><td>能力支持</td></tr>'+''.join('<tr><td>'+name+'</td><td>'+mid+'</td><td>文本</td></tr>' for name,mid in rows)+'</table>'
 return '<html><body><h1>模型列表</h1><h2>本页目录：</h2><h2>语言模型</h2>'+table([('Hy4','hy4'),('DeepSeek X','deepseek/x')]+([('Hy-Future','hy-future')] if new else []))+'<h2>视觉模型</h2><h3>图像生成</h3><h3>视频生成</h3><h3>3D 生成</h3><h2>语音模型</h2><h2>多模态理解模型</h2>'+table([('HY-Vision-Future','hy-vision-future'),('YT-VITA','youtu-vita')])+'<h2>向量模型</h2><h2>能力说明</h2></body></html>'
class TextScopeContracts(unittest.TestCase):
 def test_deepseek_closed_table_aliases_not_retired_invocation(self):
  rows,p=t.deepseek_contract(ds(),DS_SOURCE);self.assertTrue(p['verified']);self.assertEqual(len(rows),4)
  aliases=[r for r in rows if r.get('alias_of')];self.assertEqual(len(aliases),2)
  self.assertTrue(all(r['alias_of']=='future-flash' and r['lifecycle_status']=='accepted_alias' and r['retired_at'] is None for r in aliases));self.assertTrue(all(r['previous_entity_retired'] for r in aliases))
 def test_deepseek_official_search_api_heading_variant_is_bounded(self):
  body=ds().replace('Web Search &amp; Fetch Pricing','Search &amp; Fetch API Pricing')
  rows,proof=t.deepseek_contract(body,DS_SOURCE);self.assertTrue(proof['verified']);self.assertEqual(len(rows),4)
  for replacement in ('Other Models','Search & Fetch Future Pricing'):
   self.assertFalse(t.deepseek_contract(body.replace('Search &amp; Fetch API Pricing',replacement),DS_SOURCE)[1]['verified'])
 def test_deepseek_future_legal_unpriced_column_is_retained(self):
  rows,p=t.deepseek_contract(ds(('future-flash','future-pro','future-unpriced-99')),DS_SOURCE);self.assertTrue(p['verified']);self.assertIn('future-unpriced-99',[r['model_id'] for r in rows])
 def test_deepseek_rejects_wrong_types_truncation_alias_drift_and_unknown_sections(self):
  for body in (None,{},[],1,True,ds()[:-20],ds().replace('MODEL VERSION','VERSION'),ds().replace('still accepted','no longer accepted'),ds().replace('Entity-future-flash model and billed','Unknown-Entity model and billed'),ds().replace('<h2>Deduction Rules','<h2>New Models</h2><h2>Deduction Rules'),ds().replace('<td>future-pro</td>','<td>Display Name</td>'),ds().replace('</table>',''),ds().replace('https://api.deepseek.com','https://outside.invalid')):
   with self.subTest(body=str(body)[:100]):self.assertFalse(t.deepseek_contract(body,DS_SOURCE)[1]['verified'])
 def test_source_identity_scope_not_self_asserted(self):
  for field,value in [('vendor','reseller'),('channel','subscription'),('url','https://outside.invalid'),('modalities',['image']),('role','price')]:
   s=copy.deepcopy(DS_SOURCE);s[field]=value;self.assertFalse(t.deepseek_contract(ds(),s)[1]['verified'])
 def test_hunyuan_all_text_sections_native_vs_tokenhub(self):
  rows,reseller,p=t.hunyuan_text_contract(hy(),HY_SOURCE);self.assertTrue(p['verified']);self.assertEqual({r['model_id'] for r in rows},{'hy4','hy-vision-future'});self.assertEqual({r['model_id'] for r in reseller},{'deepseek/x','youtu-vita'})
 def test_hunyuan_new_native_legal_id_not_whitelisted(self):
  rows,_,p=t.hunyuan_text_contract(hy('new'),HY_SOURCE);self.assertTrue(p['verified']);self.assertIn('hy-future',[r['model_id'] for r in rows])
 def test_hunyuan_unknown_origin_section_id_and_cut_fail_closed(self):
  for body in (None,{},[],True,hy()[:-15],hy().replace('能力说明','全新文本目录'),hy().replace('hy4</td>','foreign-call</td>'),hy().replace('DeepSeek X','UnknownBrand'),hy().replace('model（调用参数）','Name'),hy().replace('hy-vision-future</td>','Display Name</td>'),hy().replace('</tr>','',1),hy().replace('<h2>多模态理解模型</h2>','')):
   with self.subTest(body=str(body)[:100]):self.assertFalse(t.hunyuan_text_contract(body,HY_SOURCE)[2]['verified'])
 def test_anthropic_retirement_bridge_requires_explicit_single_entity_notice(self):
  notice='## Deprecation history\n### 2026-06-05: Claude Future model\nOn June 5, 2026, Anthropic notified developers using Claude Future of its upcoming retirement on the Claude API.\n| Retirement date | Model | Recommended replacement |\n| --- | --- | --- |\n| August 5, 2026 | `claude-future-native` | `claude-other` |\n## API parameter deprecations\n'
  row={'display_name':'Claude Future','api_id_explicit':False,'lifecycle_status':'retired','model_id':None};out=t.anthropic_retired_bridges([row],notice)
  self.assertEqual(out[0]['model_id'],'claude-future-native');self.assertTrue(out[0]['api_id_explicit']);self.assertIsNone(out[0]['retired_at'])
  self.assertEqual(t.anthropic_retired_bridges([row],notice.replace('| Model |','| Deprecated model |'))[0]['model_id'],'claude-future-native')
  for broken in (notice.replace('Claude Future of','Claude Future and Claude Other models of'),notice.replace('Model |','API-ish |'),notice.replace('`claude-future-native`','Display Model'),notice[:notice.index('## API parameter')]):self.assertFalse(t.anthropic_retired_bridges([row],broken)[0]['api_id_explicit'])
 def test_anthropic_ambiguous_group_never_guesses_id_from_slug(self):
  rows=[{'display_name':'Claude Sonnet 4','model_id':None,'api_id_explicit':False,'lifecycle_status':'retired'},{'display_name':'Claude Opus 4','model_id':None,'api_id_explicit':False,'lifecycle_status':'retired'}]
  text='## Deprecation history\n### Group models\nAnthropic notified developers using Claude Sonnet 4 and Claude Opus 4 models of their upcoming retirement on the Claude API.\n| Retirement date | Model | Recommended replacement |\n| --- | --- | --- |\n| June 15, 2026 | `claude-sonnet-4-native` | `new-sonnet` |\n| June 15, 2026 | `claude-opus-4-native` | `new-opus` |\n## API parameter deprecations\n'
  self.assertTrue(all(not r['api_id_explicit'] for r in t.anthropic_retired_bridges(rows,text)))
 def test_hidden_additional_routes_sections_footnotes_and_pagination_fail_closed(self):
  ds_bad=[ds().replace('</article>',''),ds().replace('<h2>Deduction Rules','<h3>Additional models</h3><h2>Deduction Rules'),ds().replace('<h2>Web Search','<p>(4) An additional model <code>future-hidden</code> is accepted.</p><h2>Web Search'),ds().replace('</body>','<a href="?page=2">More</a></body>'),ds().replace('<h2>Deduction Rules','<table><tr><td>MODEL</td><td>hidden-model</td></tr></table><h2>Deduction Rules')]
  for body in ds_bad:
   with self.subTest(vendor='DeepSeek',body=body[-100:]):self.assertFalse(t.deepseek_contract(body,DS_SOURCE)[1]['verified'])
  hy_bad=[hy().replace('<h2>能力说明','<h3>New text family</h3><h2>能力说明'),hy().replace('</body>','<a rel="next" href="/models?page=2">More</a></body>'),hy().replace('<h2>能力说明</h2>','<h2>能力说明</h2><table><tr><td>model（调用参数）</td></tr><tr><td>hy-hidden</td></tr></table>')]
  for body in hy_bad:
   with self.subTest(vendor='Hunyuan',body=body[-100:]):self.assertFalse(t.hunyuan_text_contract(body,HY_SOURCE)[2]['verified'])
 def test_unknown_table_rows_unbound_footnotes_and_after_html_content_reject(self):
  for body in (ds()+'<p>Unreviewed model continuation</p>',ds().replace('</table>','<tr><td>MODEL</td><td>hidden</td></tr></table>',1),ds().replace('</table>','<tr><td>NEW MODEL LIST</td><td>hidden</td></tr></table>',1),ds().replace('<sup>(1)</sup>','<sup>(9)</sup>')):
   with self.subTest(body=body[-100:]):self.assertFalse(t.deepseek_contract(body,DS_SOURCE)[1]['verified'])
  self.assertFalse(t.hunyuan_text_contract(hy()+'<p>Unreviewed tail</p>',HY_SOURCE)[2]['verified'])
 def test_runner_applies_proofs_and_keeps_alias_lifecycle(self):
  import run_discovery as runner
  source=dict(DS_SOURCE,adapter='deepseek_model_row')
  snap=runner.parse_source(ds().encode(),source,'2026-11-18T04:00:00Z');self.assertTrue(snap['complete']);self.assertEqual(snap['coverage_evidence']['expected_record_count'],len(snap['records']));self.assertEqual(len([row for row in snap['records'] if row.get('lifecycle_status')=='accepted_alias']),2)
  source=dict(HY_SOURCE,adapter='hunyuan_invocation_tables')
  snap=runner.parse_source(hy().encode(),source,'2026-11-18T04:00:00Z');self.assertTrue(snap['complete']);self.assertTrue(all(row['text_scope_member'] for row in snap['records']));self.assertEqual(len(snap['reseller_records']),2)
  source=dict(HY_SOURCE,adapter='hunyuan_invocation_tables')
  self.assertFalse(runner.parse_source(hy().replace('能力说明','新类别').encode(),source,'2026-11-18T04:00:00Z')['complete'])
if __name__=='__main__':unittest.main()
