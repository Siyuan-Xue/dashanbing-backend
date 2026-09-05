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
    await section.locator('picture img').evaluate(image=>image.decode());
    const geometry=await section.boundingBox();
    const preview=await section.locator('picture img').evaluate(image=>{
      const rect=image.getBoundingClientRect();const frame=image.closest('figure').getBoundingClientRect();
      const source=image.parentElement.querySelector('source');
      // naturalWidth/Height are density-corrected integers for srcset images.
      // Use original source dimensions so rounding cannot look like a crop.
      const dimensions=matchMedia(source.media).matches?source:image;
      return {height:rect.height,expectedHeight:rect.width*Number(dimensions.getAttribute('height'))/Number(dimensions.getAttribute('width')),left:rect.left-frame.left,right:frame.right-rect.right};
    });
    const matchingCanvas=await section.evaluate(element=>getComputedStyle(element).backgroundColor===getComputedStyle(document.body).backgroundColor);
    if(!matchingCanvas||Math.abs(preview.height-preview.expectedHeight)>1||preview.left<12||preview.right<12||await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)||aiRequests.length)throw new Error(`Invalid showcase ${width}/${locale}/${theme}`);
    // Keep the sticky public header outside this native document-coordinate crop.
    await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));
    const clip=await section.boundingBox();
    await page.screenshot({path:join(output,`ai-${width}-${locale}-${theme}.png`),clip,fullPage:true,animations:'disabled'});
    results.push({width,locale,theme,height:geometry.height,matching_canvas:matchingCanvas,preview,ai_requests:aiRequests.length});
    await page.close();
  }
  await writeFile(join(output,'verification.json'),JSON.stringify({source:origin.origin,captured_at:new Date().toISOString(),results},null,2));
  console.log(`Captured 40 real public-page screenshots in ${output}, no AI API requests`);
}finally{await browser.close();}
