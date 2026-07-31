"""구글광고(Google Ads) 추적 스니펫 생성 — 전용 랜딩·익스포트에 주입.

전문가급 Google Ads 추적 스택:
  · Google tag(gtag.js) — GA4 측정ID + Google Ads 전환ID(전환·리마케팅)
  · 전환 추적 — CTA/구매 클릭 시 conversion 이벤트 발화(값·통화 포함)
  · 리마케팅 — Ads 태그 config
  · UTM/gclid/wbraid/gbraid 캡처 → 세션 보존 → 아웃바운드 제휴링크에 부착(정확한 귀속)
  · GA4 이벤트 — view_item_list, select_content

설정(member_sites.config JSONB):
  ga4_id="G-XXXX", ads_conversion_id="AW-XXXX", ads_conversion_label="LABEL", gads_remarketing=true
"""

from __future__ import annotations

import html
from typing import Any


def has_gads(config: dict | None) -> bool:
    c = config or {}
    return bool((c.get("ga4_id") or "").strip() or (c.get("ads_conversion_id") or "").strip())


def _ids(config: dict) -> list[str]:
    ga4 = (config.get("ga4_id") or "").strip()
    aw = (config.get("ads_conversion_id") or "").strip()
    return [x for x in (ga4, aw) if x]


def gtag_head(config: dict | None) -> str:
    """<head>에 넣을 gtag.js 로더 + GA4/Ads config."""
    c = config or {}
    ids = _ids(c)
    if not ids:
        return ""
    configs = "\n".join(f"gtag('config','{html.escape(x)}');" for x in ids)
    return (
        "<!-- Google tag (gtag.js) -->\n"
        f'<script async src="https://www.googletagmanager.com/gtag/js?id={html.escape(ids[0])}"></script>\n'
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        "gtag('js',new Date());\n" + configs + "\n</script>"
    )


_TRACKING_JS = r"""(function(){
  function g(){ if(window.gtag){ window.gtag.apply(null, arguments); } }
  var keep=['gclid','wbraid','gbraid','utm_source','utm_medium','utm_campaign','utm_term','utm_content'];
  var p=new URLSearchParams(location.search), store={};
  try{ store=JSON.parse(sessionStorage.getItem('gads_attr')||'{}'); }catch(e){}
  keep.forEach(function(k){ var v=p.get(k); if(v){ store[k]=v; } });
  try{ sessionStorage.setItem('gads_attr', JSON.stringify(store)); }catch(e){}
  function decorate(a){ try{ var u=new URL(a.href);
    Object.keys(store).forEach(function(k){ u.searchParams.set(k, store[k]); }); a.href=u.toString(); }catch(e){} }
  var SEND='__SEND_TO__';
  function wire(){
    var links=document.querySelectorAll('a[data-buy]');
    for(var i=0;i<links.length;i++){ (function(a){
      a.addEventListener('click', function(){
        decorate(a);
        if(SEND){ g('event','conversion',{send_to:SEND,
          value:Number(a.getAttribute('data-price')||0), currency:a.getAttribute('data-cur')||'KRW'}); }
        g('event','select_content',{content_type:'product', item_id:a.getAttribute('data-id')||''});
      });
    })(links[i]); }
    g('event','view_item_list',{items:links.length});
  }
  if(document.readyState!=='loading'){ wire(); } else { document.addEventListener('DOMContentLoaded', wire); }
})();"""


def tracking_js(config: dict | None) -> str:
    """</body> 앞에 넣을 UTM/gclid 캡처 + 전환/이벤트 추적 <script>."""
    c = config or {}
    if not has_gads(c):
        return ""
    aw = (c.get("ads_conversion_id") or "").strip()
    label = (c.get("ads_conversion_label") or "").strip()
    send_to = f"{aw}/{label}" if (aw and label) else (aw or "")
    return "<script>\n" + _TRACKING_JS.replace("__SEND_TO__", html.escape(send_to, quote=True)) + "\n</script>"


# ── AdSense(디스플레이 광고 게재) ──
def adsense_client(config: dict | None) -> str:
    return ((config or {}).get("adsense_client") or "").strip()


def has_adsense(config: dict | None) -> bool:
    return bool(adsense_client(config))


def adsense_loader(config: dict | None) -> str:
    """<head>에 넣을 AdSense 로더 스크립트."""
    cid = adsense_client(config)
    if not cid:
        return ""
    return ('<!-- Google AdSense -->\n'
            '<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client='
            f'{html.escape(cid)}" crossorigin="anonymous"></script>')


def adsense_unit(config: dict | None, *, slot: str | None = None, fmt: str = "auto",
                 style: str = "display:block") -> str:
    """AdSense 광고 유닛 <ins> + push. 위치별 배치에 사용."""
    cid = adsense_client(config)
    if not cid:
        return ""
    s = (slot or (config or {}).get("adsense_slot") or "").strip()
    slot_attr = f' data-ad-slot="{html.escape(s)}"' if s else ""
    return (f'<ins class="adsbygoogle" style="{html.escape(style)}" '
            f'data-ad-client="{html.escape(cid)}"{slot_attr} '
            f'data-ad-format="{html.escape(fmt)}" data-full-width-responsive="true"></ins>'
            '<script>(adsbygoogle=window.adsbygoogle||[]).push({});</script>')


def gads_report(config: dict | None) -> dict[str, Any]:
    c = config or {}
    aw = (c.get("ads_conversion_id") or "").strip()
    ads = has_adsense(c)
    return {
        "enabled": has_gads(c) or ads,
        "ga4": bool((c.get("ga4_id") or "").strip()),
        "google_ads_conversion": bool(aw),
        "conversion_label": bool((c.get("ads_conversion_label") or "").strip()),
        "remarketing": bool(aw),  # Ads 태그가 리마케팅 겸용
        "utm_gclid_capture": has_gads(c),
        "outbound_attribution": has_gads(c),
        "adsense": ads,
        "adsense_positions": ["좌측", "우측", "중앙", "하단"] if ads else [],
        "events": ["page_view", "view_item_list", "select_content", "conversion"] if has_gads(c) else [],
    }
