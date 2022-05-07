import pandas as pd
import requests
import json
from pandas.io.json import json_normalize
from functools import reduce
from datetime import datetime, timedelta
import openpyxl
import time
from time import mktime
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objs import *
from plotly.graph_objs.scatter.marker import Line
from plotly.subplots import make_subplots
import xlrd
import openpyxl
import numpy as np
import re
from bs4 import BeautifulSoup
import math
import plotly.io as pio
import plot_settings
from multiapp import MultiApp
import streamlit as st

st.set_page_config(layout='wide')

# dictionary of companys and google drive links
GOOGLE_DRIVE_URL_DICT = {
    'SPY':'https://drive.google.com/file/d/1u3q9tkmcZIKmulbz0k0k3qcDHcQnuKqt/view?usp=sharing',
    'QQQ':'https://drive.google.com/file/d/16GAn0hYJ_zm4WSTmWSp8Q83COHVEVSd1/view?usp=sharing'
}

# function to get file from google drive
@st.cache
def pull_google_drive(url):
    file_id = url.split('/')[-2]
    dwn_url = "https://drive.google.com/uc?id=" + file_id
    tmp = pd.read_csv(dwn_url)
    # tmp = pd.read_excel(dwn_url)
    return tmp

# function to reformat raw df - only for 1 ticker at a time
@st.cache
def reformat_dfs(d, chosen_tick):
    col_name_dict = {
        'QQQ':'invesco qqq trust - price',
        'SPY':'spdr s&p 500 etf trust - price'
    }

    tmp = d.copy()
    tmp.columns = [x.strip().lower() for x in tmp.columns]
    tmp = tmp.filter(['date', col_name_dict[chosen_tick]])
    tmp = tmp.rename(columns={col_name_dict[chosen_tick]: 'close'})
    tmp['tick'] = chosen_tick.lower()

    tmp['date'] = pd.to_datetime(tmp['date'])
    tmp['year'] = tmp.date.dt.year
    tmp = tmp.replace('@NA', np.nan)
    tmp = tmp[tmp.close.notnull()]
    tmp['close'] = tmp.close.astype('float')

    tmp = tmp.sort_values(by=['tick', 'date'])
    tmp['daycnt'] = tmp.groupby(['tick', 'year'])['date'].transform('cumcount')
    tmp['pchg'] = tmp.groupby(['tick', 'year']).close.pct_change() + 1

    tmp['pchg'] = np.where(tmp.daycnt == 0, 1, tmp.pchg)
    tmp = tmp.reset_index()
    tmp['norm'] = tmp.groupby(['tick', 'year'])['pchg'].cumprod()

    return tmp

def sidebar_config(GOOGLE_DRIVE_URL_DICT):
    chosen_tick = st.sidebar.selectbox(label="Ticker", options=sorted(list(GOOGLE_DRIVE_URL_DICT.keys())), index=0)

    root_view = st.sidebar.radio(label='Raw View', options=['DoD % Chg Normalized','DoD % Chg Raw','Close Price'],
                                 index=0)

    result_view = st.sidebar.radio(label='Result View', options=['DoD % Chg Normalized', 'DoD % Chg Raw'],
                                 index=0)

    return chosen_tick, root_view, result_view

def cycle_page(GOOGLE_DRIVE_URL_DICT):
    st.title('Market Cycle Analysis')

    chosen_tick, root_view, result_view = sidebar_config(GOOGLE_DRIVE_URL_DICT)

    df = pull_google_drive(GOOGLE_DRIVE_URL_DICT[chosen_tick])
    df = reformat_dfs(df, chosen_tick)

    # determine incomplete years
    yr_counts = df.groupby(['tick', 'year'])['date'].nunique().reset_index().\
        rename(columns={'date': 'unique_dates'})
    max_yr = yr_counts['year'].max()
    is_max_yr_partial = True if yr_counts[yr_counts.year==max_yr]['unique_dates'].values[0]<260 else False
    yrs_exclude = yr_counts[(yr_counts.unique_dates < 260) & (yr_counts.year != max_yr)]
    # yrs_exclude = yr_counts.query('unique_dates < 260').reset_index()

    dfco = df[~df.year.isin(yrs_exclude.year)]
    dfex = df[df.year.isin(yrs_exclude.year)]

    dfco['daycntlabel'] = dfco['daycnt'] + 1
    dfco['daycntlabel'] = np.where(dfco.daycntlabel % 20 == 0, (dfco.daycntlabel / 20 * 4).astype(int).astype(str) + " Wk",
                                 dfco.daycntlabel.astype(str))

    view_dict = {
        'DoD % Chg Normalized':'norm',
        'DoD % Chg Raw':'pchg',
        'Close Price':'close'
    }

    # ROOT PLOT
    root_plot = px.line(dfco, x='daycntlabel', y=view_dict[root_view], color='year',
                                 template=plot_settings.dockstreet_template,
                        labels={'daycntlabel':'Trading Weeks Elapsed', view_dict[root_view]:root_view, 'year':''})

    root_plot.update_xaxes(type='category',
                           showgrid=False,
                           tickvals = ['4 Wk', '8 Wk', '12 Wk', '16 Wk', '20 Wk', '24 Wk', '28 Wk',
                                       '32 Wk', '36 Wk', '40 Wk', '44 Wk', '48 Wk', '52 Wk']
                           )
    root_plot.update_layout(plot_bgcolor='white',
                            legend_title="",
                            title=dict(font_size=20,
                                       x=0.03,
                                       y=.98,
                                       yref='container',
                                       text=f"<b>{chosen_tick}: {root_view} Trends by Year</b>",
                                       font_color="#4c4c4c",
                                       xanchor='left'),
                            legend=dict(
                                font=dict(size=14),
                                traceorder="reversed"
                            ))

    st.write('<br>', unsafe_allow_html=True)
    st.plotly_chart(root_plot, use_container_width=True)

    # TO DO
    # do a forward fill so that all years chosen have the same number of days as the longest year

    with st.form("year_submit"):
        possible_years = sorted(dfco.year.unique().tolist())[::-1][1:]

        col1, space, col2, space1, col3, space2, col4 = st.columns((.5,.1,.5,.1,.5,.1,.5))

        # decennial calculation
        decennial = col1.checkbox(label="Decennial Years", value=False)
        decennial_end = col1.number_input("Years Ending In", 0, 9)
        if decennial:
            dec_yrs = sorted([x for x in possible_years if int(str(x)[-1])==decennial_end])
        else:
            dec_yrs = []

        # prescycle
        prescycle = col2.checkbox(label="Pres. Cycle Year", value=False)
        prescycle_yr = col2.number_input("Cycle Year", 1, 4)
        pres_dict = {1: [1993, 1997, 2001, 2005, 2009, 2013, 2017, 2021, 2025],
                     2: [1994, 1998, 2002, 2006, 2010, 2014, 2018, 2022, 2026],
                     3: [1995, 1999, 2003, 2007, 2011, 2015, 2019, 2023, 2027],
                     4: [1992, 1996, 2000, 2004, 2008, 2012, 2016, 2020, 2024]}
        if prescycle:
            pres_yrs = sorted([x for x in possible_years if x in pres_dict[prescycle_yr]])
        else:
            pres_yrs = []

        # manually picked
        manual = col3.checkbox(label="Chosen Years", value=False)
        similar_yr = col3.multiselect(label="Similar Years", options=possible_years,
                       default=[])
        if manual:
            similar_yrs = sorted(similar_yr)
        else:
            similar_yrs = []


        all_yrs = sorted(list(set(dec_yrs + pres_yrs + similar_yrs)))

        # out of sample year
        oos = col4.checkbox(label="Show OOS Year", value=False)
        # oos_yr = col4.selectbox(label="OOS Year", options=all_yrs, index=0)

        st.write("<br>", unsafe_allow_html=True)
        st.write(f"Years Chosen: {str(sorted(list(set(dec_yrs + pres_yrs + similar_yrs)))).strip('[]')}",
                 unsafe_allow_html=True)

        st.form_submit_button('Calculate')

    if all_yrs == []:
        st.warning('Please choose 1 or more years to view resulting plot.')
    else:
        # to forward fill
        nextyrs = [x + 1 for x in all_yrs]
        nexts = dfco[dfco.year.isin(nextyrs)]

        # FIGURE OUT BETTER LOGIC LATER
        nexts = nexts[~nexts.daycntlabel.isin(['261','262'])]

        last_next = max(nextyrs)
        if oos:
            nexts['category'] = np.where(nexts.year==last_next,last_next,'Other Yrs')
            comp_years = sorted(nexts[nexts.category=='Other Yrs']['year'].unique().tolist())
        else:
            nexts['category'] = 'All Years'
            comp_years = sorted(nexts.year.unique().tolist())

        comp_years = [str(x) for x in comp_years]

        avgs = nexts.groupby(['daycnt','daycntlabel','category'])[view_dict[result_view]].mean().\
            to_frame().reset_index()

        result_plot = px.line(avgs, x='daycntlabel', y=view_dict[result_view], color='category',
                              template=plot_settings.dockstreet_template,
                              labels={'daycntlabel':'Trading Weeks Elapsed',
                                      view_dict[result_view]:result_view})
        result_plot.update_xaxes(type='category',
                                 showgrid=False,
                                 tickvals = ['4 Wk', '8 Wk', '12 Wk', '16 Wk', '20 Wk', '24 Wk', '28 Wk',
                                             '32 Wk', '36 Wk', '40 Wk', '44 Wk', '48 Wk', '52 Wk']
                                 )
        result_plot.update_layout(plot_bgcolor='white',
                                  legend_title="",
                                  showlegend=False,
                                  margin=dict(t=90),
                                  title=dict(font_size=20,
                                           x=0.03,
                                           y=.96,
                                           yref='container',
                                           text=f"<b>{chosen_tick}: {result_view} - Subsequent Years' Average</b>" + \
                                             f'<br><span style="font-size:16px;">Composite years: {", ".join(comp_years)}</span>',
                                           font_color="#4c4c4c",
                                           xanchor='left'),
                                  legend=dict(
                                      font=dict(size=14)
                                  ))

        if oos:
            result_plot.update_layout(showlegend=True)

        st.write('<br>', unsafe_allow_html=True)
        st.plotly_chart(result_plot, use_container_width=True)

        if (is_max_yr_partial) & (max_yr-1 in similar_yrs):
            st.write(f"Data for {max_yr} only includes {yr_counts[yr_counts.year==max_yr]['unique_dates'].values[0]} trading days.")

def create_app_with_pages():
    # CREATE PAGES IN APP
    app = MultiApp()
    app.add_app("Market Cycles", cycle_page, [GOOGLE_DRIVE_URL_DICT])
    # app.add_app("Call & Put Volumes", callput_page, [])
    app.run(logo_path='logo.png')

if __name__ == '__main__':
    create_app_with_pages()