const { chromium } = require('playwright-core');
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const page = await browser.newPage();
  await page.goto('https://xiaolinnote.com/ai/rag/3_rag_vs_finetune.html', { waitUntil: 'networkidle', timeout: 60000 });
  const links = await page.evaluate(() => {
    const out = [];
    document.querySelectorAll('a[href]').forEach(a => {
      const href = a.getAttribute('href') || '';
      const txt = (a.textContent || '').trim().replace(/\s+/g,' ');
      if (href.includes('/ai/rag/')) out.push({ href, txt });
    });
    return out;
  });
  const seen = new Set();
  links.forEach(l => { const key = l.href.split('#')[0]; if(!seen.has(key)){ seen.add(key); console.log(l.href.split('#')[0] + '\t' + l.txt); } });
  await browser.close();
})();
