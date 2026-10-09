#!/usr/bin/env python3
"""Replay public discovery routes only; verification-gated vehicle data is not queried."""
from collect_public_configuration import fetch
ROUTES=[
 ('https://app.miit-eidc.org.cn/miitxxgk/gonggao/xxgk/index','probe_0.html'),
 ('https://www.miit-eidc.org.cn/','probe_1.html'),
 ('https://www.miit-eidc.com/','probe_2.html'),
 ('https://service.miit-eidc.org.cn/miitxxgk/gonggao/xxgk/index?querylb=qy','portal/gonggao_index.html'),
 ('https://yhgscx.miit.gov.cn','portal/energy_index.html'),
 ('https://yhgscx.miit.gov.cn/fuel-consumption-web/js/chunk-vendors.js','portal/energy_script_41.js'),
 ('https://yhgscx.miit.gov.cn/fuel-consumption-web/js/app.js','portal/energy_script_31.js'),
 ('https://www.cdqc.org.cn/2747/19531/878573','external/association_GTM6470BFEBEV.html'),
 ('https://www.cdqc.org.cn/2747/19531/878547','external/association_CC7000CG00FBEV.html'),
]
if __name__=='__main__':
 for url,name in ROUTES:
  r=fetch(url,name);print(name,r['status'],r.get('http_status'))
