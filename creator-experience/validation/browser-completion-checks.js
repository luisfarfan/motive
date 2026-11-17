// Execute only through proxima-browser, with the independent static server.
async (page, {artifactDir, phase = 'motion'}) => {
  const checks = [], screenshots = [], errors = [], external = [], failedHTTP = [];
  const onError = error => errors.push(String(error));
  const onConsole = message => { if (['error','warning'].includes(message.type())) errors.push(message.text()); };
  const onRequest = request => { if (!/^(http:\/\/127\.0\.0\.1:8768\/|blob:|data:)/.test(request.url())) external.push(request.url()); };
  const onResponse = response => { if (response.status() >= 400) failedHTTP.push({url:response.url(),status:response.status()}); };
  page.on('pageerror',onError); page.on('console',onConsole); page.on('request',onRequest); page.on('response',onResponse);
  const report = {phase,mode:'independent_browser_prototype',browser:'proxima-browser',native_execution:false,checks,screenshots,errors,external,failedHTTP};
  const check = (name, pass, detail = null) => {
    checks.push({name,pass:Boolean(pass),detail});
    if (!pass) throw new Error(`QA failed: ${name}: ${JSON.stringify(detail)}`);
  };
  const goto = async hash => {
    await page.goto(`http://127.0.0.1:8768/prototype/#${hash}`); await page.reload();
    await page.locator('main h1').waitFor();
  };
  const shot = async name => {
    await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(i => i.decode().catch(()=>{}))); });
    await page.evaluate(()=>window.scrollTo(0,0));
    const path = `${artifactDir}/creator-completion-${name}.png`;
    await page.screenshot({path,fullPage:true,scale:'css'});
    screenshots.push({name,path,viewport:page.viewportSize()});
  };
  const layout = async name => {
    const data = await page.evaluate(()=>({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,broken:[...document.images].filter(i=>i.complete&&!i.naturalWidth).map(i=>i.src)}));
    check(name,data.scrollWidth<=data.width&&!data.broken.length,data);
  };
  try {
    await page.emulateMedia({reducedMotion:'no-preference'});
    await page.setViewportSize({width:1440,height:1000});
    if (phase === 'motion') {
      await goto('motion');
      const packs = await page.evaluate(async()=>Promise.all(['creator-tech','neon-arena'].map(id=>fetch(`../packs/${id}/manifest.json`).then(r=>r.json()))));
      const entries = packs.flatMap(pack=>pack.animations.map(animation=>({key:`${pack.id}/${animation.id}`,animation})));
      check('all_22_entries_listed',entries.length===22&&await page.locator('#pack-animation option').count()===22);
      for (const orientation of ['horizontal','vertical']) {
        await page.locator(`[data-motion-orientation="${orientation}"]`).click();
        for (const {key,animation:a} of entries) {
          await page.locator('#pack-animation').selectOption(key);
          const result = await page.locator('#play-selected-motion').evaluate((button,a)=>{
            button.click();
            const stage=document.querySelector('#selected-motion-stage');
            const running=stage.getAnimations({subtree:true});
            if(running.length!==1)return {count:running.length};
            const anim=running[0]; anim.pause();
            const target=anim.effect.target;
            const frames=anim.effect.getKeyframes();
            const samples=[0,.5,1].map(t=>{anim.currentTime=t*a.duration_ms;const s=getComputedStyle(target);return {t,opacity:s.opacity,transform:s.transform};});
            return {count:running.length,id:target.dataset.layer,duration:anim.effect.getTiming().duration,viewBox:stage.querySelector('svg').getAttribute('viewBox'),frames:[frames[0],frames[20],frames[40]],samples};
          },a);
          check(`${key}_${orientation}_target_timing`,result.count===1&&result.id===a.layer_id&&result.duration===a.duration_ms&&result.viewBox===(orientation==='horizontal'?'0 0 960 540':'0 0 540 960'),result);
          const leaving=a.kind.endsWith('_out');
          const p=a.easing==='ease_in'?.25:a.easing==='ease_out'?.75:.5;
          const expected=a.kind.startsWith('slide')?`translateX(${-a.distance*(leaving?p:1-p)}px)`:a.kind.startsWith('scale')?`scale(${leaving?1+(a.scale_from-1)*p:a.scale_from+(1-a.scale_from)*p})`:null;
          check(`${key}_${orientation}_native_quadratic_midpoint`,expected?result.frames[1].transform===expected:Math.abs(Number(result.frames[1].opacity)-(leaving?1-p:p))<1e-6,result.frames[1]);
          await page.locator('#reset-motion-preview').click();
        }
      }
      await page.locator('#reduced-motion').check();
      for (const {key,animation:a} of entries) {
        await page.locator('#pack-animation').selectOption(key); await page.locator('#play-selected-motion').click();
        const result=await page.locator('#selected-motion-stage').evaluate((stage,id)=>({count:stage.getAnimations({subtree:true}).length,opacity:stage.querySelector(`[data-layer="${id}"]`).style.opacity}),a.layer_id);
        check(`${key}_reduced_static`,result.count===0&&Number(result.opacity)===(a.kind.endsWith('_out')?0:1),result);
      }
      await page.locator('#reduced-motion').uncheck();
      await page.locator('#pack-animation').selectOption('creator-tech/tech-lower-in');
      for (const value of ['99','10001','100.5','']) {
        await page.locator('#motion-duration').fill(value);
        check(`reject_duration_${value||'empty'}`,await page.locator('#play-selected-motion').isDisabled()&&!!await page.locator('#motion-param-error').innerText());
      }
      for (const value of ['100','10000']) {
        await page.locator('#motion-duration').fill(value);
        check(`accept_duration_${value}`,await page.locator('#play-selected-motion').isEnabled());
      }
      await page.locator('#reset-motion-parameters').click();
      for (const value of ['-1921','1921']) {
        await page.locator('#motion-distance').fill(value);
        check(`reject_distance_${value}`,await page.locator('#play-selected-motion').isDisabled());
      }
      for (const value of ['-1920','1920']) {
        await page.locator('#motion-distance').fill(value);
        check(`accept_distance_${value}`,await page.locator('#play-selected-motion').isEnabled());
      }
      await page.locator('#reset-motion-parameters').click();
      await page.locator('#motion-easing').selectOption('ease_in_out');
      check('slide_easing_editable',await page.locator('#play-selected-motion').isEnabled());
      await page.locator('#reset-motion-parameters').click();
      await page.locator('#pack-animation').selectOption('neon-arena/reward-in');
      for (const value of ['0.09','2.01']) {
        await page.locator('#motion-scale').fill(value);
        check(`reject_scale_${value}`,await page.locator('#play-selected-motion').isDisabled());
      }
      for (const value of ['0.1','2']) {
        await page.locator('#motion-scale').fill(value);
        check(`accept_scale_${value}`,await page.locator('#play-selected-motion').isEnabled());
      }
      await page.locator('#reset-motion-parameters').click();
      await page.locator('#pack-animation').selectOption('creator-tech/tech-title-in');
      check('fade_easing_locked_linear',await page.locator('#motion-easing').isDisabled()&&await page.locator('#motion-easing').inputValue()==='linear');
      await page.locator('#pack-animation').selectOption('neon-arena/reward-out');
      await page.locator('[data-motion-orientation="horizontal"]').click();
      await shot('motion-desktop');
      await page.locator('#play-selected-motion').evaluate(button=>{button.click();const a=document.querySelector('#selected-motion-stage').getAnimations({subtree:true})[0];a.pause();a.currentTime=a.effect.getTiming().duration/2;});
      await shot('motion-midpoint');
      await page.locator('#reset-motion-preview').click();
      await page.emulateMedia({reducedMotion:'reduce'}); await goto('motion');
      check('system_reduced_cannot_override',await page.locator('#reduced-motion').isChecked()&&await page.locator('#reduced-motion').isDisabled());
      await page.emulateMedia({reducedMotion:'no-preference'});
      for (const width of [1024,390]) {
        await page.setViewportSize({width,height:844}); await goto('motion');
        await page.locator('#pack-animation').selectOption('neon-arena/reward-in');
        await page.locator('[data-motion-orientation="vertical"]').click();
        await layout(`motion_vertical_${width}`); await shot(`motion-${width}`);
      }
    } else if (phase === 'edges') {
      await goto('motion');
      await page.locator('#pack-animation').focus();
      await page.locator('#pack-animation').selectOption('creator-tech/tech-lower-in');
      check('motion_selection_preserves_focus',await page.locator('#pack-animation').evaluate(e=>e===document.activeElement));
      await page.locator('#motion-duration').fill('99'); await page.locator('#motion-distance').fill('1921');
      await page.locator('#motion-duration').fill('320');
      check('invalid_fields_independent',await page.locator('#motion-duration').getAttribute('aria-invalid')==='false'&&await page.locator('#motion-distance').getAttribute('aria-invalid')==='true');
      await page.locator('#motion-distance').fill('32');
      check('correcting_all_fields_clears_invalid',await page.locator('[data-motion-field][aria-invalid="true"]').count()===0&&await page.locator('#play-selected-motion').isEnabled());
      const status=await page.locator('#play-selected-motion').evaluate(async button=>{
        button.click(); document.querySelector('#selected-motion-stage').getAnimations({subtree:true})[0].finish();
        button.click(); await Promise.resolve();
        return document.querySelector('#motion-play-status').textContent;
      });
      check('old_finish_cannot_overwrite_new_preview',status.startsWith('Preview de tech-lower-in'),status);
      await page.emulateMedia({reducedMotion:'reduce'});
      await page.locator('#play-selected-motion').click();
      check('dynamic_os_reduction_observed_without_reload',await page.locator('#selected-motion-stage').evaluate(e=>e.getAnimations({subtree:true}).length)===0);
      await page.locator('#play-scene-transition').click();
      check('dynamic_os_bridge_is_cut',await page.locator('#bridge-after').evaluate(e=>!e.getAnimations().length&&e.style.opacity==='1'));
      await page.emulateMedia({reducedMotion:'no-preference'});
      await goto('pack/creator-tech'); await page.locator('[data-tab="lifecycle"]').click();
      await page.locator('#lifecycle-fixture').focus(); await page.locator('#lifecycle-fixture').selectOption('partial-error');
      check('lifecycle_selection_preserves_focus',await page.locator('#lifecycle-fixture').evaluate(e=>e===document.activeElement));
      check('partially_created_step_not_completed',await page.locator('.lifecycle-steps li').nth(2).getAttribute('data-phase')==='partial');
      await page.locator('[data-lifecycle-action="inspect-created"]').click(); await page.locator('[data-lifecycle-action="reconcile-demo"]').click();
      check('stale_revision_separates_approval',/demo-revision-7[\s\S]*demo-revision-8/.test(await page.locator('.lifecycle-detail').innerText()));
      await page.locator('[data-lifecycle-action="reload-demo"]').click();
      check('reload_keeps_new_revision', (await page.locator('.fixture-facts').innerText()).includes('demo-revision-8'));
      await page.locator('[data-lifecycle-action="review"]').click();
      check('new_approval_binds_new_revision',(await page.locator('.lifecycle-detail').innerText()).includes('demo-revision-8'));
      await page.locator('[data-lifecycle-action="start-demo"]').click(); await page.locator('[data-lifecycle-action="next-step"]').click();
      await page.locator('[data-lifecycle-action="partial"]').click(); await page.locator('[data-lifecycle-action="inspect-created"]').click();
      check('later_partial_preserves_completed_creation',await page.locator('.lifecycle-detail tbody tr').count()===18&&await page.locator('.lifecycle-steps li').nth(3).getAttribute('data-phase')==='partial');
    } else if (phase === 'styles') {
      report.exports=[];
      for(const pack of ['creator-tech','neon-arena']) {
        await goto(`pack/${pack}`);
        await page.locator('#visual-style').selectOption('deep-ink');
        check(`${pack}_background_preset_applied`,await page.locator('[data-property="background"]').inputValue()==='#101216');
        for(const orientation of ['horizontal','vertical']) {
          await page.locator(`[data-orientation="${orientation}"]`).click();
          check(`${pack}_${orientation}_style_persists`,await page.locator('#stage svg rect').first().getAttribute('fill')==='#101216');
        }
        await page.locator('#style-variant').selectOption('reduced-motion');
        const pending=page.waitForEvent('download'); await page.locator('#export-manifest').click();
        const download=await pending;
        const path=`${artifactDir}/creator-completion-${pack}-styled.json`;
        await download.saveAs(path);report.exports.push({pack,path});
        await page.locator('.resource-controls summary').click();
        check(`${pack}_replacement_explicitly_unavailable`,await page.locator('.resource-control button:disabled').count()===2&&(await page.locator('#resource-replacement-limit').innerText()).includes('no declara'));
        if(pack==='creator-tech')await shot('style-vertical');
        await page.locator('[data-tab="details"]').click();
        await page.locator(`a[href="#motion/${pack}/${pack==='creator-tech'?'tech-lower-in':'reward-in'}"]`).click();
        check(`${pack}_recipe_reaches_motion`,await page.locator('#reduced-motion').isChecked()&&await page.locator('#reduced-motion').isDisabled());
        await page.locator('#play-selected-motion').click();
        check(`${pack}_recipe_static`,await page.locator('#selected-motion-stage').evaluate(stage=>stage.getAnimations({subtree:true}).length)===0);
        await page.locator('#inspect-animation').click();
        await page.locator('#reset-properties').click();
        check(`${pack}_reset_restores_original`,await page.locator('#visual-style').inputValue()==='original'&&await page.locator('#style-variant').inputValue()==='original');
        await page.locator('[data-property="background"]').evaluate(input=>{input.value='#141820';input.dispatchEvent(new Event('input',{bubbles:true}));});
        check(`${pack}_manual_color_is_custom`,await page.locator('#visual-style').inputValue()==='custom');
        await page.locator('#visual-style').selectOption('original');
        check(`${pack}_preset_restores_manual_color`,await page.locator('#visual-style').inputValue()==='original'&&await page.locator('[data-property="background"]').inputValue()!=='#141820');
      }
      for(const width of [1024,390]) {
        await page.setViewportSize({width,height:844}); await goto('pack/neon-arena');
        await page.locator('#visual-style').selectOption('deep-ink'); await page.locator('.resource-controls summary').click();
        await layout(`style_customizer_${width}`); await shot(`style-${width}`);
      }
      await page.locator('#visual-style').focus(); await page.keyboard.press('Home'); await page.keyboard.press('Enter');
      check('style_select_keyboard_reachable',await page.locator('#visual-style').evaluate(input=>input===document.activeElement));
    } else if (phase === 'lifecycle') {
      for (const pack of ['creator-tech','neon-arena']) {
        await goto(`pack/${pack}`); await page.locator('[data-tab="lifecycle"]').click();
        check(`${pack}_seven_fixtures`,await page.locator('#lifecycle-fixture option').count()===7);
        await page.locator('[data-lifecycle-action="review"]').click();
        check(`${pack}_reviewed`,await page.locator('#lifecycle-fixture').inputValue()==='reviewed');
        await page.locator('[data-lifecycle-action="start-demo"]').click();
        check(`${pack}_manual_progress`,await page.locator('#lifecycle-fixture').inputValue()==='installing-demo');
        for(let i=0;i<3;i++)await page.locator('[data-lifecycle-action="next-step"]').click();
        check(`${pack}_installed_explicit_example`,await page.locator('#lifecycle-fixture').inputValue()==='installed-demo'&&(await page.locator('.lifecycle-detail').innerText()).includes('No se ha instalado'));
        if(pack==='creator-tech')await shot('installed-example');
        await page.locator('[data-lifecycle-action="customize"]').click();
        check(`${pack}_installed_returns_customizer`,await page.locator('#stage').isVisible());
        await page.locator('[data-tab="lifecycle"]').click();
        await page.locator('#lifecycle-fixture').selectOption('partial-error');
        check(`${pack}_reconcile_requires_inspection`,await page.locator('[data-lifecycle-action="reconcile-demo"]').count()===0);
        await page.locator('[data-lifecycle-action="inspect-created"]').click();
        check(`${pack}_partial_entities_visible`,await page.locator('.lifecycle-detail tbody tr').count()===3);
        if(pack==='creator-tech')await shot('partial-error');
        await page.locator('[data-lifecycle-action="reconcile-demo"]').click();
        check(`${pack}_reconcile_invalidates_plan`,await page.locator('#lifecycle-fixture').inputValue()==='stale-review');
        await page.locator('[data-lifecycle-action="reload-demo"]').click();
        check(`${pack}_stale_requires_review`,await page.locator('#lifecycle-fixture').inputValue()==='ready');
        await page.locator('#lifecycle-fixture').selectOption('missing-resource');
        await page.locator('[data-lifecycle-action="inspect-resource"]').click();
        check(`${pack}_missing_hash_explicit`,/SHA-256 esperado/.test(await page.locator('.lifecycle-detail').innerText())&&!/undefined/.test(await page.locator('.lifecycle-detail').innerText()));
        await page.locator('[data-lifecycle-action="resolve-demo"]').click();
        check(`${pack}_resolved_resource_requires_review`,await page.locator('#lifecycle-fixture').inputValue()==='ready');
        await page.locator('#lifecycle-fixture').selectOption('installing-demo');
        await page.locator('[data-lifecycle-action="cancel-demo"]').click();
        check(`${pack}_cancel_preserves_uncertain_entities`,await page.locator('#lifecycle-fixture').inputValue()==='partial-error'&&(await page.locator('.lifecycle-result').innerText()).includes('No se afirma rollback'));
      }
      for(const width of [1024,390]) {
        await page.setViewportSize({width,height:844}); await goto('pack/creator-tech'); await page.locator('[data-tab="lifecycle"]').click();
        for(const fixture of ['ready','reviewed','installing-demo','installed-demo','partial-error','missing-resource','stale-review']) {
          await page.locator('#lifecycle-fixture').selectOption(fixture);
          if(fixture==='missing-resource')await page.locator('[data-lifecycle-action="inspect-resource"]').click();
          if(fixture==='partial-error')await page.locator('[data-lifecycle-action="inspect-created"]').click();
          await layout(`${fixture}_${width}`);
        }
        await shot(`lifecycle-${width}`);
      }
    }
    check('no_console_warnings_errors',!errors.length,errors);
    check('no_external_requests',!external.length,external);
    check('no_failed_http',!failedHTTP.length,failedHTTP);
    report.status='PASS';
  } catch(error) {report.status='FAIL';report.failure=String(error);}
  finally {page.off('pageerror',onError);page.off('console',onConsole);page.off('request',onRequest);page.off('response',onResponse);}
  return report;
}
