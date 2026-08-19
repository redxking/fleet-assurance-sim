from pathlib import Path
import json
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from plotly.offline import plot

root=Path(__file__).resolve().parents[1]
r2=root/'results'/'stage1_cycle2'
rob=root/'results'/'stage1_robustness'
nh1=pd.read_csv(r2/'nh1_refined.csv')
nh2=pd.read_csv(r2/'nh2_refined.csv')
nh4=pd.read_csv(r2/'nh4_refined.csv')
r1=pd.read_csv(rob/'nh1_seed_robustness.csv')
r2rob=pd.read_csv(rob/'nh2_seed_robustness.csv')
r4=pd.read_csv(rob/'nh4_neighborhood_robustness.csv')

fig=make_subplots(rows=2,cols=2,subplot_titles=(
 'NH1-R: Coupled Prediction in Individually Subcritical Region',
 'NH2-R: Raw Authorization vs Attack-Reachability Predictor',
 'NH4-R: Admission Trajectory Assurance Margin',
 'Robustness Summary'))

t=nh1[(nh1['split']=='test') & nh1['coupled_probability'].notna()]
fig.add_trace(go.Scatter(x=t['baseline_score'],y=t['coupled_probability'],mode='markers',
 marker=dict(size=5),text=['failure='+str(int(v)) for v in t['failure']],name='NH1 held-out'),row=1,col=1)

m=nh2[nh2['split']=='test'].groupby('scenario_id',as_index=False).agg(raw=('raw_product','first'),attack=('attack_product','first'),ever=('ever','mean'))
fig.add_trace(go.Scatter(x=m['raw'],y=m['ever'],mode='markers',name='Raw authorization'),row=1,col=2)
fig.add_trace(go.Scatter(x=m['attack'],y=m['ever'],mode='markers',name='Attack operator'),row=1,col=2)

mt=nh4.groupby(['profile','time_s'],as_index=False).agg(margin=('assurance_margin','mean'))
for profile,g in mt.groupby('profile'):
 fig.add_trace(go.Scatter(x=g['time_s'],y=g['margin'],mode='lines',name=f'Admission: {profile}'),row=2,col=1)
fig.add_hline(y=0,row=2,col=1,line_dash='dash')

labels=['NH1 positive seed blocks','NH2 >10% MAE blocks','NH4 separating grid points']
vals=[int((r1.auc_delta>0).sum()),int((r2rob.mae_improvement>=.10).sum()),int(r4.separation.sum())]
den=[len(r1),len(r2rob),len(r4)]
fig.add_trace(go.Bar(x=labels,y=[100*v/d for v,d in zip(vals,den)],text=[f'{v}/{d}' for v,d in zip(vals,den)],textposition='auto',name='Robustness pass rate'),row=2,col=2)

fig.update_xaxes(title_text='Maximum individual normalized ratio',row=1,col=1)
fig.update_yaxes(title_text='Coupled failure probability',row=1,col=1)
fig.update_xaxes(title_text='Threshold predictor',row=1,col=2)
fig.update_yaxes(title_text='Ever-compromised fraction',row=1,col=2)
fig.update_xaxes(title_text='Time (s)',row=2,col=1)
fig.update_yaxes(title_text='Minimum assurance margin',row=2,col=1)
fig.update_yaxes(title_text='Pass percentage',range=[0,105],row=2,col=2)
fig.update_layout(height=900,width=1450,title='Fleet Assurance Research Console: Stage 1 Cycles 1 and 2',legend=dict(orientation='h'))

out=root/'replay_bundles'/'stage1-research-console.html'
plot(fig,filename=str(out),auto_open=False,include_plotlyjs=True)
print(out)
