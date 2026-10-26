"""One-command bounded reproduction; no production purchases."""
import argparse,subprocess,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser();p.add_argument('--llm-budget-usd',type=float,default=0);p.add_argument('--reports-only',action='store_true');p.add_argument('--sandbox-booking',action='store_true',help='Documented LiteAPI sand_ control only');a=p.parse_args()
 if not 0<=a.llm_budget_usd<=5:p.error('Authorized maximum is $5')
 failures=[]
 def run(script,*args):
  r=subprocess.run([sys.executable,*script,*args],cwd=ROOT)
  if r.returncode:failures.append({'command':script,'returncode':r.returncode})
 run(['-m','unittest','discover','-s','tests','-v'])
 if not a.reports_only:
  if not (ROOT/'.mcp-venv/bin/python').exists():run(['scripts/setup_community_mcp.py'])
  for script in ['discover_mcp','run_rest','run_mcp','run_followups','run_community_mcp','run_extra_checks','run_tutu','run_tutu_followup']:run(['scripts/'+script+'.py'])
  if a.sandbox_booking:run(['scripts/run_sandbox.py'])
 for script in ['normalize_results','normalize_tutu']:run(['scripts/'+script+'.py'])
 if a.llm_budget_usd and not a.reports_only:run(['scripts/run_llm_experiments.py'],'--budget-usd',str(a.llm_budget_usd),'--profile','orchestrated')
 if a.llm_budget_usd and not a.reports_only:run(['scripts/run_llm_tutu_update.py'])
 run(['scripts/build_reports.py'])
 (ROOT/'reports/reproduction_status.json').write_text(json.dumps({'process_failures':failures,'reports_only':a.reports_only},indent=2)+'\n')
 raise SystemExit(bool(failures))
if __name__=='__main__':main()
