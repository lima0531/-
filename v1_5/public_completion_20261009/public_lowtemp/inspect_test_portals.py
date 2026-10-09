from collect_public_lowtemp import ROOT, fetch, search
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
from html import unescape
import re, json

def clean(s):
    return re.sub(r'\s+', ' ', unescape(re.sub('<[^>]*>', ' ', s))).strip()

def run():
    searches = [('新能源汽车', 'positive_control'), ('低温', 'lowtemp_broad'), ('检测报告', 'test_reports_broad')]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda x: search(*x), searches))
    portals = [
        ('tatc', 'http://www.tatc.com.cn/', '中汽中心官网链接的天津检验中心'),
        ('gatc', 'http://www.gatc.ac.cn/', '中汽中心官网链接的广州检验中心'),
        ('catarc_wh', 'http://www.catarc-wh.cn/', '中汽中心官网链接的武汉检验中心'),
        ('catarc_nb', 'http://www.catarc-nb.cn/', '中汽中心官网链接的宁波检验中心'),
        ('catarc_cert', 'http://www.catarc-cert.cn/', '中汽中心官网链接的认证业务'),
        ('cmvic', 'https://www.cmvic.com/#/index/index/', '中国汽研官网链接的国家机动车质量检验检测中心（重庆）'),
        ('smvic_cert', 'https://hss.smvic.com.cn/', '上海机动车检测认证技术研究中心官网链接的认证服务'),
        ('cqc_full', 'https://www.cqc.com.cn/www/chinese/', '中国质量认证中心完整中文站；CCC证书不能替代低温报告'),
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        receipts = list(pool.map(lambda x: fetch(x[1], 'test_portals/' + x[0] + '.html', x[2]), portals))
    # Ordinary HTTPS equivalents only; no bypass of login or anti-bot controls.
    for key,url,purpose in portals:
        receipt = next(x for x in receipts if x['local_file'].endswith('/'+key+'.html'))
        if url.startswith('http://') and receipt['status'] != 'ok':
            receipts.append(fetch('https://' + url[7:], 'test_portals/' + key + '_https.html', purpose+'（同站HTTPS入口）'))
    links = []
    for rec in receipts:
        if rec['status'] != 'ok':
            continue
        body=(ROOT/rec['local_file']).read_text(errors='replace')
        for href, inner in re.findall(r'<a\b[^>]*href=[\"\']([^\"\']*)[\"\'][^>]*>(.*?)</a>', body, re.S|re.I):
            title=clean(inner)
            if any(t in title+href.lower() for t in ['报告','查询','检验','检测','服务','联系','认证','search','verify','report','query']):
                links.append({'parent_url':rec['final_url'],'parent_file':rec['local_file'],'title':title,
                              'href':unescape(href),'url':urljoin(rec['final_url'],unescape(href))})
    (ROOT/'test_portal_links.json').write_text(json.dumps(links,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'test_portal_results.json').write_text(json.dumps(receipts,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'statuses':[(x['local_file'],x['status'],x.get('http_status')) for x in receipts], 'selected_links_saved':len(links)},ensure_ascii=False),flush=True)

if __name__=='__main__':
    run()
