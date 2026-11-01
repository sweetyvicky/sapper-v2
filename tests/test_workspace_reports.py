"""Narrative reports preserve public facts while making their limits readable."""
import base64
import hashlib
import html
import json
from pathlib import Path
import sys
import re
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from pentest.workspace_reports import render_report


class ReportPresentationTests(unittest.TestCase):
    def snapshot(self):
        return dict(version=1, generated_at=0, task=dict(id='task-id',name='任务',goal='检查目标',context='',assets=[dict(id='a',name='站点',target='https://example.invalid/'+'x'*200,assumed_scheme=False)],exclusions=['192.0.2.0/24'],allowed_tools=['http_get']),
            run=dict(id='run-id',status='completed',engagement_complete=False),
            scope=dict(origins=['https://example.invalid:443'],pinned={'example.invalid':['192.0.2.1']},excluded_origins=['https://excluded.invalid:443'],denied_networks=['192.0.2.0/24'],enrollment='whole-origin'),
            budget=dict(limits=dict(requests=10,bytes=1048576,seconds=60,parallel=1,model_calls=4),usage=dict(requests=0,bytes=0,seconds=0),model_calls=[]),
            coverage=dict(metrics=dict(assets=dict(covered=1,total=2),tests=dict(covered=1,total=3,planned=4,not_applicable=1),states=dict(covered=1,evidence_gap=1,not_started=1,not_applicable=1),types=dict(endpoint=dict(covered=1,total=2))),assets=[dict(id='a',target='https://example.invalid/',included=True,kind='endpoint',covered=True),dict(id='b',target='https://excluded.invalid/',included=False,kind='endpoint',covered=False)],checks=[dict(id='get',label='GET 观察',method='http_get'),dict(id='security',label='人工安全检查',method='manual')],cells=[dict(asset_id='a',check_id='get',state='covered',fact_ids=['fact-id']),dict(asset_id='a',check_id='security',state='evidence_gap',reasons=['evidence revoked'],assessment=dict(id='assessment-id',outcome='completed',actor='复核人',note='人工历史',created_at=0))],history=dict(plans=[dict(revision=1,digest='plan-digest',created_at=0)],assessments=[dict(id='old-assessment',outcome='not_applicable',actor='历史人员',note='历史排除',created_at=0)])),
            plan=dict(revision=1,gaps=['未测试登录'],actions=[dict(id='success',state='succeeded'),dict(id='failure',state='failed')]),findings=[])

    def test_budget_scope_coverage_and_history_have_precise_readable_semantics(self):
        for fmt in ('html','markdown'):
            out=render_report(self.snapshot(),fmt)
            if fmt=='markdown': out=re.sub(r'\\([\W_])',r'\1',out)
            for text in ('预留额度已消费','1 MiB','0 字节','0 秒','0 次','1 / 2','1 / 3','HTTP 观察','人工安全检查','历史成功动作','不适用','排除','未测试登录','192.0.2.1','whole-origin','历史排除','plan-digest','UTC','暂无记录案例'):
                self.assertIn(text,out)
            self.assertIn('已覆盖（当前证据有效）',out)
            self.assertNotIn('已覆盖观察',out)
            self.assertNotIn('实际用量',out)
            self.assertNotIn('未提供',out)
            self.assertNotIn('"covered":',out)
            self.assertNotIn('没有漏洞',out)

    def test_case_narrative_history_and_independent_advice_remain_distinct(self):
        data=self.snapshot()
        data['findings']=[dict(id='case',title='失效案例 <script>title()</script>',status='stale',severity='high',description='failed <img src=x onerror=alert(1)>',impact='影响',reproduction='步骤',remediation='修复建议正文',cwe='CWE-79',operator_note='操作员说明',invalid_reasons=['policy expired'],narrative_incomplete=False,narrative_revision=0,narrative_history=[dict(revision=1,created_at=0,data=dict(description='早期描述',impact='早期影响',reproduction='早期复现',remediation='早期修复'))],evidence=[dict(id='evidence-full-id',receipt_id='receipt-full-id',tool='http_get',http_status=0,body_sha256='a'*64,excerpt='confirmed <script>evil()</script>',started_at=0)],reviews=[dict(reviewer='独立审查者',outcome='confirmed',at=0,note='历史结论',evidence_id='unattached-review-evidence')])]
        data['review_suggestions']=[dict(finding_id='case',evidence_id='independent-id',call_id='call-id',outcome='confirmed',current_finding_status='stale',evidence_current_valid=False)]
        for fmt in ('html','markdown'):
            out=render_report(data,fmt)
            for text in ('failed','confirmed','早期描述','早期影响','早期复现','早期修复','policy expired','历史结论','仅有证据引用','当前有效性未知','CWE-79','a'*64,'receipt-full-id','内容摘录（已隐藏常见敏感字段）','4096','不完整','尚未采纳','无效或缺失','不是漏洞已修复','UTC'):
                self.assertIn(text,out)
            self.assertNotIn('原状态已过期',out)
            self.assertNotIn('<script>',out)
            self.assertNotIn('<img ',out)
            self.assertLess(out.index('失效案例'),out.index('模型复核建议'))
        self.assertEqual(json.loads(render_report(data,'json')),data)

    def test_exact_static_style_hash_no_active_content_and_optional_omission(self):
        data=self.snapshot(); data['untrusted_extension']={'odd':'do-not-render'}
        data['task']['context']='javascript:alert(1) <style>body{display:none}</style>'
        out=render_report(data,'html')
        style=re.search(r'<style>(.*?)</style>',out,re.S).group(1)
        digest=base64.b64encode(hashlib.sha256(style.encode('utf-8')).digest()).decode('ascii')
        csp=html.unescape(re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"',out).group(1))
        self.assertIn("style-src 'sha256-"+digest+"'",csp)
        self.assertIn("default-src 'none'",csp)
        self.assertNotIn('unsafe-inline',csp)
        self.assertNotRegex(out,r'<(?:script|img|link|iframe|a)\b')
        self.assertEqual(out.count('<style>'),1)
        self.assertIn('@media print',style)
        self.assertIn('overflow-wrap',style)
        self.assertNotIn('do-not-render',out)
        self.assertNotIn('<dt>背景</dt><dd><pre></pre>',out)
        self.assertIn('<pre>否</pre>',out)


if __name__ == '__main__': unittest.main()
