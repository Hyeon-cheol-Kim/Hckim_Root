import re
import csv
import sys
from collections import defaultdict


def parse_ufs_trace(filepath):
    pending = {}
    results = []

    with open(filepath) as f:
        for line in f:
            if 'block_rq_issue' in line:
                m = re.search(
                    r'(\S+)-(\d+)\s+\[(\d+)\].*?(\d+\.\d+): block_rq_issue:'
                    r'.*?(?:dev=)?(\d+,\d+)\s+sector=(\d+)\s+nr_sector=(\d+)\s+rwbs=(\S+)',
                    line
                )
                if m:
                    comm, pid, cpu, ts, dev, sector, nr_sector, rwbs = m.groups()
                    chunk_kb = int(nr_sector) * 512 / 1024
                    pending[sector] = {
                        'comm': comm,
                        'pid': pid,
                        'cpu': cpu,
                        'issue_ts': float(ts),
                        'dev': dev,
                        'chunk_kb': chunk_kb,
                        'rwbs': rwbs,
                        'is_meta': 'M' in rwbs or 'S' in rwbs,
                    }

            elif 'block_rq_complete' in line:
                m = re.search(
                    r'(\d+\.\d+): block_rq_complete:.*?sector=(\d+).*?error=(\d+)',
                    line
                )
                if m:
                    ts, sector, error = m.groups()
                    if sector in pending:
                        ev = pending.pop(sector)
                        latency_us = (float(ts) - ev['issue_ts']) * 1e6
                        results.append({**ev, 'latency_us': latency_us, 'error': error})

    return results


def write_raw_csv(results, path):
    """raw I/O 이벤트 전체를 한 행씩 기록"""
    fieldnames = [
        'comm', 'pid', 'cpu', 'dev',
        'chunk_kb', 'rwbs', 'is_meta',
        'issue_ts', 'latency_us', 'error',
    ]
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in fieldnames})
    print(f"[raw]  {path}  ({len(results)} rows)")


def write_chunk_summary_csv(results, path):
    """chunk size별 집계"""
    by_chunk = defaultdict(list)
    for r in results:
        by_chunk[f"{r['chunk_kb']:.0f}KB"].append(r)

    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['chunk_size', 'total_ios', 'data_ios', 'meta_ios',
                         'avg_latency_us', 'min_latency_us', 'max_latency_us'])
        for chunk_size in sorted(by_chunk.keys(), key=lambda x: float(x[:-2])):
            items = by_chunk[chunk_size]
            lats = [i['latency_us'] for i in items]
            data_cnt = sum(1 for i in items if not i['is_meta'])
            meta_cnt = sum(1 for i in items if i['is_meta'])
            writer.writerow([
                chunk_size,
                len(items),
                data_cnt,
                meta_cnt,
                f"{sum(lats)/len(lats):.2f}",
                f"{min(lats):.2f}",
                f"{max(lats):.2f}",
            ])
    print(f"[chunk summary]  {path}  ({len(by_chunk)} chunk sizes)")


def write_pid_summary_csv(results, path):
    """fio 프로세스(PID)별 집계 + WAF"""
    fio_results = [r for r in results if 'fio' in r['comm']]
    by_pid = defaultdict(list)
    for r in fio_results:
        by_pid[r['pid']].append(r)

    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['pid', 'comm', 'total_ios', 'data_ios', 'meta_ios',
                         'avg_latency_us', 'min_latency_us', 'max_latency_us',
                         'total_data_kb', 'total_written_kb', 'waf'])
        for pid, items in sorted(by_pid.items()):
            lats = [i['latency_us'] for i in items]
            data_items = [i for i in items if not i['is_meta']]
            meta_items = [i for i in items if i['is_meta']]
            total_data_kb   = sum(i['chunk_kb'] for i in data_items)
            total_written_kb = sum(i['chunk_kb'] for i in items)
            waf = total_written_kb / total_data_kb if total_data_kb else 0
            writer.writerow([
                pid,
                items[0]['comm'],
                len(items),
                len(data_items),
                len(meta_items),
                f"{sum(lats)/len(lats):.2f}",
                f"{min(lats):.2f}",
                f"{max(lats):.2f}",
                f"{total_data_kb:.1f}",
                f"{total_written_kb:.1f}",
                f"{waf:.3f}",
            ])
    print(f"[pid summary]  {path}  ({len(by_pid)} pids)")


def write_chunk_per_pid_csv(results, path):
    """PID × chunk size 교차 집계"""
    fio_results = [r for r in results if 'fio' in r['comm']]
    table = defaultdict(lambda: defaultdict(list))
    chunk_sizes = set()

    for r in fio_results:
        key = f"{r['chunk_kb']:.0f}KB"
        table[r['pid']][key].append(r['latency_us'])
        chunk_sizes.add(key)

    sorted_chunks = sorted(chunk_sizes, key=lambda x: float(x[:-2]))

    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        header = ['pid']
        for c in sorted_chunks:
            header += [f"{c}_count", f"{c}_avg_lat_us"]
        writer.writerow(header)

        for pid, chunks in sorted(table.items()):
            row = [pid]
            for c in sorted_chunks:
                lats = chunks.get(c, [])
                row.append(len(lats))
                row.append(f"{sum(lats)/len(lats):.2f}" if lats else '')
            writer.writerow(row)
    print(f"[pid x chunk]  {path}  ({len(table)} pids x {len(sorted_chunks)} chunk sizes)")


if __name__ == '__main__':
    trace_file = sys.argv[1] if len(sys.argv) > 1 else 'ufs_trace.txt'
    out_prefix = sys.argv[2] if len(sys.argv) > 2 else 'ufs_result'

    print(f"Parsing: {trace_file}")
    results = parse_ufs_trace(trace_file)
    print(f"Total completed IOs: {len(results)}\n")

    write_raw_csv          (results, f"{out_prefix}_raw.csv")
    write_chunk_summary_csv(results, f"{out_prefix}_chunk_summary.csv")
    write_pid_summary_csv  (results, f"{out_prefix}_pid_summary.csv")
    write_chunk_per_pid_csv(results, f"{out_prefix}_pid_x_chunk.csv")

    print("\nDone.")
