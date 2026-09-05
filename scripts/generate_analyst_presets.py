"""Generate real, validated GLM reports for existing presets before homepage capture.

Run from the application checkout with GLM_API_KEY set in the environment/.env.
No credentials are accepted as command-line arguments or printed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import create_app
from app.services.analyst import configured, digest, pack, system_prompt, validate_report
from app.services.analyst_facts import load_preset_facts
from app.services.analyst_collections import scoped_facts, saved_preset_report, preset_report_path
from app.services.glm import GlmClient, GlmError


async def generate(presets, locales, styles, *, force=False):
    app = create_app()
    if not configured(app):
        raise SystemExit('GLM_API_KEY is required to generate real example reports')
    settings = app.state.settings
    semaphore = asyncio.Semaphore(settings.analyst_concurrency)
    cooldown_until = 0.0
    failures = []
    async with GlmClient(api_key=settings.glm_api_key.get_secret_value(), model=settings.glm_model, base_url=settings.glm_base_url, reasoning_effort=settings.glm_reasoning_effort, temperature=settings.glm_temperature, max_tokens=settings.glm_max_tokens, timeout=settings.glm_timeout_seconds) as client:
        async def variant(preset_id, full_facts, locale, style, subject_id):
            nonlocal cooldown_until
            label = f'{preset_id} {locale} {style} {subject_id or "session"}'
            if not force and saved_preset_report(app, preset_id, full_facts, locale, style, subject_id).report:
                print(f'Reused verified {label}', flush=True)
                return
            facts = scoped_facts(full_facts, subject_id).model_dump(mode='json')
            payload = {'facts': facts, 'memory': {}, 'locale': locale, 'style': style, 'subject_id': subject_id}
            for attempt in range(3):
                try:
                    async with semaphore:
                        while cooldown_until > asyncio.get_running_loop().time():
                            await asyncio.sleep(cooldown_until - asyncio.get_running_loop().time())
                        response = await client.complete_json([{'role':'system','content':system_prompt(payload,report=True)}, {'role':'user','content':pack({'facts':facts,'memory':{}})}], request_id=f'preset-{uuid4()}')
                        body = validate_report(response.data, facts, {})
                    report = {**body.model_dump(), 'id':str(uuid4()), 'model':settings.glm_model, 'locale':locale, 'style':style, 'created_at':datetime.now(timezone.utc).isoformat()}
                    destination = preset_report_path(settings, preset_id, locale, style, subject_id)
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    temporary = destination.with_suffix('.json.tmp')
                    temporary.write_text(json.dumps({'verified':True, 'subject_id':subject_id, 'facts_hash':digest(facts), 'report':report, 'usage':response.usage}, ensure_ascii=False,indent=2),encoding='utf-8')
                    temporary.replace(destination)
                    print(f'Saved verified {label}', flush=True)
                    return
                except (GlmError, ValueError) as error:
                    delay = 2 ** (attempt + 1)
                    if isinstance(error, GlmError) and error.code == 'rate_limited':
                        delay = max(30 * 2 ** attempt, error.retry_after_seconds or 0)
                        cooldown_until = max(cooldown_until, asyncio.get_running_loop().time() + delay)
                    if attempt == 2 or isinstance(error, GlmError) and not error.retryable:
                        failures.append(label)
                        print(f'Failed {label}: {error.code if isinstance(error, GlmError) else "invalid_report"}', flush=True)
                        return
                    await asyncio.sleep(delay)
        work = []
        for preset_id in presets:
            facts = load_preset_facts(app, preset_id)
            for locale in locales:
                for subject_id in [None, *(s.id for s in facts.subjects)]:
                    for style in styles:
                        work.append(variant(preset_id, facts, locale, style, subject_id))
        await asyncio.gather(*work)
    if failures:
        raise SystemExit(f'{len(failures)} variants failed, rerun to fill only missing reports')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--presets',nargs='+',default=['quick-demo'],choices=['quick-demo','mixed-actions','verified-outcome','layup-demo'])
    parser.add_argument('--locales',nargs='+',default=['zh','en'],choices=['zh','en'])
    parser.add_argument('--styles',nargs='+',default=['coach','roast'],choices=['coach','roast'])
    parser.add_argument('--force', action='store_true', help='Replace existing verified reports instead of filling missing variants')
    args=parser.parse_args()
    asyncio.run(generate(args.presets,args.locales,args.styles,force=args.force))
