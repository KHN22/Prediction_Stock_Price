"""Build the dated dashboard comparison from the frozen experiment (offline)."""
from html import escape
from pathlib import Path
import re
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from experiment import HERE, ROOT, OUT, control, df, env, partitions, baseline_vectors, raw_weight, rmse

def label(th,en):
    return f'<span data-en="{escape(en,quote=True)}">{escape(th)}</span>'

def financial_overlay(base):
    # Calendar-matched prior year only. Bound ratios when profits cross zero.
    fin=env["fin"].copy().sort_values("fiscalDateEnding")
    prior=fin.shift(4)
    valid=(fin.fiscalDateEnding-prior.fiscalDateEnding).dt.days.between(345,385)
    features=pd.DataFrame({"margin":fin.fin_net_margin,"gross_margin":fin.fin_gross_margin,
        "margin_change":(fin.fin_net_margin-prior.fin_net_margin).where(valid),
        "revenue_growth":((fin.is_totalRevenue-prior.is_totalRevenue)/
                          (fin.is_totalRevenue.abs()+prior.is_totalRevenue.abs())).where(valid)})
    features=features.clip(-1,1).set_index(fin.date).sort_index().reindex(df.date,method="ffill")
    train,test,folds=partitions("6m")
    target=df.target_log_return_6m.to_numpy()
    def fit(tr,va):
        x=features.iloc[tr]
        med=x.median().fillna(0)
        # Each published quarter gets equal total influence in the regression.
        quarter=df.fiscalDateEnding.iloc[tr]
        weights=1/quarter.map(quarter.value_counts()).to_numpy()
        model=Ridge(alpha=2).fit(x.fillna(med),target[tr]-base[tr],sample_weight=weights)
        return model.predict(features.iloc[va].fillna(med))
    residuals=[]; errors=[]; fold_weights=[]
    for tr,va in folds:
        r=fit(tr,va)
        e=target[va]-base[va]
        fold_weights.append(np.clip(raw_weight(e,r),0,1))
        residuals.extend(r)
        errors.extend(e)
    w=np.clip(raw_weight(np.array(errors),np.array(residuals)),0,1)
    pred=base[test]+w*fit(train,test)
    known=np.flatnonzero(df.target_date_6m.le(df.date.iloc[-1]))
    increment=100*np.exp(base[-1])*np.expm1(w*fit(known,[len(df)-1])[0])
    return w,fold_weights,rmse(pred-target[test]),increment

def build():
    metrics=pd.read_csv(OUT/"metrics.csv")
    latest=pd.read_csv(OUT/"latest.csv")
    fixed=pd.read_csv(OUT/"fixed_members.csv")
    hb=pd.read_csv(OUT/"baseline_holdout.csv")
    def row(name,base,ml,w,rm,da):
        values=[name,f'{base:+.2f}%',f'{ml:+.2f}',f'{base+ml:+.2f}%',w,f'{rm:.4f}',f'{da*100:.1f}%']
        return '<tr>'+''.join(f'<th scope="row">{v}</th>' if i==0 else f'<td>{v}</td>' for i,v in enumerate(values))+'</tr>'
    parts=[]
    base=baseline_vectors(126)["decayed"]
    for h,key in [('3m','B_price_macro'),('6m','C_price_macro_financials')]:
        q=metrics.query("horizon==@h and feature_set==@key and arm=='control'").iloc[0]
        l=latest.query("horizon==@h and feature_set==@key and arm=='control'").iloc[0]
        rows=row('Control '+key[0]+' · Momentum 21d',l.base_pct,l.residual_increment_pp,l.weight.round(3),q.rmse,q.direction)
        if h=='3m':
            f=fixed.query("horizon==@h and feature_set==@key").iloc[0]
            rows+=row('RF · '+label('ฐานราคาคงเดิม','Flat baseline'),f.latest_base_pct,f.residual_increment_pp,f.weight.round(3),f.rmse,f.direction)
        else:
            b=hb.query("horizon==@h and baseline=='decayed'").iloc[0]
            rows+=row('Decayed Momentum',100*np.expm1(base[-1]),0,'—',b.rmse,b.direction)
        headings=[('วิธี','Method'),('ฐาน','Baseline'),('ML (จุด %)','ML (pp)'),('ผลรวม','Total'),('น้ำหนัก ML','ML weight'),('RMSE','RMSE'),('ทิศทางถูก','Direction accuracy')]
        parts.append('<section class="lab-'+h+'"><h3>'+label(*({'3m':('3 เดือน · ราคา + Macro เทียบ Control B','3 months · Price + macro vs Control B'),'6m':('6 เดือน · แรงส่งถ่วงน้ำหนักเทียบ Control C (ราคา + Macro + งบ)','6 months · Decayed momentum vs Control C (price + macro + financials)')}[h]))+'</h3><div class="macro-table-wrap" tabindex="0"><table class="statement-table"><thead><tr>'+''.join('<th scope="col">'+label(*pair)+'</th>' for pair in headings)+'</tr></thead><tbody>'+rows+'</tbody></table></div></section>')
    w,fold,err,inc=financial_overlay(base)
    review=control['financialReview']
    def growth(k):
        line=review['lines'][k]
        return (line['actual']/line['previous']-1)*100
    folds=' / '.join(f'{v:.2f}' for v in fold)
    title=label('มุมมองทดลอง MU','MU experiments')
    html='<details id="mu-lab" class="card notes"><summary>'+title+'</summary><p>'+label('ผลทดลอง ณ '+control['asOf']+' · ราคาปิด $601.25 · ผลชุดนี้ตรึงไว้เพื่อเทียบย้อนหลัง','Frozen experiment · '+control['asOf']+' · Closing price $601.25')+'</p>'+''.join(parts)
    html+='<p>'+label('ฐานและส่วนเพิ่มจาก ML รวมกันเป็นผลตอบแทนคาดการณ์ จุดเปอร์เซ็นต์วัดผลของ ML หลังใช้น้ำหนักแล้ว ส่วน RMSE วัดผลตอบแทน log บนชุดทดสอบ ยิ่งต่ำยิ่งดี','Baseline return plus the weighted ML increment equals the forecast return. RMSE measures held-out log-return error; lower is better.')+'</p><h3>'+label('งบที่เติบโตช่วยปรับประมาณการ 6 เดือนได้แค่ไหน?','Does earnings growth improve the six-month estimate?')+'</h3><p>'+label(f"งวดสิ้นสุด {review['quarter']} รายได้โต {growth('revenue'):.1f}% และกำไรสุทธิโต {growth('netIncome'):.1f}% จากไตรมาสก่อน",f"Quarter ended {review['quarter']}: revenue grew {growth('revenue'):.1f}% and net income grew {growth('netIncome'):.1f}% quarter over quarter.")+'</p><p>'+label(f'ทดลองเสริมฐาน Decayed ด้วยอัตรากำไรและการเปลี่ยนแปลงงบรายปี ให้แต่ละไตรมาสมีน้ำหนักฝึกเท่ากัน น้ำหนัก ML รายรอบ {folds} น้ำหนักรวม {w:.3f} เพิ่มผลคาดการณ์ {inc:+.2f} จุดเปอร์เซ็นต์ RMSE บนชุดทดสอบ {err:.4f} เทียบฐานล้วน {b.rmse:.4f}',f'Added margins and year-over-year financial changes to Decayed, giving each quarter equal training weight. Fold weights {folds}. Pooled weight {w:.3f}; forecast increment {inc:+.2f} pp. Test RMSE {err:.4f} vs baseline alone {b.rmse:.4f}.')+'</p><small>'+label('ทดสอบย้อนหลังจากชุดเดิม ระยะ 6 เดือนมี 226 จุดที่ทับซ้อนกัน เมื่อเว้นทุก 126 วันจากจุดแรกเหลือ 2 จุด','Retrospective test. The 226 six-month windows overlap; sampling every 126 sessions from the first origin leaves two observations.')+'</small></details>'
    path=ROOT/'public/index.html'
    s=path.read_text(encoding='utf-8')
    marker='<!-- MU frozen lab -->'
    if marker in s:
        s=re.sub(marker+'.*?<!-- end MU lab -->','',s,flags=re.S)
    pos=s.index('    <div class="forecast-heading"')
    s=s[:pos]+marker+html+'<!-- end MU lab -->'+s[pos:]
    path.write_text(s,encoding='utf-8')
    print(w,fold,err,inc)
if __name__=='__main__':
    build()
