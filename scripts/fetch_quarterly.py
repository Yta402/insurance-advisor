"""采集3个已确认季度的保险消费投诉通报正文。"""
import json
from playwright.sync_api import sync_playwright

targets = [
    {"quarter": "2022Q3", "docId": "1093470"},
    {"quarter": "2022Q4", "docId": "1100596"},
    {"quarter": "2023Q1", "docId": "1113177"},
]
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    for t in targets:
        url = (f"https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html"
               f"?docId={t['docId']}&itemId=925&generaltype=0")
        page = browser.new_page()
        try:
            page.goto(url, timeout=60000)
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            page.wait_for_timeout(2000)
            body = ""
            for sel in [".content", "#zoom", ".pages_content", ".gdetail", ".TRS_Editor"]:
                try:
                    el = page.query_selector(sel)
                    if el:
                        txt = el.inner_text()
                        if len(txt) > 200:
                            body = txt
                            break
                except Exception:
                    pass
            if not body:
                body = page.evaluate("document.body.innerText")
            is_ins = "保险消费投诉" in body
            results.append({
                "quarter": t["quarter"], "docId": t["docId"], "url": url,
                "is_insurance": is_ins, "body_len": len(body), "body": body,
            })
        except Exception as e:
            results.append({"quarter": t["quarter"], "docId": t["docId"], "error": str(e)})
        finally:
            page.close()
    browser.close()

with open("insurance/scripts/quarterly_bodies.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
for r in results:
    print(r["quarter"], "| is_ins:", r.get("is_insurance"), "| len:", r.get("body_len"))
