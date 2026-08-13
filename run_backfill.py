"""
run_backfill.py — รัน backfill ให้จบ โดยไม่ติด timeout ของ Vercel

มี 2 โหมด:

1) local (ค่าเริ่มต้น) — รัน run_daily_export() ตรงๆ บนเครื่องนี้
   ไม่มีข้อจำกัดเรื่องเวลาเลย เหมาะกับการซ่อมข้อมูลย้อนหลังหลายเดือน
   ต้องมี .env ที่มี POSTGRES_URL_NON_POOLING, TURSO_* ครบ

       python3 run_backfill.py --start 01/07/2026 --end 31/07/2026

2) remote — ยิง API ของ production แล้ววน /backfill-continue จนจบ
   เหมาะเวลาอยากให้ข้อมูลถูกเขียนจากฝั่ง production

       python3 run_backfill.py --mode remote \
           --start 01/07/2026 --end 31/07/2026 \
           --base-url https://report-trade.vercel.app \
           --secret "$CRON_SECRET"

ทั้งสองโหมดปลอดภัยต่อการรันซ้ำ (run_daily_export ล้างข้อมูลของ zone+วันนั้น
ก่อน insert ใหม่เสมอ) ถ้าหยุดกลางคันแล้วรันใหม่ ข้อมูลจะไม่ซ้ำ
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def parse_date(s):
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(f'รูปแบบวันที่ไม่ถูกต้อง: {s} (ใช้ DD/MM/YYYY หรือ YYYY-MM-DD)')


def run_local(start_date, end_date, dry_run):
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    from auto_daily_export import run_daily_export

    total_days = (end_date - start_date).days + 1
    dates = [start_date + timedelta(days=i) for i in range(total_days)]

    print("=" * 70)
    print(f"🔁 Backfill (local) {start_date} -> {end_date}  ({total_days} วัน)")
    print("=" * 70)

    if dry_run:
        for d in dates:
            print(f"   • {d.strftime('%d/%m/%Y')}")
        print(f"\n(dry run) จะ re-sync ทั้งหมด {total_days} วัน")
        return 0

    started = time.time()
    total_records = 0
    failed = []

    for idx, d in enumerate(dates, 1):
        day_str = d.strftime('%d/%m/%Y')
        day_started = time.time()
        print(f"\n[{idx}/{total_days}] {day_str}")
        try:
            res = run_daily_export(force=True,
                                   target_dt=datetime.combine(d, datetime.min.time()))
            records = res.get('total_records', 0) or 0
            total_records += records
            if res.get('sync_completed'):
                print(f"   ✅ {records:,} records ({time.time() - day_started:.0f}s)")
            else:
                failed.append(day_str)
                print(f"   ⚠️ sync ไม่สมบูรณ์: errors={res.get('total_errors')}, "
                      f"warnings={res.get('total_warnings')}")
        except Exception as e:
            failed.append(day_str)
            print(f"   ❌ {e}")

    elapsed = time.time() - started
    print("\n" + "=" * 70)
    print(f"🔁 เสร็จใน {elapsed / 60:.1f} นาที | {total_records:,} records")
    if failed:
        print(f"❌ วันที่ล้มเหลว {len(failed)} วัน: {', '.join(failed[:20])}")
        print("   รันสคริปต์นี้ซ้ำเฉพาะช่วงที่ล้มเหลวได้เลย (idempotent)")
    else:
        print("✅ สำเร็จครบทุกวัน")
    print("=" * 70)
    return 1 if failed else 0


def run_remote(start_date, end_date, dry_run, base_url, secret, max_rounds):
    import requests

    base_url = base_url.rstrip('/')
    headers = {'Content-Type': 'application/json'}
    if secret:
        headers['Authorization'] = f'Bearer {secret}'

    print("=" * 70)
    print(f"🔁 Backfill (remote) {start_date} -> {end_date}")
    print(f"   target: {base_url}")
    print("=" * 70)

    resp = requests.post(
        f'{base_url}/api/admin/backfill-range',
        headers=headers,
        json={
            'date_start': start_date.strftime('%d/%m/%Y'),
            'date_end': end_date.strftime('%d/%m/%Y'),
            'dry_run': dry_run,
        },
        timeout=600,
    )
    data = resp.json()

    if resp.status_code != 200 or not data.get('job_id'):
        if dry_run:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        print(f"❌ เริ่ม job ไม่สำเร็จ ({resp.status_code}): "
              f"{data.get('error') or data}")
        return 1

    job_id = data['job_id']
    print(f"📋 job_id = {job_id}")

    rounds = 0
    while True:
        print(f"   {data.get('days_done', 0)}/{data.get('total_days', 0)} วัน "
              f"({data.get('progress_pct', 0)}%) | {data.get('total_records', 0):,} records")

        if data.get('completed'):
            break

        rounds += 1
        if rounds > max_rounds:
            print(f"⚠️ ครบ {max_rounds} รอบแล้วยังไม่จบ — หยุดไว้ก่อน")
            print(f"   ทำต่อได้ด้วย: --continue-job {job_id}")
            return 1

        resp = requests.post(
            f'{base_url}/api/admin/backfill-continue',
            headers=headers, json={'job_id': job_id}, timeout=600,
        )
        if resp.status_code != 200:
            print(f"❌ continue ล้มเหลว ({resp.status_code}): {resp.text[:300]}")
            print(f"   ทำต่อได้ด้วย: --continue-job {job_id}")
            return 1
        data = resp.json()

    print("\n" + "=" * 70)
    print(f"✅ เสร็จ: {data.get('days_done')} วัน | "
          f"{data.get('total_records', 0):,} records")
    if data.get('days_failed'):
        print(f"❌ วันที่ล้มเหลว: {data['days_failed']} วัน — "
              f"ดูรายละเอียดที่ /api/admin/backfill-status?job_id={job_id}")
    print("=" * 70)
    return 1 if data.get('days_failed') else 0


def continue_remote(job_id, base_url, secret, max_rounds):
    import requests

    base_url = base_url.rstrip('/')
    headers = {'Content-Type': 'application/json'}
    if secret:
        headers['Authorization'] = f'Bearer {secret}'

    print(f"🔁 ทำ job {job_id} ต่อ")
    for rounds in range(max_rounds):
        resp = requests.post(f'{base_url}/api/admin/backfill-continue',
                             headers=headers, json={'job_id': job_id}, timeout=600)
        if resp.status_code != 200:
            print(f"❌ continue ล้มเหลว ({resp.status_code}): {resp.text[:300]}")
            return 1
        data = resp.json()
        print(f"   {data.get('days_done', 0)}/{data.get('total_days', 0)} วัน "
              f"({data.get('progress_pct', 0)}%)")
        if data.get('completed'):
            print(f"✅ เสร็จ: {data.get('total_records', 0):,} records")
            return 1 if data.get('days_failed') else 0
    print(f"⚠️ ครบ {max_rounds} รอบแล้วยังไม่จบ")
    return 1


def main():
    p = argparse.ArgumentParser(description='รัน backfill ให้จบโดยไม่ติด timeout')
    p.add_argument('--mode', choices=['local', 'remote'], default='local')
    p.add_argument('--start', type=parse_date, help='วันเริ่ม (DD/MM/YYYY)')
    p.add_argument('--end', type=parse_date, help='วันสิ้นสุด (DD/MM/YYYY)')
    p.add_argument('--dry-run', action='store_true', help='แสดงวันที่ที่จะรัน ไม่ sync จริง')
    p.add_argument('--base-url', default=os.environ.get('BACKFILL_BASE_URL',
                                                        'https://report-trade.vercel.app'))
    p.add_argument('--secret', default=os.environ.get('CRON_SECRET', ''))
    p.add_argument('--max-rounds', type=int, default=200,
                   help='จำนวนรอบ continue สูงสุด (โหมด remote)')
    p.add_argument('--continue-job', default='', help='ทำ job เดิมต่อ (โหมด remote)')
    args = p.parse_args()

    if args.continue_job:
        return continue_remote(args.continue_job, args.base_url, args.secret, args.max_rounds)

    if not args.start or not args.end:
        p.error('ต้องระบุ --start และ --end (หรือใช้ --continue-job)')
    if args.start > args.end:
        p.error('--start ต้องไม่เกิน --end')

    if args.mode == 'local':
        return run_local(args.start, args.end, args.dry_run)
    return run_remote(args.start, args.end, args.dry_run,
                      args.base_url, args.secret, args.max_rounds)


if __name__ == '__main__':
    sys.exit(main())
