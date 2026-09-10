"""Regression test: real humans must never be classified as bots."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "modules"))
from visitor_report import BOT_PATTERN

HUMANS = {
    "Chrome desktop": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Safari iOS": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Chrome Android": "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36",
    "Firefox": "Mozilla/5.0 (X11; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0",
    "Edge": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0",
    "Safari macOS": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Samsung Internet": "Mozilla/5.0 (Linux; Android 14; SAMSUNG SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) SamsungBrowser/25.0 Chrome/121.0.0.0 Mobile Safari/537.36",
    "Firefox iOS": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) FxiOS/128.0 Mobile/15E148 Safari/605.1.15",
    "Edge iOS": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 EdgiOS/128.0 Mobile/15E148 Safari/605.1.15",
    # --- in-app browsers: this site's traffic is social, so these matter most ---
    "Instagram in-app": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Instagram 336.0.0.35.90 (iPhone14,2; iOS 17_5_1; en_US; en; scale=3.00; 1170x2532)",
    "Facebook in-app": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [FBAN/FBIOS;FBDV/iPhone14,2;FBMD/iPhone;FBSN/iOS;FBSV/17.5]",
    "Google app iOS (GSA)": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) GSA/315.0.615285256 Mobile/15E148 Safari/604.1",
    "Google app Android": "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Mobile Safari/537.36 GoogleApp/15.20.32",
    "DuckDuckGo Android": "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/128.0.0.0 Mobile DuckDuckGo/5 Safari/537.36",
    "Yandex Browser": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 YaBrowser/24.7.0.0 Safari/537.36",
    "Pinterest in-app": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Pinterest/12.34",
    "LinkedIn in-app": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 [LinkedInApp]",
}

BOTS = {
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Bingbot": "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
    "GPTBot": "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.1; +https://openai.com/gptbot",
    "ClaudeBot": "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)",
    "AhrefsBot": "Mozilla/5.0 (compatible; AhrefsBot/7.0; +http://ahrefs.com/robot/)",
    "SemrushBot": "Mozilla/5.0 (compatible; SemrushBot/7~bl; +http://www.semrush.com/bot.html)",
    "PetalBot": "Mozilla/5.0 (compatible; PetalBot;+https://webmaster.petalsearch.com/site/petalbot)",
    "Bytespider": "Mozilla/5.0 (compatible; Bytespider; spider-feedback@bytedance.com)",
    "YandexBot": "Mozilla/5.0 (compatible; YandexBot/3.0; +http://yandex.com/bots)",
    "Baiduspider": "Mozilla/5.0 (compatible; Baiduspider/2.0; +http://www.baidu.com/search/spider.html)",
    "DuckDuckBot": "DuckDuckBot/1.1; (+http://duckduckgo.com/duckduckbot.html)",
    "facebookexternalhit": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
    "WhatsApp preview": "WhatsApp/2.23.20.0 A",
    "Twitterbot": "Twitterbot/1.0",
    "curl": "curl/8.5.0",
    "wget": "Wget/1.21.4",
    "python-requests": "python-requests/2.31.0",
    "UptimeRobot": "Mozilla/5.0+(compatible; UptimeRobot/2.0; http://www.uptimerobot.com/)",
    "HeadlessChrome": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/128.0.0.0 Safari/537.36",
    "PerplexityBot": "Mozilla/5.0 (compatible; PerplexityBot/1.0; +https://perplexity.ai/perplexitybot)",
    "Go client": "Go-http-client/2.0",
    "Nuclei scanner": "Mozilla/5.0 (compatible; Nuclei - Open-source project (github.com/projectdiscovery/nuclei))",
}

fp = [(n, u) for n, u in HUMANS.items() if BOT_PATTERN.search(u)]
fn = [(n, u) for n, u in BOTS.items() if not BOT_PATTERN.search(u)]

print(f"humans tested: {len(HUMANS)}   bots tested: {len(BOTS)}")
print()
if fp:
    print(f"FALSE POSITIVES - real visitors wrongly filtered ({len(fp)}):")
    for n, u in fp:
        print(f"  {n}: matched {BOT_PATTERN.search(u).group(0)!r}")
else:
    print("no false positives: every real browser passes")
print()
if fn:
    print(f"FALSE NEGATIVES - bots wrongly counted as human ({len(fn)}):")
    for n, u in fn:
        print(f"  {n}")
else:
    print("no false negatives: every bot is caught")

sys.exit(1 if (fp or fn) else 0)
