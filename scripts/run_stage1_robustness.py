from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import spearmanr
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from fleet_sim.experiments.stage1_research import (_dynamic_assurance_outcome,_fit_logistic,_predict_logistic,_roc_auc,_weighted_attack_operator,_weighted_spectral_radius,_simulate_weighted_sir,simulate_admission_trajectory)
from fleet_sim.graphs.factory import build_graph,spectral_radius
OUT=ROOT/'results'/'stage1_robustness';OUT.mkdir(parents=True,exist_ok=True)

# NH1 seed robustness
n1=[]
for seed in [7101,7102,7103,7104,7105,7106,7107,7108]:
 rng=np.random.default_rng(seed);X=rng.uniform(.45,.98,(1800,7));names=['cp','contain','obs','sup','rev','timing','mission_inv'];rows=[]
 for x in X:
  y,_,_=_dynamic_assurance_outcome(x,n_agents=10000,rng=rng);split='test' if (.55<x[2]<.82 and x[4]>.68 and x[0]<.86) else 'train';rows.append([*x,y,split])
 d=pd.DataFrame(rows,columns=names+['y','split'])
 def mat(fr):
  return np.column_stack([fr[names].values,fr.obs*fr.contain,fr.contain*fr.rev,fr.rev*fr.cp,fr.obs*fr.sup,fr.timing*fr.mission_inv])
 tr=d[d.split=='train'];te=d[d.split=='test'];w=_fit_logistic(mat(tr),tr.y.values);p=_predict_logistic(mat(te),w)
 n1.append({'seed':seed,'auc_coupled':_roc_auc(te.y.values,p),'auc_baseline':_roc_auc(te.y.values,te[names].max(axis=1).values),'test_n':len(te),'failure_rate':te.y.mean()})
n1=pd.DataFrame(n1);n1['auc_delta']=n1.auc_coupled-n1.auc_baseline;n1.to_csv(OUT/'nh1_seed_robustness.csv',index=False)

# NH2 independent graph-seed robustness on refined matched-auth design
n2=[]
for block in [8101,8102,8103,8104]:
 n=140;reps=15;rows=[];sid=0
 auth_specs=[('rr4','random_regular',{'degree':4}),('rr8','random_regular',{'degree':8}),('ba2','barabasi_albert',{'attachment':2}),('h6','hierarchical',{'span':6})]
 dep_specs=[('rr3','random_regular',{'degree':3},'train'),('rr10','random_regular',{'degree':10},'train'),('er3','erdos_renyi',{'degree':3},'train'),('er12','erdos_renyi',{'degree':12},'train'),('ba1','barabasi_albert',{'attachment':1},'test'),('ba5','barabasi_albert',{'attachment':5},'test'),('h4','hierarchical',{'span':4},'test'),('h12','hierarchical',{'span':12},'test')]
 for ai,(an,at,akw) in enumerate(auth_specs):
  gab=build_graph(n,at,seed=block*10+ai,**akw);ga=gab.materialize();raw=spectral_radius(gab);gc=build_graph(n,'random_regular',seed=block*10+100+ai,degree=6).materialize();gs=build_graph(n,'hierarchical',seed=block*10+200+ai,span=8).materialize()
  for di,(dn,dt,dkw,split) in enumerate(dep_specs):
   gd=build_graph(n,dt,seed=block*10+300+ai*20+di,**dkw).materialize();gx=_weighted_attack_operator(ga,gc,gd,gs);ar=_weighted_spectral_radius(gx)
   for ratio in (.2,.3,.4,.5):
    ev=[]
    for rep in range(reps):ev.append(_simulate_weighted_sir(gx,beta=ratio*.3,gamma=.3,seed=block*100000+sid*100+rep)[1])
    rows.append({'sid':sid,'split':split,'raw':raw*ratio,'attack':ar*ratio,'ever':np.mean(ev)});sid+=1
 d=pd.DataFrame(rows);tr=d[d.split=='train'];te=d[d.split=='test'];m={}
 for col in ['raw','attack']:
  coef=np.linalg.lstsq(np.c_[np.ones(len(tr)),tr[col]],tr.ever,rcond=None)[0];ph=np.c_[np.ones(len(te)),te[col]]@coef;m[col+'_mae']=np.mean(abs(ph-te.ever));m[col+'_rho']=spearmanr(te[col],te.ever).statistic
 n2.append({'seed_block':block,**m,'mae_improvement':(m['raw_mae']-m['attack_mae'])/m['raw_mae']})
n2=pd.DataFrame(n2);n2.to_csv(OUT/'nh2_seed_robustness.csv',index=False)

# NH4 neighborhood robustness
n4=[]
for cp in [150.,165.,180.]:
 for sup in [24.,27.,30.]:
  for ramp in [160.,180.,200.]:
   rates={}
   margins={}
   for profile in ['step','staged']:
    bad=[];mm=[]
    for rep in range(20):
     d=simulate_admission_trajectory(profile,seed=9100+rep,cp_capacity_ops_s=cp,sup_capacity_reviews_s=sup,ramp_duration_s=ramp)
     mm.append(float(d.assurance_margin.min()));bad.append(float(d.assurance_margin.min()<0))
    rates[profile]=np.mean(bad);margins[profile]=np.mean(mm)
   n4.append({'cp_capacity':cp,'sup_capacity':sup,'ramp_s':ramp,'step_bad_rate':rates['step'],'staged_bad_rate':rates['staged'],'step_margin':margins['step'],'staged_margin':margins['staged'],'separation':int(rates['step']>=.95 and rates['staged']<=.10)})
n4=pd.DataFrame(n4);n4.to_csv(OUT/'nh4_neighborhood_robustness.csv',index=False)

summary={
 'NH1':{'seed_blocks':len(n1),'mean_auc_delta':float(n1.auc_delta.mean()),'min_auc_delta':float(n1.auc_delta.min()),'positive_blocks':int((n1.auc_delta>0).sum())},
 'NH2':{'seed_blocks':len(n2),'mean_mae_improvement':float(n2.mae_improvement.mean()),'min_mae_improvement':float(n2.mae_improvement.min()),'blocks_over_10pct':int((n2.mae_improvement>=.10).sum()),'attack_rho_better_blocks':int((n2.attack_rho>n2.raw_rho).sum())},
 'NH4':{'grid_points':len(n4),'separation_points':int(n4.separation.sum()),'separation_fraction':float(n4.separation.mean())}
}
(OUT/'robustness_summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
