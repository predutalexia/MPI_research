#!/usr/bin/env python3
import sys
import time
import argparse
import csv
import logging
from collections import Counter
from pathlib import Path

sys.setrecursionlimit(10000)

class ResolutionSolver:
    def __init__(self):
        self.stats = Counter()
        self.timeout = 300  # seconds

    def solve(self, formula):
        self.stats.clear()
        self.start_time = time.time()
        clauses = set(formula)
        sat = self._resolve(clauses)
        elapsed = time.time() - self.start_time
        return sat, elapsed, dict(self.stats), {}

    def _resolve(self, clauses):
        prev_clause_count = -1
        iteration = 0

        while True:
            if time.time() - self.start_time > self.timeout:
                print(f"[RESOLUTION] Timeout after {self.timeout}s at iteration {iteration}")
                return None

            iteration += 1
            clause_list = list(clauses)
            new_resolvents = set()

            for i in range(len(clause_list)):
                for j in range(i + 1, len(clause_list)):
                    ci, cj = clause_list[i], clause_list[j]
                    for lit in ci:
                        if -lit in cj:
                            self.stats['resolution_steps'] += 1
                            resolvent = (ci - {lit}) | (cj - {-lit})
                            if not resolvent:
                                print(f"[RESOLUTION] Empty clause derived at iteration {iteration}")
                                return False
                            new_resolvents.add(frozenset(resolvent))

            if new_resolvents.issubset(clauses):
                print(f"[RESOLUTION] No new resolvents at iteration {iteration}, terminating with SAT")
                return True

            clauses |= new_resolvents

def load_dimacs(path: Path):
    project_root = Path(__file__).parent.parent.resolve()
    full_path = path if path.is_absolute() else project_root / path
    clauses = []
    with open(full_path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(('c','p','%')):
                continue
            lits = list(map(int, line.split()))
            if lits and lits[-1] == 0:
                lits.pop()
            if lits:
                clauses.append(frozenset(lits))
    return clauses

def run_file(cnf_path: str):
    formula = load_dimacs(Path(cnf_path))
    solver = ResolutionSolver()
    return solver.solve(formula)

def run_benchmark(folder: str, limit: int, output_path: str):
    folder = Path(folder)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.exists():
        try:
            output.unlink()
        except PermissionError:
            logging.error(f"Cannot overwrite {output}: it may be open or read-only.")
            return

    fieldnames = [
        'Filename', 'Expected', 'Result', 'Correct', 'Time',
        'resolution_steps', 'decisions', 'unit_props', 'backtracks', 'pure_literals'
    ]

    with open(output, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for sub in ['sat', 'unsat']:
            expected = 'SAT' if sub == 'satisfiable' else 'UNSAT'
            subdir = folder / sub
            if not subdir.exists():
                logging.warning(f"Missing subfolder: {subdir}, skipping...")
                continue

            for cnf_file in sorted(subdir.glob('*.cnf'))[:limit]:
                sat, elapsed, stats, _ = run_file(str(cnf_file))
                if sat is True:
                    result = 'SAT'
                elif sat is False:
                    result = 'UNSAT'
                else:
                    result = 'TIMEOUT'

                writer.writerow({
                    'Filename':         cnf_file.name,
                    'Expected':         expected,
                    'Result':           result,
                    'Correct':          (result == expected),
                    'Time':             f"{elapsed:.6f}",
                    'resolution_steps': stats.get('resolution_steps', 0),
                    'decisions':        0,
                    'unit_props':       0,
                    'backtracks':       0,
                    'pure_literals':    0,
                })

    print(f"Benchmark complete. Wrote {output}")

def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(description="Resolution SAT Solver")
    subparsers = parser.add_subparsers(dest='command')

    run_p = subparsers.add_parser('run', help='Solve a single CNF file')
    run_p.add_argument('cnf_file', help='Path to CNF DIMACS file')

    bench_p = subparsers.add_parser('benchmark', help='Benchmark CNF files in a folder')
    bench_p.add_argument('folder', help='Path containing satisfiable/unsatisfiable subfolders')
    bench_p.add_argument('--limit', type=int, default=10, help='Max files per subfolder')
    bench_p.add_argument('--output', default='results/resolution/test.csv', help='CSV output path')

    args = parser.parse_args()
    if args.command == 'run':
        sat, elapsed, stats, _ = run_file(args.cnf_file)
        print('SAT' if sat else 'UNSAT' if sat is False else 'TIMEOUT')
        print(f"Time: {elapsed:.3f}s, Stats: {stats}")
    elif args.command == 'benchmark':
        run_benchmark(args.folder, args.limit, args.output)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
