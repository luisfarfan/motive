// Run this function only through proxima-browser browser_run_code_unsafe.
// Independent prototype only; no Motive, CDP, device, provider or network fixture.
async (page, {artifactDir}) => {
  const checks = [];
  const screenshots = [];
  const errors = [];
  const external = [];
  const failedHTTP = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', msg => { if (['error', 'warning'].includes(msg.type())) errors.push(msg.text()); });
  page.on('request', req => { if (!req.url().startsWith('http://127.0.0.1:8768/') && !req.url().startsWith('blob:') && !req.url().startsWith('data:')) external.push(req.url()); });
  page.on('response', res => { if (res.status() >= 400) failedHTTP.push({url: res.url(), status: res.status()}); });
  const assert = (name, condition, detail = null) => {
    checks.push({name, pass: Boolean(condition), detail});
    if (!condition) throw new Error(`QA failed: ${name}: ${JSON.stringify(detail)}`);
  };
  const goto = async hash => {
    await page.goto(`http://127.0.0.1:8768/prototype/#${hash}`);
    await page.reload();
    await page.locator('main h1').waitFor();
    await page.waitForFunction(() => !document.querySelector('.loading'));
  };
  const shot = async name => {
    await page.evaluate(async () => { await document.fonts.ready; await Promise.all([...document.images].map(i => i.decode().catch(() => {}))); });
    const path = `${artifactDir}/creator-${name}.png`;
    await page.screenshot({path, fullPage:true, scale:'css'});
    screenshots.push({name, path, viewport:page.viewportSize()});
  };
  const checkLayout = async name => {
    const data = await page.evaluate(() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,broken:[...document.images].filter(i=>i.complete&&!i.naturalWidth).map(i=>i.src)}));
    assert(name, data.scrollWidth <= data.width && data.broken.length === 0, data);
  };
  await page.setViewportSize({width:1440,height:1000});
  await goto('library');
  assert('library_two_collections', await page.locator('article.pack-card').count() === 2);
  await page.locator('#search').fill('absent-search-xyz');
  assert('empty_search_explained', await page.locator('#clear-filters').isVisible());
  await page.locator('#clear-filters').click();
  await page.getByRole('button',{name:'Gaming',exact:true}).click();
  assert('category_filters_to_one', await page.locator('article.pack-card').count() === 1);
  await page.getByRole('button',{name:'Todas',exact:true}).click();
  await page.locator('#compat-filter').selectOption('native');
  assert('unsupported_resource_filter_empty', await page.locator('#clear-filters').isVisible());
  await page.locator('#clear-filters').click();
  await checkLayout('library_desktop_layout'); await shot('library-desktop');
  await page.getByRole('link',{name:'Explorar Creator Tech',exact:true}).click();
  await page.locator('[data-property="starting-title"]').fill('Ideas locales.\nImpacto real.');
  assert('typed_text_updates_preview', (await page.locator('#stage').innerText()).includes('Ideas locales.'));
  await page.locator('[data-property="starting-title"]').fill('line\n'.repeat(18));
  assert('invalid_text_rejected', await page.locator('[data-property="starting-title"]').getAttribute('aria-invalid') === 'true');
  await page.locator('[data-property="starting-title"]').fill('Ideas locales.\nImpacto real.');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#export-manifest').click();
  const download = await downloadPromise;
  const exportPath = `${artifactDir}/creator-customized-manifest.json`;
  await download.saveAs(exportPath);
  assert('customized_download', download.suggestedFilename() === 'creator-tech-customized.json');
  await page.locator('#reset-properties').click();
  for (const orientation of ['horizontal','vertical']) {
    await page.locator(`[data-orientation="${orientation}"]`).click();
    for (let i=0; i<6; i++) {
      await page.locator(`[data-scene="${i}"]`).click();
      assert(`tech_scene_${i}_${orientation}`, await page.locator('#stage svg').getAttribute('viewBox') === (orientation==='horizontal'?'0 0 960 540':'0 0 540 960'));
    }
  }
  await page.locator('[data-scene="0"]').click();
  await page.locator('[data-orientation="horizontal"]').click();
  await shot('detail-desktop');
  await page.locator('#open-plan').click();
  await page.locator('#project-state').selectOption('matchday');
  assert('combined_graph_overflow_blocks', await page.locator('#confirm-plan').isDisabled());
  await shot('plan-capacity-block');
  await page.locator('#project-state').selectOption('empty');
  await page.locator('#image-capability').selectOption('no');
  assert('missing_image_capability_blocks', await page.locator('#confirm-plan').isDisabled());
  await page.locator('#image-capability').selectOption('yes');
  assert('unreviewed_plan_blocks', await page.locator('#confirm-plan').isDisabled());
  await page.locator('#approve-plan').check(); await page.locator('#confirm-plan').click();
  assert('plan_review_never_claims_install', (await page.locator('#plan-result').innerText()).includes('No se ha instalado'));
  await goto('deck/neon-arena');
  await page.locator('[data-button="live"]').click();
  assert('sensitive_requires_dialog', await page.locator('dialog').isVisible());
  await page.locator('dialog button[value="cancel"]').click();
  await page.waitForFunction(() => document.querySelector('#history-list').innerText.includes('descartada'));
  assert('cancel_has_no_pending', await page.locator('.pending-card').count() === 0);
  await page.locator('#hold-pending').check();
  await page.locator('[data-button="live"]').click(); await page.locator('#dialog-confirm').click();
  await page.waitForFunction(() => document.querySelector('[data-button="live"]').dataset.state === 'pending');
  assert('pending_button_disabled', await page.locator('[data-button="live"]').isDisabled());
  await page.getByRole('button',{name:'Completar ensayo',exact:true}).click();
  assert('cooldown_visible', await page.locator('[data-button="live"]').getAttribute('data-state') === 'cooling_down');
  await page.locator('#missing-capability').check();
  assert('direct_missing_capability', await page.locator('[data-button="reward-entry"]').getAttribute('data-state') === 'missing');
  assert('composite_independent_widget_counter_ready', await page.locator('[data-button="celebrate"]').getAttribute('data-state') === 'ready');
  assert('disabled_provider', await page.locator('[data-button="provider-follow"]').isDisabled());
  await page.locator('#missing-capability').uncheck();
  await page.locator('[data-button="celebrate"]').click();
  await shot('deck-desktop');
  await goto('motion');
  await page.locator('[data-play="slide_in"]').click();
  const motion = await page.locator('#sample-slide_in').evaluate(el => el.getAnimations({subtree:true}).map(a => ({duration:a.effect.getTiming().duration,frames:a.effect.getKeyframes().map(f=>f.transform)})));
  assert('motion_actual_declared_target', motion.length > 0 && motion[0].frames.some(x=>x?.includes('-')), motion);
  await page.locator('#reduced-motion').check();
  await page.locator('[data-play="scale_in"]').click();
  assert('explicit_reduced_motion_static', await page.locator('#sample-scale_in').evaluate(el=>el.getAnimations({subtree:true}).length) === 0);
  await shot('motion-desktop');
  await page.emulateMedia({reducedMotion:'reduce'});
  await goto('motion');
  assert('os_reduced_motion_observed', await page.locator('#reduced-motion').isChecked());
  await page.emulateMedia({reducedMotion:'no-preference'});
  for (const viewport of [{width:1024,height:768},{width:390,height:844}]) {
    await page.setViewportSize(viewport);
    await goto('library'); await checkLayout(`library_${viewport.width}`); await shot(`library-${viewport.width}`);
    await goto('pack/neon-arena');
    for (const orientation of ['horizontal','vertical']) {
      await page.locator(`[data-orientation="${orientation}"]`).click();
      for(let i=0;i<6;i++) {
        await page.locator(`[data-scene="${i}"]`).click();
        await checkLayout(`neon_scene_${i}_${orientation}_${viewport.width}`);
      }
    }
    await page.locator('[data-scene="0"]').click(); await shot(`vertical-${viewport.width}`);
    await goto('deck/neon-arena'); await checkLayout(`deck_${viewport.width}`);
    await goto('motion'); await checkLayout(`motion_${viewport.width}`);
  }
  await page.setViewportSize({width:1440,height:1000});
  await goto('library'); await page.keyboard.press('Tab');
  assert('keyboard_skip_link', await page.locator('.skip-link').evaluate(el=>el===document.activeElement));
  await page.keyboard.press('Enter');
  assert('skip_targets_main', await page.locator('main').evaluate(el=>el===document.activeElement));
  assert('no_console_errors_or_warnings', errors.length===0, errors);
  assert('no_external_requests', external.length===0, external);
  assert('no_http_errors', failedHTTP.length===0, failedHTTP);
  return {mode:'independent_browser_prototype',native_media_acceptance:false,browser:'proxima-browser',checks,screenshots,exportPath,errors,external,failedHTTP};
}
