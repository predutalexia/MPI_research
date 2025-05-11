#!/usr/bin/env python3
import argparse
import csv
import sys
import traceback
from pathlib import Path

# algorithms package is on sys.path
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

from algorithms.dpll      import DPLLSolver
from algorithms.dp        import DPSolver
from algorithms.resolution import ResolutionSolver

SOLVERS = {
    'resolution': ResolutionSolver,
    'dp':         DPSolver,
    'dpll':       DPLLSolver,
}

# CNF sizes 
SIZES      = ['test','small','medium','large']
EXPECT_DIR = {'satisfiable':'SAT','unsatisfiable':'UNSAT'}

# output CSV columns
FIELDNAMES = [
    'Filename','Expected','Result','Correct','Time',
    'Decisions','UnitProps','Backtracks','ResolutionSteps'
]

def load_dimacs(path: Path):
    clauses = []
    with open(path, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in ('c','p','%'):
                continue
            nums = list(map(int, line.split()))
            if nums and nums[-1] == 0:
                nums.pop()
            if nums:
                clauses.append(frozenset(nums))
    return clauses

def run_all(selected_solver: str = None):
    cnf_root     = BASE_DIR / 'cnfs'
    results_root = BASE_DIR / 'results'

    to_run = {selected_solver:SOLVERS[selected_solver]} if selected_solver else SOLVERS

    for name, SolverCls in to_run.items():
        solver = SolverCls()
        out_dir = results_root / name
        out_dir.mkdir(parents=True, exist_ok=True)

        for size in SIZES:
            csv_path = out_dir / f"{size}.csv"
            with open(csv_path, 'w', newline='') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
                writer.writeheader()

                for sub, expected in EXPECT_DIR.items():
                    folder = cnf_root / size / sub
                    if not folder.exists():
                        continue

                    for cnf in sorted(folder.glob('*.cnf')):
                        try:
                            formula = load_dimacs(cnf)
                            sat, elapsed, stats, _ = solver.solve(formula)
                            if   sat is True:  result = 'SAT'
                            elif sat is False: result = 'UNSAT'
                            else:              result = 'TIMEOUT'
                            correct = (result == expected)
                        except Exception as e:
                            result = 'ERROR'
                            elapsed = 0.0
                            stats   = {}
                            correct = False
                            print(f"[ERROR][{name}][{size}/{sub}] {cnf.name}: {e}")
                            traceback.print_exc()

                        row = {
                            'Filename':        cnf.name,
                            'Expected':        expected,
                            'Result':          result,
                            'Correct':         correct,
                            'Time':            f"{elapsed:.6f}",
                            'Decisions':       stats.get('decisions', 0),
                            'UnitProps':       stats.get('unit_props', 0),
                            'Backtracks':      stats.get('backtracks', 0),
                            'ResolutionSteps': stats.get('resolution_steps', 0),
                        }
                        writer.writerow(row)
                        print(f"[{name.upper()}][{size}/{sub}] {cnf.name}: {result} (time {elapsed:.3f}s)")

if __name__ == '__main__':
    p = argparse.ArgumentParser(description="Run SAT solver benchmarks")
    p.add_argument('solver', nargs='?', choices=SOLVERS.keys(),
                   help="(Optional) name of solver to run (default: all)")
    args = p.parse_args()
    run_all(selected_solver=args.solver)
