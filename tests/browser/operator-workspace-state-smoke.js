async page=>{
 const messages=[];const failed=[];const consoleListener=m=>{if(m.type()==='error')messages.push(m.text())};const responseListener=r=>{if(r.status()>=400)failed.push(r.status()+' '+r.url())};page.on('console',consoleListener);page.on('response',responseListener);
 try{
  const state=await page.evaluate(async()=>{const tasks=(await(await fetch('/api/tasks')).json()).tasks;const snapshots=[];for(const t of tasks){const records=(await(await fetch('/api/tasks/'+t.id+'/runs')).json()).runs;for(const r of records)snapshots.push((await(await fetch('/api/runs/'+r.id)).json()).snapshot);}return {tasks,snapshots};});
  const actualGuidance=[];for(const s of state.snapshots)for(const m of s.messages.filter(m=>m.kind==='guidance'&&m.status==='consumed')){const call=s.model_calls.find(c=>c.id===m.consumer);if(!call||!call.message_ids.includes(m.id))throw new Error('guidance consumer/call IDs not bound');actualGuidance.push({run:s.run.id,message:m.id,consumer:m.consumer});}
  if(actualGuidance.length!==2)throw new Error('two real guidance consumers expected');
  const main=state.snapshots.find(s=>s.draft.name==='合成验收 · 完整操作流程');if(main.findings.length!==2||main.findings.some(f=>f.status!=='stale'))throw new Error('cases not retained');
  await page.goto(new URL(page.url()).origin+'/#/tasks/'+main.run.draft_id+'/runs/'+main.run.id);await page.getByRole('tab',{name:'概览',exact:true}).click();const option=await page.getByRole('combobox',{name:'测试轮次',exact:true}).locator('option:checked').textContent();if(!option.includes('本批计划完成'))throw new Error('selected round label stale');
  for(const tab of ['测试过程','资产与覆盖','漏洞','报告'])await page.getByRole('tab',{name:tab,exact:true}).click();await page.frameLocator('iframe').locator('body').filter({hasText:'合成验收'}).waitFor();await page.waitForTimeout(2500);
  if(messages.length||failed.length)throw new Error('normal flow console/network errors '+JSON.stringify({messages,failed}));
  return {tasks:state.tasks.length,runs:state.snapshots.map(s=>({id:s.run.id,status:s.run.status,draft:s.run.draft_revision,findings:s.findings.length,messages:s.messages.length,calls:s.model_calls.length,receipts:s.runtime.tasks.filter(t=>t.receipt_state==='verified').length})),actualGuidance,normalErrors:messages,normalHTTPFailures:failed};
 }finally{page.removeListener('console',consoleListener);page.removeListener('response',responseListener);}
}
