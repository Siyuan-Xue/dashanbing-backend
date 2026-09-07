"""Queue and generate original preset variants through the global durable AI pool.

Requires an upgraded local database. No credentials are accepted in arguments or
printed. Existing successful variants are never overwritten; failed variants need
an explicit, audited administrator repair. This command never resets retry counts.
"""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sqlmodel import Session
from app.main import create_app
from app.admin_models import AdminPresetJob
from app.services.analyst import configured
from app.services.analyst_facts import load_preset_facts
from app.services.analyst_collections import scoped_facts
from app.services.admin import initialize_settings
from app.services.admin_presets import enqueue_preset,run_preset


async def generate(presets,locales,styles,*,force=False):
    if force:
        raise SystemExit('Overwriting successful variants is disabled; use an audited administrator repair for failed variants')
    app=create_app()
    if not configured(app):
        raise SystemExit('GLM_API_KEY is required to generate real example reports')
    initialize_settings(app)
    ids=[]
    for preset_id in presets:
        full=load_preset_facts(app,preset_id)
        for locale in locales:
            for subject_id in [None,*(subject.id for subject in full.subjects)]:
                for style in styles:
                    ids.append(enqueue_preset(app,preset_id,scoped_facts(full,subject_id).model_dump(mode='json'),locale=locale,style=style,subject_id=subject_id))
    async def worker(job_id):
        while True:
            with Session(app.state.engine) as session:
                row=session.get(AdminPresetJob,job_id)
                status=row.status
            if status in {'completed','failed'}:
                return status
            if not await run_preset(app,job_id):
                await asyncio.sleep(0.5)
    states=await asyncio.gather(*(worker(job_id) for job_id in ids))
    failed=states.count('failed')
    print(f'Completed {len(states)-failed}; failed {failed}',flush=True)
    if failed:
        raise SystemExit('Failed variants require explicit administrator repair')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--presets',nargs='+',default=['quick-demo'],choices=['quick-demo','mixed-actions','verified-outcome','layup-demo'])
    parser.add_argument('--locales',nargs='+',default=['zh','en'],choices=['zh','en'])
    parser.add_argument('--styles',nargs='+',default=['coach','roast'],choices=['coach','roast'])
    args=parser.parse_args()
    asyncio.run(generate(args.presets,args.locales,args.styles))
