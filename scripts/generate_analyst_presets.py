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
from app.services.glm import GlmClient


async def generate(presets, locales, styles):
    app = create_app()
    if not configured(app):
        raise SystemExit('GLM_API_KEY is required to generate real example reports')
    settings = app.state.settings
    async with GlmClient(api_key=settings.glm_api_key.get_secret_value(), model=settings.glm_model, base_url=settings.glm_base_url, reasoning_effort=settings.glm_reasoning_effort, temperature=settings.glm_temperature, max_tokens=settings.glm_max_tokens, timeout=settings.glm_timeout_seconds) as client:
        for preset_id in presets:
            facts = load_preset_facts(app, preset_id).model_dump(mode='json')
            for locale in locales:
                for style in styles:
                    payload = {'facts': facts, 'memory': {}, 'locale': locale, 'style': style}
                    response = await client.complete_json([{'role':'system','content':system_prompt(payload,report=True)},{'role':'user','content':pack({'facts':facts,'memory':{}})}],request_id=f'preset-{uuid4()}')
                    body = validate_report(response.data, facts, {})
                    report = {**body.model_dump(), 'id':str(uuid4()), 'model':settings.glm_model, 'locale':locale, 'style':style, 'created_at':datetime.now(timezone.utc).isoformat()}
                    destination = settings.runtime_root / 'analyst-presets' / preset_id / f'{locale}-{style}.json'
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    temporary = destination.with_suffix('.json.tmp')
                    temporary.write_text(json.dumps({'verified':True,'facts_hash':digest(facts),'report':report,'usage':response.usage},ensure_ascii=False,indent=2),encoding='utf-8')
                    temporary.replace(destination)
                    print(f'Saved verified {preset_id} {locale} {style} report')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--presets',nargs='+',default=['quick-demo'],choices=['quick-demo','mixed-actions','verified-outcome','layup-demo'])
    parser.add_argument('--locales',nargs='+',default=['zh','en'],choices=['zh','en'])
    parser.add_argument('--styles',nargs='+',default=['coach'],choices=['coach','roast'])
    args=parser.parse_args()
    asyncio.run(generate(args.presets,args.locales,args.styles))
