const { chromium } = require('playwright-core');
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const page = await browser.newPage();
  await page.goto('https://xiaolinnote.com/ai/rag/3_rag_vs_finetune.html', { waitUntil: 'networkidle', timeout: 60000 });
  console.log('TITLE:', await page.title());
  // look for the print button text
  const btns = await page.evaluate(() => {
    return [...document.querySelectorAll('.print-button, button')].map(b => (b.title||b.textContent||'').trim()).filter(Boolean).slice(0,10);
  });
  console.log('BUTTONS:', JSON.stringify(btns));
  await page.pdf({ path: 'test.pdf', printBackground: true, format: 'A4' });
  console.log('PDF written');
  await browser.close();
})();
