#!/usr/bin/env python3
"""Render the outcome audit with Matplotlib (optional analysis dependency)."""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data/research/activity_outcomes'
OUT = ROOT/'docs/figures'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    w = pd.read_csv(DATA/'active_windows.csv.gz')
    e = pd.read_csv(DATA/'perimeter_associations.csv')
    summary = json.loads((DATA/'summary.json').read_text())
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,
                         'axes.spines.right':False,'axes.labelcolor':'#334b43',
                         'text.color':'#233d34','axes.titleweight':'bold','axes.titlesize':12})
    fig, axes = plt.subplots(2,2,figsize=(13.5,9.3),layout='constrained')
    fig.set_facecolor('#fcfcf8')
    fig.suptitle('Was findet der saisonale Outlier-Score?',fontsize=20,fontweight='bold',x=.04,ha='left')
    ax=axes[0,0]
    h=ax.hexbin(w.activity,w.score,xscale='log',gridsize=(55,35),bins='log',mincnt=1,cmap='Greys',linewidths=0)
    ax.axhline(95,color='#ba623b',linestyle='--',linewidth=1)
    ax.text(1.2,96,'Outlier ab 95',color='#a64f2e',fontsize=9)
    ax.set(xlabel='VIIRS-Detektionen je Zelle und 7 Tage (logarithmisch)',ylabel='Saisonaler Score',ylim=(0,102))
    ax.set_title('A  Größe erklärt den Score nur teilweise',loc='left')
    ax.text(.98,.04,f'Spearman ρ = {summary["score_count_spearman_active"]:.2f}\n213.574 aktive Zellfenster',transform=ax.transAxes,ha='right',va='bottom',fontsize=9,bbox={'facecolor':'white','edgecolor':'none','alpha':.8})
    cb=fig.colorbar(h,ax=ax,pad=.02,shrink=.8);cb.set_label('Zellfenster (log. Häufigkeit)',fontsize=9)

    ax=axes[0,1]
    bins=['under_100ha','100_1000ha','1000_10000ha','over_10000ha']
    groups=[summary['events']['any_observed_cell_day'][key] for key in bins]
    fractions=[g['flagged_95']/g['n'] for g in groups]
    ax.bar(range(4),fractions,color=['#a9bda2','#779b82','#457b67','#275b49'],width=.65)
    for i,(g,fraction) in enumerate(zip(groups,fractions)):
        ax.text(i,fraction+.025,f'{fraction:.0%}\n({g["flagged_95"]}/{g["n"]})',ha='center',fontsize=10)
    ax.set_xticks(range(4),['<100','100–1.000','1.000–10.000','≥10.000'])
    ax.set(xlabel='Dokumentierte Ereignisfläche (ha)',ylabel='Anteil mit mindestens einem Score ≥95',ylim=(0,1.15))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.set_title('B  Fast alle großen Feuer tauchen irgendwann auf',loc='left')
    ax.text(.02,.97,'Nur zuordenbare, beobachtete Perimeterereignisse.\nLängere / größere Feuer haben mehr Chancen auf einen Treffer.',transform=ax.transAxes,va='top',fontsize=8.5)

    ax=axes[1,0]
    for name,year,col in [('SODA',2014,'#bf653d'),('WHITES',2014,'#33795f'),('ABNEY',2017,'#775c91')]:
        row=e[(e.name==name)&(e.year==year)].iloc[0]
        vals=[row.peak_week_annual_score,row.peak_week_score]
        ax.plot([0,1],vals,'o-',color=col,linewidth=2,markersize=6)
        ax.text(-.05,vals[0],f'{vals[0]:.1f}',ha='right',va='center',color=col,fontsize=10)
        ax.text(1.05,vals[1],f'{name.title()} {year}: {vals[1]:.1f}',va='center',color=col,fontsize=10)
    ax.axhline(95,color='#b8aa94',linestyle='--',linewidth=1)
    ax.set_xticks([0,1],['Gleiche Zelle, ganzjährig','Gleiche Zelle, saisonal'])
    ax.set(xlim=(-.25,2.0),ylim=(80,103),ylabel='Score für dasselbe 7-Tage-Messfenster')
    ax.set_title('C  Die Jahreszeit ändert die Einordnung',loc='left')
    ax.text(.02,.03,'Stärkste beobachtete Woche des jeweiligen Perimeterereignisses;\nScore der Zelle mit den meisten zugeordneten Detektionen.',transform=ax.transAxes,fontsize=8.5,va='bottom')

    ax=axes[1,1]
    flagged=w[w.score>=95]
    definitions=[('1–2',1,2),('3–5',3,5),('6–19',6,19),('20–99',20,99),('≥100',100,np.inf)]
    fractions=[((flagged.activity>=low)&(flagged.activity<=high)).mean() for _,low,high in definitions]
    ax.barh(range(5),fractions,color=['#c67b50','#d6a56a','#b3bc89','#81a18b','#42745c'])
    for i,fraction in enumerate(fractions):ax.text(fraction+.006,i,f'{fraction:.1%}',va='center',fontsize=10)
    ax.set_yticks(range(5),[x[0] for x in definitions]);ax.invert_yaxis()
    ax.set(xlabel='Anteil der 41.974 als Outlier markierten Zellfenster',ylabel='Detektionen im 7-Tage-Fenster',xlim=(0,.36))
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set_title('D  Auffällig bedeutet oft wenig, aber ungewohnt',loc='left')
    fig.get_layout_engine().set(h_pad=.12,w_pad=.12,hspace=.10,wspace=.10)
    fig.savefig(OUT/'activity-outlier-outcomes.png',dpi=170,facecolor=fig.get_facecolor(),bbox_inches='tight')
    fig.savefig(OUT/'activity-outlier-outcomes.pdf',facecolor=fig.get_facecolor(),bbox_inches='tight')
    print(OUT/'activity-outlier-outcomes.png')


if __name__=='__main__':main()
