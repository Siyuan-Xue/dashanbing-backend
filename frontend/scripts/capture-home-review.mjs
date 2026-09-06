#!/usr/bin/env node
// Real public page only: static assets, no account session or model requests.
import { parseArgs } from 'node:util';
import { resolve, join } from 'node:path';
import { mkdir, writeFile } from 'node:fs/promises';
import { chromium } from '@playwright/test';

const {values}=parseArgs({options:{'base-url':{type:'string',default:'http://localhost:5183'},'output-dir':{type:'string',default:'../runtime/analyst-preview/report-switching-review'}}});
const origin=new URL(values['base-url']);
if(!['http:','https:'].includes(origin.protocol)||origin.username||origin.password)throw new Error('Use an HTTP(S) origin without credentials');
const output=resolve(values['output-dir']);await mkdir(output,{recursive:true});
const browser=await chromium.launch();const results=[];
try{
  for(const width of [320,390,768,1440,1920])for(const locale of ['zh','en'])for(const theme of ['light','dark']){
    const page=await browser.newPage({viewport:{width,height:900},colorScheme:theme,reducedMotion:'reduce'});
    const aiRequests=[];
    page.on('request',request=>{const path=new URL(request.url()).pathname;if(path.startsWith('/api/v1/') && path.includes('/analyst') || path.endsWith('/chat/completions'))aiRequests.push(request.url());});
    await page.addInitScript(({locale,theme})=>{localStorage.setItem('dashanbing-locale',locale);localStorage.setItem('dashanbing-theme',theme);},{locale,theme});
    await page.goto(origin.origin+'/',{waitUntil:'networkidle'});
    await page.locator('.product-preview-video img').evaluate(image=>image.decode());
    await page.screenshot({path:join(output,`home-${width}-${locale}-${theme}.png`),animations:'disabled'});
    const section=page.locator('.ai-showcase');await section.scrollIntoViewIfNeeded();
    await section.locator('.ai-preview-cameras img').evaluateAll(images=>Promise.all(images.map(image=>image.decode())));
    const geometry=await section.boundingBox();
    const layout=await page.evaluate(()=>{
      const box=selector=>{const r=document.querySelector(selector).getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom};};
      const video=box('.hero-preview-wrap > .product-preview');const ai=box('.ai-preview-frame');
      const headings=[...document.querySelectorAll('main h1,main h2')].map(element=>{const r=element.getBoundingClientRect();return {text:element.textContent,center:r.x+r.width/2,align:getComputedStyle(element).textAlign};});
      const overflow=[...document.querySelectorAll('.ai-preview-content *')].filter(element=>{const r=element.getBoundingClientRect();return r.width&&r.height&&(r.left<ai.x||r.right>ai.right+1||r.bottom>ai.bottom+1);}).map(element=>element.className);
      const matchingCanvas=getComputedStyle(document.querySelector('.ai-showcase')).backgroundColor===getComputedStyle(document.body).backgroundColor;
      return {video,ai,headings,overflow,matchingCanvas,pageOverflow:document.documentElement.scrollWidth>innerWidth};
    });
    if(!layout.matchingCanvas||layout.pageOverflow||layout.overflow.length||aiRequests.length||Math.max(Math.abs(layout.video.width-layout.ai.width),Math.abs(layout.video.height-layout.ai.height),Math.abs(layout.video.x-layout.ai.x))>1||layout.headings.some(heading=>Math.abs(heading.center-width/2)>1||heading.align!=='center'))throw new Error(`Invalid showcase ${width}/${locale}/${theme}: ${JSON.stringify(layout)}`);
    // Keep the sticky public header outside this native document-coordinate crop.
    await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
    const clip=await section.boundingBox();
    await page.screenshot({path:join(output,`ai-${width}-${locale}-${theme}.png`),clip,fullPage:true,animations:'disabled'});
    results.push({width,locale,theme,height:geometry.height,layout,ai_requests:aiRequests.length});
    await page.close();
  }
  await writeFile(join(output,'verification.json'),JSON.stringify({source:origin.origin,captured_at:new Date().toISOString(),results},null,2));
  console.log(`Captured 40 real public-page screenshots in ${output}, no AI API requests`);
}finally{await browser.close();}
