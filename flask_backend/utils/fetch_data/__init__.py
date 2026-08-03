"""
数据拉取脚本集合

使用方式：
  cd flask_backend
  python utils/fetch_data/run_all_fetch.py

或单独执行：
  python utils/fetch_data/fetch_etf.py
  python utils/fetch_data/fetch_index.py
  python utils/fetch_data/fetch_moneyflow_ind_dc.py --start 20230912 --end YYYYMMDD
  python utils/fetch_data/fetch_moneyflow_cnt_ths.py --start 20240910 --end YYYYMMDD
  python utils/fetch_data/fetch_moneyflow_ind_ths.py --start 20240910 --end YYYYMMDD
"""