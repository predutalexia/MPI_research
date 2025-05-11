#!/usr/bin/env python3
import sys
import time
import argparse
import logging
import csv
from collections import Counter
from pathlib import Path

sys.setrecursionlimit(10000)

def negate(literal: int) -> int:
    return -literal

class DPSolver:
    def __init__(self):
        #unit_props, pure_literals, eliminations, resolution_steps
        self.stats = Counter()
        self.model = {}

    def solve(self, formula):
        self.stats.clear()
        self.model.clear()
        self.start_time = time.time()
        self.timeout = 300  # seconds

        sat, assignments = self._dp(set(formula), {})
        elapsed = time.time() - self.start_time
        if sat is True:
            self.model.update(assignments)
        return sat, elapsed, dict(self.stats), self.model

    def _dp(self, phi, assignments):
        if time.time() - self.start_time > self.timeout:
            return None, {}

        # 1. Unit propagation
        while True:
            units = {next(iter(c)) for c in phi if len(c) == 1}
            if not units:
                break
            for lit in units:
                self.stats['unit_props'] += 1
                assignments[abs(lit)] = (lit > 0)
                new_phi = set()
                for c in phi:
                    if lit in c:
                        continue
                    if negate(lit) in c:
                        red = c - {negate(lit)}
                        if not red:
                            return False, {}
                        new_phi.add(frozenset(red))
                    else:
                        new_phi.add(c)
                phi = new_phi

        # 2. Pure-literal elimination
        lits = {l for c in phi for l in c}
        pures = {l for l in lits if negate(l) not in lits}
        for lit in pures:
            self.stats['pure_literals'] += 1
            assignments[abs(lit)] = (lit > 0)
            phi = {c for c in phi if lit not in c}
            if any(len(c) == 0 for c in phi):
             return False, {}


        # 3. Termination checks
        if not phi:
            return True, assignments
        if frozenset() in phi:
            return False, {}

        # 4. Resolution/elimination step
        lits = {l for c in phi for l in c}
        candidates = {l for l in lits if negate(l) in lits}
        if not candidates:
            return False, {}
        lit = next(iter(candidates))
        self.stats['eliminations'] += 1

        pos_clauses = [c for c in phi if lit in c]
        neg_clauses = [c for c in phi if negate(lit) in c]
        resolvents = set()
        for c1 in pos_clauses:
            for c2 in neg_clauses:
                self.stats['resolution_steps'] += 1
                resolvent = (c1 - {lit}) | (c2 - {negate(lit)})
                resolvents.add(frozenset(resolvent))

        phi = {c for c in phi if lit not in c and negate(lit) not in c} | resolvents
        return self._dp(phi, assignments)

# DIMACS loader
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
    solver = DPSolver()
    return solver.solve(formula)

def run_benchmark(folder: str, limit: int, output_path: str):
    project_root = Path(__file__).parent.parent.resolve()
    cnf_root = (project_root / folder).resolve()
    output_file = (project_root / output_path).resolve()

    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_file.exists():
        try:
            output_file.unlink()
        except PermissionError:
            logging.error(f"Cannot overwrite {output_file}. Close any open program using it.")
            return

    fieldnames = [
        'Filename','Expected','Result','Correct','Time',
        'unit_props','pure_literals','eliminations','resolution_steps'
    ]
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for sub in ['satisfiable','unsatisfiable']:
            expected = 'SAT' if sub == 'satisfiable' else 'UNSAT'
            subdir = cnf_root / sub
            if not subdir.exists():
                logging.warning(f"Missing folder: {subdir}")
                continue

            for cnf_file in sorted(subdir.glob('*.cnf'))[:limit]:
                sat, elapsed, stats, _ = run_file(str(cnf_file))
                result = 'SAT' if sat is True else 'UNSAT' if sat is False else 'TIMEOUT'

                writer.writerow({
                    'Filename':         cnf_file.name,
                    'Expected':         expected,
                    'Result':           result,
                    'Correct':          (result == expected),
                    'Time':             f"{elapsed:.6f}",
                    'unit_props':       stats.get('unit_props', 0),
                    'pure_literals':    stats.get('pure_literals', 0),
                    'eliminations':     stats.get('eliminations', 0),
                    'resolution_steps': stats.get('resolution_steps', 0),
                })

    print(f"Benchmark complete. Wrote {output_file}")


def main():
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="DP SAT Solver")
    sub = parser.add_subparsers(dest='command')

    run_p = sub.add_parser('run', help='Solve a single CNF file')
    run_p.add_argument('cnf_file', help='Path to DIMACS CNF file')
    run_p.add_argument('--time', action='store_true', help='Print timing and stats')

    bench_p = sub.add_parser('benchmark', help='Benchmark CNF files in a folder')
    bench_p.add_argument('folder', help='Path with satisfiable/unsatisfiable subfolders')
    bench_p.add_argument('--limit', type=int, default=10, help='Max files per subfolder')
    bench_p.add_argument('--output', default='results/dp/test.csv', help='CSV output path')

    args = parser.parse_args()
    if args.command == 'run':
        sat, elapsed, stats, model = run_file(args.cnf_file)
        print('SAT' if sat else 'UNSAT' if sat is False else 'TIMEOUT')
        if args.time:
            print(f"Time: {elapsed:.3f}s, Stats: {stats}")
    elif args.command == 'benchmark':
        run_benchmark(args.folder, args.limit, args.output)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()


