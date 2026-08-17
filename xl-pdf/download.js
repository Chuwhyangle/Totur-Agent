const { chromium } = require('playwright-core');
const fs = require('fs');

const chapters = [
  ['1_whatisrag','01_什么是RAG'],
  ['2_rag_problems','02_RAG解决什么问题'],
  ['3_rag_vs_finetune','03_RAG与微调对比'],
  ['4_chunking','04_文档切割Chunking'],
  ['5_semantic_cuts','05_规避语义被切割'],
  ['6_embedding','06_Embedding是什么'],
  ['7_embedding_algos','07_Embedding算法'],
  ['8_vectordb','08_向量数据库'],
  ['9_vectordb_practice','09_向量数据库实践'],
  ['10_online_workflow','10_RAG在线工作流程'],
  ['11_retrieval_types','11_向量与关键词检索'],
  ['12_query_rewrite','12_Query润色重写'],
  ['13_multi_retrieval','13_多路召回'],
  ['14_retrieval_opt','14_检索优化策略'],
  ['15_advanced_paradigms','15_复杂RAG范式'],
  ['16_graph_db','16_图数据库增强检索'],
  ['17_hallucination','17_规避RAG幻觉'],
  ['18_evaluation','18_量化RAG效果'],
  ['19_dynamic_update','19_知识库动态更新'],
  ['20_hardest_parts','20_RAG落地难点'],
];

const OUT = 'pdfs';
if (!fs.existsSync(OUT)) fs.mkdirSync(OUT);

(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const ok = [], fail = [];
  for (const [slug, name] of chapters) {
    const url = 'https://xiaolinnote.com/ai/rag/' + slug + '.html';
    const file = OUT + '/' + name + '.pdf';
    try {
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
      await page.goto(url, { waitUntil: 'networkidle', timeout: 90000 });
      await page.waitForTimeout(1200); // let lazy images load
      await page.pdf({ path: file, printBackground: true, format: 'A4', margin: { top: '1cm', bottom: '1cm', left: '1cm', right: '1cm' } });
      const sz = fs.statSync(file).size;
      ok.push(`${name}: ${(sz/1024).toFixed(0)}KB`);
      console.log('OK  ' + name);
      await page.close();
    } catch (e) {
      fail.push(name + ' -> ' + e.message.split('\n')[0]);
      console.log('FAIL ' + name + ': ' + e.message.split('\n')[0]);
    }
  }
  await browser.close();
  console.log('\n===== 汇总 =====');
  console.log('成功 ' + ok.length + ' / ' + chapters.length);
  if (fail.length) { console.log('失败:'); fail.forEach(f=>console.log('  ' + f)); }
})();
