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

    with st.form("year_submit"):
        similar_yrs = st.multiselect(label="Similar Years", options=sorted(dfco.year.unique().tolist())[::-1][1:],
                       default=[])
        st.form_submit_button('Calculate')

    if similar_yrs == []:
        st.warning('Please choose 1 or more years to view resulting plot.')
    else:
        nextyrs = [x + 1 for x in similar_yrs]
        nexts = dfco[dfco.year.isin(nextyrs)]
        avgs = nexts.groupby('daycnt')[view_dict[result_view]].mean().to_frame().reset_index()

        result_plot = px.line(avgs, x='daycntlabel', y=view_dict[result_view],
                              template=plot_settings.dockstreet_template,
                              labels={'daycntlabel':'Trading Weeks Elapsed', view_dict[result_view]:result_view})
        result_plot.update_xaxes(type='category',
                                 showgrid=False,
                                 tickvals = ['4 Wk', '8 Wk', '12 Wk', '16 Wk', '20 Wk', '24 Wk', '28 Wk',
                                             '32 Wk', '36 Wk', '40 Wk', '44 Wk', '48 Wk', '52 Wk']
                                 )
        result_plot.update_layout(plot_bgcolor='white',
                                  legend_title="",
                                  title=dict(font_size=20,
                                           x=0.03,
                                           y=.98,
                                           yref='container',
                                           text=f"<b>{chosen_tick}: {result_view} - Subsequent Years' Average</b>",
                                           font_color="#4c4c4c",
                                           xanchor='left'),
                                  legend=dict(
                                      font=dict(size=14)
                                  ))

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