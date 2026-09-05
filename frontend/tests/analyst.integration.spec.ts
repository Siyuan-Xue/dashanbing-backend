import { fileURLToPath } from 'node:url';
import { expect, test, type Locator, type Page, type TestInfo } from '@playwright/test';
import type { AnalystReport, ComparisonReportState, ContextInput, Observation, TrainingProfile } from '../src/analyst/types';

// Explicit QA fixtures and screenshots, never assets for the public homepage
const stamp = '2026-09-05T08:00:00Z';
const task = { id:'analyst-task',title:'Analyst QA session',mode:'quick',source_type:'upload',preset_id:null,status:'completed',progress:100,stage_message:'Completed',error_code:null,error_message:null,submitted_at:stamp,created_via:'tasks_api',retry_count:0,created_at:stamp,updated_at:stamp,started_at:stamp,completed_at:stamp,inputs:[] };
const metrics = { registered_participant_count:2,event_count:4,action_counts:{triple_threat:0,free_throw:0,jump_shot:4,layup:0},shots:{attempts:4,makes:2,misses:2,undetermined:0,make_rate:.5,unlinked_outcomes:0} };
const subjects = [{id:'player_1',label:'球员 1',profile_id:null},{id:'player_2',label:'球员 2',profile_id:null}];
const evidence = [1,2,3,4].map((i)=>({id:`event-${i}`,event_index:i,subject_id:i<=2?'player_1':'player_2',action_type:'jump_shot',start_ms:i*1000,end_ms:i*1000+800,time_ms:i*1000+500,media_kind:'phases',times_ms:{phases:i*1000+500,cam_01:i*1000+500,cam_02:i*1000+800,cam_03:i*1000+500,cam_04:i*1000+500},result:i%2?'make':'miss',confidence:.9,angles:{}}));
const facts = {schema_version:1,metrics,subjects,evidence,warnings:[],pose_available:false};
const media = Object.fromEntries(['phases','cam_01','cam_02','cam_03','cam_04'].map(kind=>[kind,`/api/v1/tasks/${task.id}/media/${kind}`]));
const result = {...metrics,unsupported_event_count:0,events:evidence,media,warnings:[],disclaimer:'QA fixture'};
const fixtureVideo = fileURLToPath(new URL('./fixtures/autoplay.webm',import.meta.url));
type FixtureOptions = { withProfiles?: boolean; withHistory?: boolean; initiallyBound?: boolean };
type RecordedRequest = { method: string; path: string; body: unknown };
const analystRoot = `/api/v1/tasks/${task.id}/analyst`;
const profiles: TrainingProfile[] = [
  { id:'qa-player-1',kind:'player',name:'Alex',goals:'Consistent release',notes:'',created_at:stamp,updated_at:stamp },
  { id:'qa-player-2',kind:'player',name:'Blair',goals:'Footwork',notes:'',created_at:stamp,updated_at:stamp },
  { id:'qa-team',kind:'team',name:'QA Team',goals:'Team practice',notes:'',created_at:stamp,updated_at:stamp },
];
const history: Observation[] = [
  { id:'qa-player-history',profile_id:'qa-player-1',task_id:'previous-player-task',occurred_at:'2026-09-01T08:00:00Z',mode:'quick',metrics,media_available:true },
  { id:'qa-team-history',profile_id:'qa-team',task_id:null,occurred_at:'2026-09-02T08:00:00Z',mode:'quick',metrics,media_available:false },
];
async function fixture(page: Page, locale: 'en' | 'zh'='en', options: FixtureOptions = {}) {
  let messages: Array<{id:string;role:string;content:string;citations:string[];status:string}> = [];
  let analystCalls=0;
  const requests: RecordedRequest[] = [];
  const unexpectedRequests: RecordedRequest[] = [];
  const comparisonItems: ComparisonReportState[] = [];
  let bindings: ContextInput = {
    subjects: subjects.map((subject,index)=>({id:subject.id,profile_id:options.initiallyBound ? profiles[index].id : null})),
    team_profile_id:options.initiallyBound ? 'qa-team' : null,
    comparison_id:null,
  };
  const availableHistory = () => {
    if (!options.withProfiles || options.withHistory === false) return [];
    const linked = new Set([...bindings.subjects.map(subject=>subject.profile_id),bindings.team_profile_id]);
    return history.filter(item=>linked.has(item.profile_id));
  };
  const context = () => ({
    task_id:task.id,facts,
    subjects:subjects.map(subject=>({...subject,...bindings.subjects.find(item=>item.id===subject.id)})),
    team_profile_id:bindings.team_profile_id,comparison_id:bindings.comparison_id,comparisons:availableHistory(),
  });
  const report: AnalystReport={id:'explicit-qa-fixture',summary:locale==='zh'?'本场记录了四次出手，两次命中':'Four recorded shots, two makes',highlights:[{text:locale==='zh'?'这一球值得重看':'Review this recorded make',evidence_ids:['event-1']}],players:[{subject_id:'player_1',text:locale==='zh'?'回看出手画面':'Review the release footage',evidence_ids:['event-1']}],comparison:null,suggestions:[locale==='zh'?'下一次保持同样的练习条件，再比较表现':'Repeat the same drill before comparing sessions'],model:'glm-5.3',locale,style:'coach',created_at:stamp};
  await page.route('**/api/v1/**',async route=>{
    const req=route.request(); const path=new URL(req.url()).pathname;
    const recorded = {method:req.method(),path,body:req.postData() ? req.postDataJSON() : null};
    requests.push(recorded);
    if(path.includes('/analyst')) analystCalls++;
    if(path==='/api/v1/users/me')return route.fulfill({json:{id:7,username:'qa',email:'qa@example.test',is_active:true}});
    if(path==='/api/v1/tasks')return route.fulfill({json:{items:[task],total:1,page:1,page_size:20}});
    if(path==='/api/v1/presets')return route.fulfill({json:[]});
    if(path===`/api/v1/tasks/${task.id}`)return route.fulfill({json:task});
    if(path.endsWith('/result'))return route.fulfill({json:result});
    if(path.includes('/media/'))return route.fulfill({path:fixtureVideo,contentType:'video/webm'});
    if(path==='/api/v1/training-profiles' && req.method()==='GET')return route.fulfill({json:options.withProfiles ? profiles : []});
    if(path.startsWith('/api/v1/training-profiles/') && path.endsWith('/history') && req.method()==='GET')return route.fulfill({json:availableHistory().filter(item=>path===`/api/v1/training-profiles/${item.profile_id}/history`)});
    if(path===`${analystRoot}/context` && req.method()==='GET')return route.fulfill({json:context()});
    if(path===`${analystRoot}/context` && req.method()==='PUT') {
      bindings=req.postDataJSON();
      return route.fulfill({json:context()});
    }
    // An empty list is the default; eligible history never creates a report automatically.
    if(path===`${analystRoot}/comparisons` && req.method()==='GET')return route.fulfill({json:{items:comparisonItems}});
    if(path===`${analystRoot}/comparisons` && req.method()==='POST') {
      const body=req.postDataJSON();
      if(!availableHistory().some(item=>item.id===body.comparison_id))return route.fulfill({status:422,json:{detail:'Select an eligible historical session'}});
      const item: ComparisonReportState = {
        comparison_id:body.comparison_id,status:'completed',error:null,
        report:{...report,id:`qa-comparison-${body.comparison_id}`,locale:body.locale,style:body.style,
          summary:locale==='zh'?`独立历史训练对比：${body.comparison_id}`:`Independent historical comparison: ${body.comparison_id}`,
          comparison:{text:locale==='zh'?'与已选历史训练相比，本场命中率保持不变':'The make rate is unchanged from the selected historical session',evidence_ids:['event-1']},
        },
      };
      const index=comparisonItems.findIndex(value=>value.comparison_id===item.comparison_id);
      if(index<0)comparisonItems.push(item); else comparisonItems[index]=item;
      return route.fulfill({status:202,json:item});
    }
    if(path.endsWith('/analyst/reports') && req.method()==='GET')return route.fulfill({json:{facts,subjects,items:[null,...subjects.map(subject=>subject.id)].flatMap(subject_id=>['coach','roast'].map(style=>({subject_id,locale,style,status:'completed',error:null,report:subject_id===null && style==='coach' ? report : {...report,id:`qa-${subject_id || 'session'}-${style}`,style,summary:`${subject_id || 'session'} ${style} full report`,highlights:report.highlights.filter(item=>item.evidence_ids.every(id=>!subject_id || evidence.find(e=>e.id===id)?.subject_id===subject_id)),players:report.players.filter(item=>!subject_id || item.subject_id===subject_id)}})))}});
    if(path.endsWith('/analyst/report'))return route.fulfill({json:{status:'completed',report,error:null}});
    if(path==='/api/v1/analyst/conversations')return route.fulfill({status:201,json:{id:'qa-conversation',messages:[]}});
    if(path.endsWith('/qa-conversation/messages')) {
      messages=[{id:'question',role:'user',content:req.postDataJSON().content,citations:[],status:'completed'},{id:'answer',role:'assistant',content:'',citations:[],status:'running'}];
      return route.fulfill({status:202,json:{message_id:'answer',job_id:'qa-job'}});
    }
    if(path.endsWith('/qa-conversation/events')) {
      messages[1]={...messages[1],content:'Review the evidence [event-1]',citations:['event-1'],status:'completed'};
      return route.fulfill({contentType:'text/event-stream',body:`event: message\ndata: ${JSON.stringify(messages[1])}\n\nevent: done\ndata: {}\n\n`});
    }
    if(path.endsWith('/qa-conversation'))return route.fulfill({json:{id:'qa-conversation',messages}});
    unexpectedRequests.push(recorded);
    return route.fulfill({status:404,json:{detail:'QA route not found'}});
  });
  return {
    report,requests,unexpectedRequests,
    get analystCalls(){return analystCalls;},
    get contextWrites(){return requests.filter(item=>item.path===`${analystRoot}/context` && item.method==='PUT');},
    get reportRequests(){return requests.filter(item=>[`${analystRoot}/report`,`${analystRoot}/reports`].includes(item.path));},
    get comparisonPosts(){return requests.filter(item=>item.path===`${analystRoot}/comparisons` && item.method==='POST');},
    get comparisonGets(){return requests.filter(item=>item.path===`${analystRoot}/comparisons` && item.method==='GET');},
    get mutations(){return requests.filter(item=>!['GET','HEAD'].includes(item.method));},
  };
}
for(const width of [320,390,768,1440,1920])for(const locale of ['zh','en'] as const)for(const theme of ['light','dark']){
  test(`analyst layout ${width} ${locale} ${theme}`,async({page},info)=>{
    test.skip(info.project.name!=='desktop-chromium','Explicit viewport matrix');
    await page.setViewportSize({width,height:900});
    await page.addInitScript(({locale,theme})=>{localStorage.setItem('dashanbing-locale',locale);localStorage.setItem('dashanbing-theme',theme);},{locale,theme});
    await fixture(page,locale);
    await page.goto(`/workspace/tasks/${task.id}`);
    await expect(page.locator('[data-report-id="explicit-qa-fixture"]')).toBeVisible();
    const video=page.locator('.result-media-panel'), analyst=page.locator('#analyst'), raw=page.locator('.result-insights-panel');
    const v=await video.boundingBox(),a=await analyst.boundingBox(),r=await raw.boundingBox();
    expect(v&&a&&r).toBeTruthy();
    expect(v!.y+v!.height).toBeLessThanOrEqual(r!.y+2);
    expect(r!.y+r!.height).toBeLessThanOrEqual(a!.y+2);
    expect(Math.abs(v!.width-a!.width)).toBeLessThan(2);
    const columns=await page.locator('.analyst-report-grid').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').map(Number.parseFloat));
    expect(columns.length).toBe(1);
    const toolbarItems=await page.locator('.analyst-header h2, .analyst-header-actions > .analyst-settings > button, .analyst-bind-button, .analyst-refresh').evaluateAll(elements=>elements.map(element=>{const box=element.getBoundingClientRect();return box.y+box.height/2}));
    expect(Math.max(...toolbarItems)-Math.min(...toolbarItems)).toBeLessThan(2);
    const reportBox=await page.locator('.analyst-report').boundingBox(),chatBox=await page.locator('.analyst-chat').boundingBox();
    expect(chatBox!.y).toBeGreaterThanOrEqual(reportBox!.y+reportBox!.height);
    await page.locator('.analyst-settings > button').click();
    const selectWidths=await page.locator('.analyst-settings select').evaluateAll(elements=>elements.map(el=>el.getBoundingClientRect().width));
    expect(Math.max(...selectWidths)-Math.min(...selectWidths)).toBeLessThan(1);
    expect(Math.max(...selectWidths)).toBeLessThanOrEqual(200);
    const boundaries=await analyst.evaluate(el=>({top:getComputedStyle(el).borderTopWidth,bottom:getComputedStyle(el).borderBottomWidth,chat:getComputedStyle(el.querySelector('.analyst-chat')!).borderTopWidth}));
    expect(boundaries).toEqual({top:'1px',bottom:'0px',chat:'0px'});
    await page.keyboard.press('Escape');
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await analyst.scrollIntoViewIfNeeded();
    await page.screenshot({path:info.outputPath('qa-analyst.png'),animations:'disabled'});
    const originalHeight=await page.locator('.insight-content').evaluate(el=>el.getBoundingClientRect().height);
    for(const name of [locale==='zh'?'时间线':'Timeline','JSON',locale==='zh'?'概览':'Summary']){
      await page.getByRole('tab',{name,exact:true}).click();
      expect(await page.locator('.insight-content').evaluate(el=>el.getBoundingClientRect().height)).toBeCloseTo(originalHeight,0);
    }
  });
}
test('evidence seeks active camera and chat streams then restores',async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('dashanbing-locale','en'));
  await fixture(page);
  await page.goto(`/workspace/tasks/${task.id}`);
  await expect(page.locator('[data-report-id="explicit-qa-fixture"]')).toBeVisible();
  await page.getByRole('tab',{name:'Camera 2',exact:true}).click();
  await page.locator('.analyst-report').getByRole('button',{name:'View evidence · 1.5s'}).first().click();
  await expect.poll(()=>page.locator('video').evaluate((el:HTMLVideoElement)=>el.currentTime)).toBeGreaterThanOrEqual(1.8);
  await expect.poll(()=>page.locator('video').evaluate((el:HTMLVideoElement)=>el.paused)).toBe(false);
  await page.getByRole('textbox',{name:'Ask the analyst'}).fill('Which shot should I review?');
  await page.getByRole('button',{name:'Send',exact:true}).click();
  await expect(page.locator('.analyst-messages')).toContainText('Review the evidence');
  await page.reload();
  await expect(page.locator('.analyst-messages')).toContainText('Which shot should I review?');
  await expect(page.locator('.analyst-messages')).toContainText('Review the evidence');
});
test('homepage adds analyst capability without querying analyst API',async({page})=>{
  const api=await fixture(page,'zh');
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'让我看看你打球什么b样'})).toBeVisible();
  await expect(page.getByText('AI 分析师，看懂这一场，练好下一场',{exact:true})).toBeVisible();
  expect(api.analystCalls).toBe(0);
  await expect(page.getByRole('link',{name:'开始一次复盘',exact:true})).toBeVisible();
});

test('completed player and tone switches use the loaded collection without generation requests',async({page})=>{
  await page.addInitScript(()=>localStorage.setItem('dashanbing-locale','en'));
  const api=await fixture(page);
  await page.goto(`/workspace/tasks/${task.id}`);
  await expect(page.locator('[data-report-id="explicit-qa-fixture"]')).toBeVisible();
  const reads=api.reportRequests.length;
  await page.getByRole('button',{name:'Configure',exact:true}).click();
  const selectors=page.getByRole('dialog',{name:'Configure',exact:true}).getByRole('combobox');
  for(const subject of ['player_1','player_2',''])for(const style of ['coach','roast']){
    await selectors.nth(0).selectOption(subject);
    await selectors.nth(1).selectOption(style);
    const id=!subject && style==='coach' ? 'explicit-qa-fixture' : `qa-${subject || 'session'}-${style}`;
    await expect(page.locator(`[data-report-id="${id}"]`)).toBeVisible();
  }
  expect(api.reportRequests).toHaveLength(reads);
  expect(api.mutations).toEqual([]);
  expect(api.unexpectedRequests).toEqual([]);
});

for(const width of [768,800,900,1024])test(`expanded tablet sidebar preserves the analyst toolbar at ${width}px`,async({page},info)=>{
  test.skip(info.project.name!=='desktop-chromium','Explicit tablet widths');
  await page.setViewportSize({width,height:700});
  await page.addInitScript(()=>localStorage.setItem('dashanbing-locale','en'));
  await fixture(page,'en',{withProfiles:true,initiallyBound:true});
  await page.goto(`/workspace/tasks/${task.id}`);
  await expect(page.getByRole('button',{name:'Compare training',exact:true})).toBeEnabled();
  await page.locator('.workspace-collapsed-header .workspace-collapse').click();
  const toolbar=page.getByRole('toolbar',{name:'AI analyst',exact:true});
  await toolbar.scrollIntoViewIfNeeded();
  const heading=await toolbar.getByRole('heading').boundingBox();
  const controls=await toolbar.getByRole('button').evaluateAll(elements=>elements.map(element=>{const box=element.getBoundingClientRect();return {right:box.right,center:box.y+box.height/2}}));
  expect(heading!.width).toBeGreaterThan(100);
  expect(heading!.height).toBeLessThan(40);
  for(const control of controls){expect(control.right).toBeLessThanOrEqual(width);expect(Math.abs(control.center-heading!.y-heading!.height/2)).toBeLessThan(2);}
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
});

for(const [width,height] of [[320,568],[390,664],[1440,768],[1920,700]])test(`AI showcase fits a short screen ${width}x${height}`,async({page},info)=>{
  test.skip(info.project.name!=='desktop-chromium','Explicit short viewports');
  await page.setViewportSize({width,height});
  await page.addInitScript(()=>localStorage.setItem('dashanbing-locale','en'));
  const api=await fixture(page);
  await page.goto('/');
  const showcase=page.locator('.ai-showcase');
  await showcase.scrollIntoViewIfNeeded();
  await showcase.locator('picture img').evaluate((image:HTMLImageElement)=>image.decode());
  expect((await showcase.boundingBox())!.height).toBeLessThanOrEqual(height);
  await expect(showcase.getByRole('link',{name:'View AI review'})).toBeVisible();
  expect(api.analystCalls).toBe(0);
});

const flowCopy = {
  en: { bind:'Bind profiles',players:['Player 1','Player 2'],team:'Team',confirm:'Confirm',cancel:'Cancel',configure:'Configure',style:'Analysis style',compare:'Compare training',history:'Historical session',generate:'Generate comparison' },
  zh: { bind:'绑定档案',players:['球员 1','球员 2'],team:'球队',confirm:'确认',cancel:'取消',configure:'配置',style:'分析风格',compare:'对比训练',history:'历史训练',generate:'生成对比报告' },
};
const profileFlows = [
  { width:320,locale:'en',theme:'light' },
  { width:390,locale:'zh',theme:'dark' },
  { width:768,locale:'en',theme:'light' },
  { width:1440,locale:'zh',theme:'light' },
] as const;

async function expectUnavailable(button: Locator) {
  if(await button.count())await expect(button).toBeDisabled();
  else await expect(button).toHaveCount(0);
}
async function expectFitsViewport(page: Page, element: Locator) {
  const box=await element.boundingBox();
  expect(box).not.toBeNull();
  const viewport=page.viewportSize()!;
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x+box!.width).toBeLessThanOrEqual(viewport.width+1);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.y+box!.height).toBeLessThanOrEqual(viewport.height+1);
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
}
async function captureQA(page: Page, info: TestInfo, name: string, fullPage=false) {
  const path=info.outputPath(`${name}.png`);
  if(fullPage)await page.evaluate(()=>window.scrollTo({top:0,left:0,behavior:'instant'}));
  await page.screenshot({path,fullPage,animations:'disabled'});
  await info.attach(name,{path,contentType:'image/png'});
}

for(const {width,locale,theme} of profileFlows) {
  test(`profile binding and independent comparisons ${width} ${locale} ${theme}`,async({page},info)=>{
    test.skip(info.project.name!=='desktop-chromium','Explicit viewport flows');
    const t=flowCopy[locale];
    await page.setViewportSize({width,height:900});
    await page.addInitScript(({locale,theme})=>{
      localStorage.setItem('dashanbing-locale',locale);
      localStorage.setItem('dashanbing-theme',theme);
    },{locale,theme});
    const api=await fixture(page,locale,{withProfiles:true});
    await page.goto(`/workspace/tasks/${task.id}`);
    const original=page.locator(`[data-report-id="${api.report.id}"]`);
    const expectOriginal=async()=>{
      await expect(original).toBeVisible();
      await expect(original).toHaveAttribute('data-report-id',api.report.id);
      await expect(original.locator('[data-report-summary]')).toHaveText(api.report.summary);
      await expect(original).not.toContainText(locale==='zh'?'独立历史训练对比':'Independent historical comparison');
    };
    await expectOriginal();
    const bind=page.getByRole('button',{name:t.bind,exact:true});
    const compare=page.getByRole('button',{name:t.compare,exact:true});
    await expect(bind).toBeEnabled();
    await expectUnavailable(compare);
    await expect(page.locator('[data-report-id]')).toHaveCount(1);
    await expect(page.locator('[data-comparison-id]')).toHaveCount(0);
    expect(api.mutations).toEqual([]);
    const initialReportRequests=api.reportRequests.length;

    // Configure only changes player and style; binding and comparison stay separate.
    await page.getByRole('button',{name:t.configure,exact:true}).click();
    const settings=page.getByRole('dialog',{name:t.configure,exact:true});
    await expect(settings).toBeVisible();
    await expect(settings.getByRole('combobox')).toHaveCount(2);
    await expect(settings.getByRole('combobox',{name:t.style,exact:true})).toHaveValue('coach');
    await expect(settings.getByRole('option')).toHaveCount(5);
    await expect(settings.getByRole('combobox',{name:t.history,exact:true})).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(settings).toBeHidden();

    const bindingDialog=page.getByRole('dialog',{name:t.bind,exact:true});
    const chooseBindings=async()=>{
      for(const [index,label] of t.players.entries()) {
        const select=bindingDialog.getByRole('combobox',{name:label,exact:true});
        await expect(select).toBeEnabled();
        await expect(select.getByRole('option')).toHaveText([locale==='zh'?'未关联':'Not linked','Alex','Blair']);
        await select.selectOption(profiles[index].id);
      }
      const team=bindingDialog.getByRole('combobox',{name:t.team,exact:true});
      await expect(team.getByRole('option')).toHaveText([locale==='zh'?'未关联':'Not linked','QA Team']);
      await team.selectOption('qa-team');
    };
    await bind.click();
    await expect(bindingDialog).toHaveAttribute('aria-modal','true');
    await expect(bindingDialog.getByRole('combobox')).toHaveCount(3);
    await chooseBindings();
    expect(api.mutations).toEqual([]);
    await expectFitsViewport(page,bindingDialog);
    await captureQA(page,info,'qa-bind-profiles');
    await bindingDialog.getByRole('button',{name:t.cancel,exact:true}).click();
    await expect(bindingDialog).toBeHidden();
    await expectOriginal();
    expect(api.contextWrites).toEqual([]);
    await expectUnavailable(compare);

    // Cancel discarded every draft; Confirm saves one complete player/team payload.
    await bind.click();
    for(const label of [...t.players,t.team])await expect(bindingDialog.getByRole('combobox',{name:label,exact:true})).toHaveValue('');
    await chooseBindings();
    await bindingDialog.getByRole('button',{name:t.confirm,exact:true}).click();
    await expect(bindingDialog).toBeHidden();
    await expect(compare).toBeEnabled();
    expect(api.contextWrites).toEqual([{
      method:'PUT',path:`${analystRoot}/context`,
      body:{subjects:[{id:'player_1',profile_id:'qa-player-1'},{id:'player_2',profile_id:'qa-player-2'}],team_profile_id:'qa-team',comparison_id:null},
    }]);
    await expectOriginal();
    expect(api.reportRequests).toHaveLength(initialReportRequests);
    expect(api.comparisonPosts).toEqual([]);
    await expect(page.locator('[data-report-id]')).toHaveCount(1);
    await expect(page.locator('[data-comparison-id]')).toHaveCount(0);

    // Binding changes enable comparison, but do not change the original report or generate a comparison.
    await bind.click();
    for(const [index,label] of t.players.entries())await expect(bindingDialog.getByRole('combobox',{name:label,exact:true})).toHaveValue(profiles[index].id);
    await expect(bindingDialog.getByRole('combobox',{name:t.team,exact:true})).toHaveValue('qa-team');
    await bindingDialog.getByRole('button',{name:t.cancel,exact:true}).click();
    const picker=page.getByRole('dialog',{name:t.compare,exact:true});
    await compare.click();
    await expect(picker).toBeVisible();
    await expect(picker.getByRole('combobox')).toHaveCount(1);
    const historicalSession=picker.getByRole('combobox',{name:t.history,exact:true});
    const generate=picker.getByRole('button',{name:t.generate,exact:true});
    for(const item of history)await expect(historicalSession.locator(`option[value="${item.id}"]`)).toHaveCount(1);
    await historicalSession.selectOption(history[0].id);
    await expect(generate).toBeEnabled();
    expect(api.comparisonPosts).toEqual([]);
    expect(api.contextWrites).toHaveLength(1);
    await expectFitsViewport(page,picker);
    const pickerBox=await picker.boundingBox();
    expect(pickerBox!.width).toBeLessThanOrEqual(440);
    expect(pickerBox!.height).toBeLessThanOrEqual(400);
    await captureQA(page,info,'qa-comparison-picker');
    await page.keyboard.press('Escape');
    await expect(picker).toBeHidden();
    expect(api.comparisonPosts).toEqual([]);

    const appended: Locator[]=[];
    for(const [index,item] of history.entries()) {
      await compare.click();
      await historicalSession.selectOption(item.id);
      expect(api.comparisonPosts).toHaveLength(index);
      await generate.click();
      await expect(picker).toBeHidden();
      const comparison=page.locator(`[data-comparison-id="${item.id}"]`);
      await expect(comparison).toBeVisible();
      await expect(comparison).toHaveAttribute('data-comparison-status','completed');
      await expect(comparison).toContainText(locale==='zh'?`独立历史训练对比：${item.id}`:`Independent historical comparison: ${item.id}`);
      appended.push(comparison);
      await expectOriginal();
      expect(api.comparisonPosts).toEqual(history.slice(0,index+1).map(value=>({
        method:'POST',path:`${analystRoot}/comparisons`,body:{comparison_id:value.id,locale,style:'coach'},
      })));
      expect(api.contextWrites).toHaveLength(1);
      expect(api.reportRequests).toHaveLength(initialReportRequests);
      await expect(page.locator('[data-report-id]')).toHaveCount(1);
      await expect(page.locator('[data-comparison-id]')).toHaveCount(index+1);
      for(const saved of appended)await expect(saved).toBeVisible();
    }

    const expectReportOrder=async()=>{
      const originalBox=await original.boundingBox();
      const chatBox=await page.locator('.analyst-chat').boundingBox();
      expect(originalBox && chatBox).toBeTruthy();
      for(const comparison of appended) {
        const box=await comparison.boundingBox();
        expect(box).not.toBeNull();
        expect(box!.y).toBeGreaterThanOrEqual(originalBox!.y+originalBox!.height-1);
        expect(box!.y+box!.height).toBeLessThanOrEqual(chatBox!.y+1);
      }
    };
    await expectReportOrder();
    const comparisonReads=api.comparisonGets.length;
    await page.reload();
    await expectOriginal();
    for(const comparison of appended)await expect(comparison).toBeVisible();
    await expect(page.locator('[data-report-id]')).toHaveCount(1);
    await expect(page.locator('[data-comparison-id]')).toHaveCount(2);
    await expect.poll(()=>api.comparisonGets.length).toBeGreaterThan(comparisonReads);
    await expectReportOrder();
    await expect(page.getByRole('dialog',{name:t.compare,exact:true})).toBeHidden();
    expect(api.comparisonPosts).toHaveLength(2);
    expect(api.contextWrites).toHaveLength(1);
    expect(api.reportRequests.filter(item=>item.method!=='GET')).toEqual([]);
    expect(api.mutations).toEqual([api.contextWrites[0],...api.comparisonPosts]);
    expect(api.unexpectedRequests).toEqual([]);
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await page.locator('#analyst').scrollIntoViewIfNeeded();
    await captureQA(page,info,'qa-comparisons-restored',true);
  });
}

for(const scenario of [
  { name:'unbound profiles',options:{withProfiles:true},eligible:false },
  { name:'bound profiles without history',options:{withProfiles:true,initiallyBound:true,withHistory:false},eligible:false },
  { name:'bound profiles with eligible history',options:{withProfiles:true,initiallyBound:true},eligible:true },
]) {
  test(`comparison starts empty with ${scenario.name} and never auto-generates`,async({page})=>{
    await page.addInitScript(()=>localStorage.setItem('dashanbing-locale','en'));
    const api=await fixture(page,'en',scenario.options);
    await page.goto(`/workspace/tasks/${task.id}`);
    await expect(page.locator(`[data-report-id="${api.report.id}"]`)).toBeVisible();
    await expect(page.getByRole('button',{name:'Bind profiles',exact:true})).toBeEnabled();
    const compare=page.getByRole('button',{name:'Compare training',exact:true});
    if(scenario.eligible) {
      await expect(compare).toBeEnabled();
      await compare.click();
      const picker=page.getByRole('dialog',{name:'Compare training',exact:true});
      await picker.getByRole('combobox',{name:'Historical session',exact:true}).selectOption(history[0].id);
      await expect(picker.getByRole('button',{name:'Generate comparison',exact:true})).toBeEnabled();
      await page.keyboard.press('Escape');
      await expect(picker).toBeHidden();
    } else await expectUnavailable(compare);
    await expect(page.locator('[data-report-id]')).toHaveCount(1);
    await expect(page.locator('[data-comparison-id]')).toHaveCount(0);
    expect(api.mutations).toEqual([]);
    expect(api.unexpectedRequests).toEqual([]);
  });
}
