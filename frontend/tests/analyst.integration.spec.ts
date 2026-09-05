import { fileURLToPath } from 'node:url';
import { expect, test, type Page } from '@playwright/test';

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
async function fixture(page: Page, locale='en') {
  let messages: Array<{id:string;role:string;content:string;citations:string[];status:string}> = [];
  let analystCalls=0;
  const report={id:'explicit-qa-fixture',summary:locale==='zh'?'本场记录了四次出手，两次命中':'Four recorded shots, two makes',highlights:[{text:locale==='zh'?'这一球值得重看':'Review this recorded make',evidence_ids:['event-1']}],players:[{subject_id:'player_1',text:locale==='zh'?'回看出手画面':'Review the release footage',evidence_ids:['event-1']}],comparison:null,suggestions:[locale==='zh'?'下一次保持同样的练习条件，再比较表现':'Repeat the same drill before comparing sessions'],model:'glm-5.3',locale,style:'coach',created_at:stamp};
  await page.route('**/api/v1/**',async route=>{
    const req=route.request(); const path=new URL(req.url()).pathname;
    if(path.includes('/analyst')) analystCalls++;
    if(path==='/api/v1/users/me')return route.fulfill({json:{id:7,username:'qa',email:'qa@example.test',is_active:true}});
    if(path==='/api/v1/tasks')return route.fulfill({json:{items:[task],total:1,page:1,page_size:20}});
    if(path==='/api/v1/presets')return route.fulfill({json:[]});
    if(path===`/api/v1/tasks/${task.id}`)return route.fulfill({json:task});
    if(path.endsWith('/result'))return route.fulfill({json:result});
    if(path.includes('/media/'))return route.fulfill({path:fixtureVideo,contentType:'video/webm'});
    if(path==='/api/v1/training-profiles')return route.fulfill({json:[]});
    if(path.endsWith('/analyst/context'))return route.fulfill({json:{task_id:task.id,facts,subjects,team_profile_id:null,comparison_id:null,comparisons:[]}});
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
    return route.fulfill({status:404,json:{detail:'QA route not found'}});
  });
  return {get analystCalls(){return analystCalls;}};
}
for(const width of [320,390,768,1440,1920])for(const locale of ['zh','en'])for(const theme of ['light','dark']){
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
    expect(v!.y+v!.height).toBeLessThanOrEqual(a!.y+2);
    expect(a!.y+a!.height).toBeLessThanOrEqual(r!.y+2);
    expect(Math.abs(v!.width-a!.width)).toBeLessThan(2);
    const columns=await page.locator('.analyst-columns').evaluate(el=>getComputedStyle(el).gridTemplateColumns.split(' ').map(Number.parseFloat));
    expect(columns.length).toBe(width>=1280?2:1);
    if(columns.length===2)expect(columns[0]/columns[1]).toBeCloseTo(2,1);
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
