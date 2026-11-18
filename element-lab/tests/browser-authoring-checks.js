async page => {
 const checks=[];const check=(name,ok)=>checks.push({name,status:ok?'PASS':'FAIL'});
 await page.goto('http://127.0.0.1:8776/');
 await page.getByRole('button',{name:'Creador nativo',exact:true}).click();
 for(const name of ['lower-third','community-alert','goal-celebration','countdown']){
  await page.locator('#native-template').selectOption(name);
  await page.waitForFunction(()=>document.querySelector('#native-status').textContent==='Contrato válido');
  check('form_'+name,await page.evaluate(()=>document.querySelectorAll('#native-previews img').length===2&&!document.querySelector('#download-native').disabled));
 }
 // Delay real loopback responses only; no fabricated contract/manifest result.
 let releaseCompile,gotCompile;const heldCompile=new Promise(r=>releaseCompile=r),seenCompile=new Promise(r=>gotCompile=r);
 await page.route('**/api/compile',async route=>{const response=await route.fetch();gotCompile();await heldCompile;await route.fulfill({response});});
 await page.locator('#compile-native').click();await seenCompile;
 await page.locator('#native-properties [name="title"]').fill('Editado durante la validación');
 const compileResponse=page.waitForResponse(r=>r.url().endsWith('/api/compile'));releaseCompile();await compileResponse;await page.waitForTimeout(80);
 check('stale_compile_does_not_accept_changed_form',await page.evaluate(()=>document.querySelector('#native-status').textContent==='Cambios sin validar'&&document.querySelector('#download-native').disabled));
 await page.unroute('**/api/compile');
 let releaseTemplate,gotTemplate;const heldTemplate=new Promise(r=>releaseTemplate=r),seenTemplate=new Promise(r=>gotTemplate=r);
 await page.route('**/api/template/community-alert',async route=>{const response=await route.fetch();gotTemplate();await heldTemplate;await route.fulfill({response});});
 await page.locator('#native-template').selectOption('community-alert');await seenTemplate;
 await page.locator('#native-template').selectOption('countdown');
 await page.waitForFunction(()=>document.querySelector('#native-status').textContent==='Contrato válido');
 const templateResponse=page.waitForResponse(r=>r.url().endsWith('/api/template/community-alert'));releaseTemplate();await templateResponse;await page.waitForTimeout(80);
 check('stale_template_does_not_replace_latest_form',await page.evaluate(()=>document.querySelector('#native-template').value==='countdown'&&document.querySelector('#native-properties [name="duration"]').value==='90000'&&!document.querySelector('#native-properties [name="entry-duration"]')));
 await page.unroute('**/api/template/community-alert');
 await page.goto('http://127.0.0.1:8776/');await page.waitForFunction(()=>window.labTest?.inspect().ready);
 return {status:checks.every(c=>c.status==='PASS')?'PASS':'FAIL',mode:'proxima-browser-only',checks,real_loopback_responses:true,native_render_verified:false};
}
