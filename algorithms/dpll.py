#!/usr/bin/env python3
import sys
import time
import argparse
import logging
import csv
from collections import defaultdict, Counter
from pathlib import Path

sys.setrecursionlimit(10000)

def load_dimacs(path: Path):
    clauses = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(('c','p','%')):
                continue
            lits = list(map(int, line.split()))
            if lits and lits[-1] == 0:
                lits = lits[:-1]
            if lits:
                clauses.append(lits)
    return clauses

class FastDPLLSolver:
    def __init__(self, clauses, timeout=300):
        self.clauses = clauses                       
        self.num_vars = max(abs(l) for c in clauses for l in c)
        self.timeout = timeout
        self.stats = Counter()
        self.assignments = {}                         
        self.trail = []                               
        self.levels = []                             
        self.watch_list = defaultdict(list)           
        self.jw_weights = {}                          
        self.start_time = None
        self._init_weights()
        self._init_watches()

    def _init_weights(self):
        self.jw_weights = Counter()
        for clause in self.clauses:
            w = 2 ** (-len(clause))
            for lit in clause:
                self.jw_weights[abs(lit)] += w

    def _init_watches(self):
        for ci, clause in enumerate(self.clauses):
            # watch first two literals (or one)
            if len(clause) > 1:
                lits = clause[:2]
            else:
                lits = clause[:1]
            for lit in lits:
                self.watch_list[lit].append(ci)

    def value_of(self, lit):
        v = self.assignments.get(abs(lit))
        if v is None:
            return None
        return v if lit > 0 else not v

    def new_level(self):
        self.levels.append(len(self.trail))

    def backtrack(self):
        self.stats['backtracks'] += 1
        mark = self.levels.pop()
        while len(self.trail) > mark:
            var = self.trail.pop()
            del self.assignments[var]

    def enqueue(self, lit, is_decision=False):
        var = abs(lit)
        val = lit > 0
        if var in self.assignments:
            return self.assignments[var] == val

        self.assignments[var] = val
        self.trail.append(var)
        if not is_decision:
            self.stats['unit_props'] += 1
        return self._propagate(-lit)

    def _propagate(self, false_lit):
        watchers = list(self.watch_list[false_lit])
        self.watch_list[false_lit].clear()
        for ci in watchers:
            clause = self.clauses[ci]
            # try to find replacement watch
            for alt in clause:
                if alt == false_lit:
                    continue
                if self.value_of(alt) is not False:
                    self.watch_list[alt].append(ci)
                    break
            else:
                # no replacement, clause is unit or conflict
                unassigned = [l for l in clause if self.value_of(l) is None]
                if not unassigned:
                    return False  
                # unit clause
                if not self.enqueue(unassigned[0]):
                    return False
        return True

    def pick_branch_var(self):
        best = None
        best_w = -1.0
        for var, w in self.jw_weights.items():
            if var not in self.assignments and w > best_w:
                best_w = w
                best = var
        # return positive literal by default
        return best

    def solve(self):
        self.start_time = time.time()
        # initial unit clauses
        for ci, clause in enumerate(self.clauses):
            if len(clause) == 1:
                if not self.enqueue(clause[0]):
                    return False, time.time() - self.start_time, dict(self.stats), {}
        # recurse
        sat = self._dpll()
        elapsed = time.time() - self.start_time
        return sat, elapsed, dict(self.stats), {v: self.assignments[v] for v in self.assignments}

    def _dpll(self):
        if time.time() - self.start_time > self.timeout:
            return None
        # SAT
        if len(self.assignments) == self.num_vars:
            return True
        
        self.new_level()
        lit = self.pick_branch_var()
        self.stats['decisions'] += 1
        if self.enqueue(lit, is_decision=True) and self._dpll():
            return True
        self.backtrack()
        self.new_level()
        if self.enqueue(-lit, is_decision=True) and self._dpll():
            return True
        self.backtrack()
        return False

def run_file(cnf_path):
    clauses = load_dimacs(Path(cnf_path))
    solver = FastDPLLSolver(clauses)
    return solver.solve()

def run_benchmark(folder, limit, output_path):
    project_root = Path(__file__).parent.parent.resolve()
    cnf_root      = (project_root / folder).resolve()
    output_file   = (project_root / output_path).resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        try:
            output_file.unlink()
        except PermissionError:
            logging.error(f"Cannot overwrite {output_file}, close it and retry")
            return

    fieldnames = [
        'Filename','Expected','Result','Correct','Time',
        'decisions','unit_props','backtracks'
    ]
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for sub, exp in [('sat','SAT'),('unsat','UNSAT')]:
            subdir = cnf_root / sub
            if not subdir.exists():
                logging.warning(f"Missing {subdir}, skipping")
                continue
            for cnf_file in sorted(subdir.glob('*.cnf'))[:limit]:
                sat, elapsed, stats, model = run_file(str(cnf_file))
                res = 'SAT' if sat else 'UNSAT' if sat is False else 'TIMEOUT'
                writer.writerow({
                    'Filename':   cnf_file.name,
                    'Expected':   exp,
                    'Result':     res,
                    'Correct':    (res == exp),
                    'Time':       f"{elapsed:.6f}",
                    'decisions':  stats.get('decisions',0),
                    'unit_props': stats.get('unit_props',0),
                    'backtracks': stats.get('backtracks',0),
                })
    print(f"Benchmark complete. Results to {output_file}")

def main():
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    parser = argparse.ArgumentParser(description="Fast DPLL Solver")
    sub = parser.add_subparsers(dest='cmd')
    r = sub.add_parser('run')
    r.add_argument('cnf_file')
    b = sub.add_parser('benchmark')
    b.add_argument('folder')
    b.add_argument('--limit', type=int, default=10)
    b.add_argument('--output', default='results/dpll/test.csv')
    args = parser.parse_args()
    if args.cmd == 'run':
        sat, elapsed, stats, model = run_file(args.cnf_file)
        print('SAT' if sat else 'UNSAT' if sat is False else 'TIMEOUT')
        print(f"Time: {elapsed:.3f}s, Stats: {stats}")
    elif args.cmd == 'benchmark':
        run_benchmark(args.folder, args.limit, args.output)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()

print("Wrote FastDPLLSolver to algorithms/dpll.py")
