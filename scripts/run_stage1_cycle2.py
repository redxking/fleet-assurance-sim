from __future__ import annotations

import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from fleet_sim.experiments.stage1_research import (
    _dynamic_assurance_outcome,
    _fit_logistic,
    _predict_logistic,
    _roc_auc,
    _weighted_attack_operator,
    _weighted_spectral_radius,
    _simulate_weighted_sir,
    simulate_admission_trajectory,
)
from fleet_sim.graphs.factory import build_graph, spectral_radius

SEED = 20260819
RESULTS = ROOT / 'results' / 'stage1_cycle2'
FIGURES = ROOT / 'figures' / 'stage1_cycle2'
RESULTS.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)


def nh1():
    rng = np.random.default_rng(SEED + 101)
    X = rng.uniform(0.45, 0.98, size=(4000, 7))
    names = ['cp','contain','obs','sup','rev','timing','mission_inv']
    rows=[]
    for i,x in enumerate(X):
        y,severity,details = _dynamic_assurance_outcome(x,n_agents=10000,rng=rng)
        split = 'test' if (0.55 < x[2] < 0.82 and x[4] > 0.68 and x[0] < 0.86) else 'train'
        row={'sample_id':i,'split':split,'failure':y,'severity':severity,'baseline_score':float(np.max(x))}
        row.update({k:float(v) for k,v in zip(names,x)}); row.update(details); rows.append(row)
    df=pd.DataFrame(rows)
    def matrix(fr):
        base=fr[names].to_numpy(float)
        inter=np.column_stack([
            fr.obs*fr.contain, fr.contain*fr.rev, fr.rev*fr.cp,
            fr.obs*fr.sup, fr.timing*fr.mission_inv
        ])
        return np.column_stack([base,inter])
    tr=df[df.split=='train']; te=df[df.split=='test'].copy()
    w=_fit_logistic(matrix(tr),tr.failure.to_numpy())
    pc=_predict_logistic(matrix(te),w)
    pb=1/(1+np.exp(-18*(te.baseline_score.to_numpy()-0.90)))
    auc_c=_roc_auc(te.failure.to_numpy(),pc); auc_b=_roc_auc(te.failure.to_numpy(),te.baseline_score.to_numpy())
    bc=float(np.mean((pc-te.failure.to_numpy())**2)); bb=float(np.mean((pb-te.failure.to_numpy())**2))
    te['coupled_probability']=pc; te['baseline_probability']=pb
    df=df.merge(te[['sample_id','coupled_probability','baseline_probability']],on='sample_id',how='left')
    df.to_csv(RESULTS/'nh1_refined.csv',index=False)
    return df, {'auc_coupled':auc_c,'auc_baseline':auc_b,'brier_coupled':bc,'brier_baseline':bb,
                'test_n':int(len(te)),'test_failure_rate':float(te.failure.mean()),
                'supported':bool(auc_c-auc_b>=0.02 and bc<bb)}


def nh2():
    n=160; reps=30; rows=[]; sid=0
    auth_specs=[('rr4','random_regular',{'degree':4}),('rr8','random_regular',{'degree':8}),
                ('ba2','barabasi_albert',{'attachment':2}),('h6','hierarchical',{'span':6})]
    dep_specs=[('rr3','random_regular',{'degree':3},'train'),('rr10','random_regular',{'degree':10},'train'),
               ('er3','erdos_renyi',{'degree':3},'train'),('er12','erdos_renyi',{'degree':12},'train'),
               ('ba1','barabasi_albert',{'attachment':1},'test'),('ba5','barabasi_albert',{'attachment':5},'test'),
               ('h4','hierarchical',{'span':4},'test'),('h12','hierarchical',{'span':12},'test')]
    for ai,(aname,atop,akw) in enumerate(auth_specs):
        ga_b=build_graph(n,atop,seed=10000+ai,**akw); ga=ga_b.materialize(); raw=spectral_radius(ga_b)
        gc=build_graph(n,'random_regular',seed=11000+ai,degree=6).materialize()
        gs=build_graph(n,'hierarchical',seed=12000+ai,span=8).materialize()
        for di,(dname,dtop,dkw,split) in enumerate(dep_specs):
            gd=build_graph(n,dtop,seed=13000+ai*100+di,**dkw).materialize()
            gx=_weighted_attack_operator(ga,gc,gd,gs); ar=_weighted_spectral_radius(gx)
            for ratio in (0.20,0.30,0.40,0.50):
                vals=[]
                for rep in range(reps):
                    rseed=SEED+sid*1000+rep
                    peak,ever,dur=_simulate_weighted_sir(gx,beta=ratio*.30,gamma=.30,seed=rseed)
                    vals.append((peak,ever,dur,rseed))
                for peak,ever,dur,rseed in vals:
                    rows.append({'scenario_id':sid,'auth':aname,'dependency':dname,'split':split,'ratio':ratio,
                                 'raw_product':raw*ratio,'attack_product':ar*ratio,
                                 'peak':peak,'ever':ever,'duration':dur,'seed':rseed})
                sid+=1
    df=pd.DataFrame(rows); df.to_csv(RESULTS/'nh2_refined.csv',index=False)
    means=df.groupby(['scenario_id','split'],as_index=False).agg(raw=('raw_product','first'),attack=('attack_product','first'),ever=('ever','mean'),peak=('peak','mean'))
    tr=means[means.split=='train']; te=means[means.split=='test']
    metrics={}
    preds={}
    for col in ('raw','attack'):
        coef=np.linalg.lstsq(np.c_[np.ones(len(tr)),tr[col]],tr.ever,rcond=None)[0]
        ph=np.c_[np.ones(len(te)),te[col]]@coef
        preds[col]=ph
        metrics[f'{col}_mae']=float(np.mean(np.abs(ph-te.ever)))
        metrics[f'{col}_spearman']=float(spearmanr(te[col],te.ever).statistic)
    metrics['mae_improvement_fraction']=(metrics['raw_mae']-metrics['attack_mae'])/metrics['raw_mae']
    metrics['supported']=bool(metrics['mae_improvement_fraction']>=.10 and metrics['attack_spearman']>metrics['raw_spearman'])
    return df,means,metrics


def nh4():
    frames=[]
    for rep in range(60):
        seed=SEED+5000+rep
        for profile in ('step','staged'):
            frames.append(simulate_admission_trajectory(profile,seed=seed,cp_capacity_ops_s=165.0,
                sup_capacity_reviews_s=27.0,ramp_duration_s=180.0))
    df=pd.concat(frames,ignore_index=True); df.to_csv(RESULTS/'nh4_refined.csv',index=False)
    per=df.groupby(['profile','seed'],as_index=False).agg(min_margin=('assurance_margin','min'),
        final_n=('n_agents','last'),max_cp_queue=('cp_queue','max'),max_sup_queue=('sup_queue','max'))
    per['ever_inadmissible']=(per.min_margin<0).astype(int)
    s=per.groupby('profile').agg(inadmissible_rate=('ever_inadmissible','mean'),mean_min_margin=('min_margin','mean'),
        final_n=('final_n','mean'),mean_max_cp_queue=('max_cp_queue','mean'),mean_max_sup_queue=('max_sup_queue','mean'))
    metrics={'step_inadmissible_rate':float(s.loc['step','inadmissible_rate']),
             'staged_inadmissible_rate':float(s.loc['staged','inadmissible_rate']),
             'step_mean_min_margin':float(s.loc['step','mean_min_margin']),
             'staged_mean_min_margin':float(s.loc['staged','mean_min_margin']),
             'same_final_n':bool(np.isclose(s.loc['step','final_n'],s.loc['staged','final_n']))}
    metrics['supported']=bool(metrics['step_inadmissible_rate']>=.95 and metrics['staged_inadmissible_rate']<=.10 and metrics['same_final_n'])
    return df,per,metrics


def figures(n1,n2means,n4):
    te=n1[n1.split=='test'].dropna(subset=['coupled_probability'])
    fig,ax=plt.subplots(figsize=(7.2,5)); ax.scatter(te.baseline_score,te.coupled_probability,c=te.failure,alpha=.55,s=18)
    ax.set_xlabel('Maximum individual constraint ratio (<1 by design)'); ax.set_ylabel('Coupled predicted failure probability')
    ax.set_title('NH1-R: interaction-sensitive held-out region'); ax.grid(alpha=.2); fig.tight_layout(); fig.savefig(FIGURES/'nh1_refined.png',dpi=170); plt.close(fig)
    te2=n2means[n2means.split=='test']; fig,ax=plt.subplots(figsize=(7.2,5));
    ax.scatter(te2.raw,te2.ever,label='Raw authorization product'); ax.scatter(te2.attack,te2.ever,marker='x',label='Attack operator product')
    ax.set_xlabel('Predictor value');ax.set_ylabel('Mean ever-compromised fraction');ax.set_title('NH2-R: matched authorization, held-out dependencies');ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(FIGURES/'nh2_refined.png',dpi=170);plt.close(fig)
    m=n4.groupby(['profile','time_s'],as_index=False).assurance_margin.mean();fig,ax=plt.subplots(figsize=(7.8,5));
    for p,g in m.groupby('profile'):ax.plot(g.time_s,g.assurance_margin,label=p)
    ax.axhline(0,ls='--',lw=1);ax.set_xlabel('Time (s)');ax.set_ylabel('Mean minimum assurance margin');ax.set_title('NH4-R: same final N, different admission trajectories');ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(FIGURES/'nh4_refined.png',dpi=170);plt.close(fig)


n1,m1=nh1(); n2,n2means,m2=nh2(); n4,n4per,m4=nh4(); figures(n1,n2means,n4)
summary={'seed':SEED,'evidence_scope':'model-conditioned; parameters notional; no external validation',
         'NH1_R':m1,'NH2_R':m2,'NH4_R':m4}
(RESULTS/'stage1_cycle2_summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
