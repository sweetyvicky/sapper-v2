async page => {
 const assert=(ok,message)=>{if(!ok)throw new Error(message)};
 const report={};
 await page.getByRole('tab',{name:/覆盖总览/}).click();
 const data=JSON.parse(await page.locator('#coverage-data').textContent());
 const slider=page.getByRole('slider');
 await slider.press('Home');
 report.frames=[];
 for(let i=0;i<data.frames.length;i++){
   if(i)await slider.press('ArrowRight');
   assert(await slider.inputValue()===String(i),'frame selection '+i);
   const snapshot=data.frames[i].snapshot;
   const cards=await page.getByRole('region',{name:'全局覆盖指标'}).locator('article').allTextContents();
   assert(cards[0].includes(`${snapshot.metrics.assets.covered} / ${snapshot.metrics.assets.total}`),'asset metric '+i);
   assert(cards[1].includes(`${snapshot.metrics.tests.covered} / ${snapshot.metrics.tests.total}`),'test metric '+i);
   for(const [state,count] of Object.entries(snapshot.metrics.states))assert(await page.locator('.cell.'+state).count()===count,'matrix '+i+' '+state);
   report.frames.push({step:i+1,assets:snapshot.metrics.assets.covered,tests:snapshot.metrics.tests.covered,states:snapshot.metrics.states});
 }
 const metrics=await page.getByRole('region',{name:'全局覆盖指标'}).textContent();
 await page.getByRole('searchbox',{name:'搜索资产'}).fill('本地观察');
 assert(await page.locator('.cell').count()===4,'search rows');
 assert(await page.getByRole('region',{name:'全局覆盖指标'}).textContent()===metrics,'search denominator');
 await page.getByRole('button',{name:'清除筛选'}).click();
 await page.getByRole('combobox',{name:'测试状态'}).selectOption('evidence_gap');
 assert(await page.locator('.cell.evidence_gap').count()===2,'gap filter');
 assert(await page.getByRole('region',{name:'全局覆盖指标'}).textContent()===metrics,'state denominator');
 await page.getByRole('button',{name:'清除筛选'}).click();
 await page.getByRole('combobox',{name:'资产类型'}).selectOption('service');
 assert(await page.locator('.cell').count()===4,'kind filter');
 assert(await page.getByRole('region',{name:'全局覆盖指标'}).textContent()===metrics,'kind denominator');
 await page.getByRole('button',{name:'清除筛选'}).click();
 await page.getByRole('searchbox',{name:'搜索资产'}).fill('不存在的验收资产');
 assert(await page.locator('.cell').count()===0,'empty search');
 await page.getByRole('button',{name:'清除筛选'}).click();
 report.filters='search/kind/state/empty preserve global denominator';
 const cell=page.getByRole('button',{name:'本地观察端点 · HTTP 响应观察 · 证据失效/缺口',exact:true});
 await cell.click();
 assert(await page.locator('#detail').isVisible(),'detail open');
 assert((await page.locator('#detail').textContent()).includes('证据失效/缺口'),'detail reason');
 await page.keyboard.press('Escape');
 assert(!(await page.locator('#detail').isVisible()),'Escape close');
 assert(await cell.evaluate(e=>e===document.activeElement),'focus restored');
 report.detail='opens, reason visible, Escape closes and restores focus';
 for(const label of ['资产关系','执行过程','证据与发现']){
   await page.getByRole('tab',{name:new RegExp(label)}).click();
   assert(await page.getByRole('tabpanel').isVisible(),'tabpanel '+label);
   assert((await page.getByRole('tabpanel').textContent()).includes(label),'tab content '+label);
 }
 await page.getByRole('tab',{name:/覆盖总览/}).click();
 await page.locator('#play').click();
 await page.waitForFunction(()=>Number(document.querySelector('#frame').value)>0,{timeout:5000});
 await page.locator('#play').click();
 const paused=await slider.inputValue();
 await page.waitForTimeout(1400);
 assert(await slider.inputValue()===paused,'replay pause');
 await slider.press('End');
 report.playback='keyboard slider allframes, play restart and pause';
 report.requests=await page.evaluate(()=>performance.getEntriesByType('resource').map(r=>r.name));
 assert(report.requests.length===0,'standalone page made resource requests');
 report.overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
 assert(!report.overflow,'desktop horizontal overflow');
 return report;
}

