"""Read-only MCP feature discovery/probes, isolated cached research outputs."""
from pathlib import Path
import sys,json,time,datetime
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'fetch_data'))
import download_amv_research as d
def query(name,args,key):
    dest=ROOT/'raw'/f'{key}.json';dest.parent.mkdir(exist_ok=True)
    if dest.exists():return json.loads(dest.read_text(encoding='utf8'))
    record={'tool':name,'arguments':args,'retrieved_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        r=d.SESSION.post(d.ENDPOINT,json={'jsonrpc':'2.0','id':7,'method':'tools/call','params':{'name':name,'arguments':args}},timeout=(15,35))
        r.raise_for_status();r.encoding='utf8'
        if r.text.lstrip().startswith('{'):e=r.json()
        else:e=next(json.loads(line[5:].strip()) for line in r.text.splitlines() if line.startswith('data:') and '"id"' in line)
        if 'error' in e:raise RuntimeError(str(e['error']))
        result=e['result']
        if result.get('isError'):raise RuntimeError(str(result.get('content')))
        rows=[]
        for b in result.get('content',[]):
            if b.get('type')=='text':
                v=json.loads(b['text'])
                if not isinstance(v,list):raise RuntimeError(str(v))
                rows.extend(v)
        record['rows']=rows
    except Exception as e:record['error']=d.redact(e)
    dest.write_text(json.dumps(record,ensure_ascii=False),encoding='utf8')
    print(key,len(record.get('rows',[])),json.dumps(record.get('error',''),ensure_ascii=True)[:220],flush=True)
    time.sleep(.2)
    return record
if __name__=='__main__':
    period={'start_date':'20240910','end_date':'20260930'}
    query('margin',period,'margin')
    query('moneyflow_mkt_dc',period,'market_flow')
    for code in ['000001.SH','399001.SZ','000905.SH','399006.SZ']:
        query('index_dailybasic',{**period,'ts_code':code},'basic_'+code)
    for code in ['000300.SH','000905.SH','000852.SH','932000.CSI','399006.SZ','000001.SH']:
        query('index_daily',{**period,'ts_code':code},'index_'+code)
    for start,end in [('20240910','20241231'),('20250101','20251231'),('20260101','20260930')]:
        query('daily_info',{'start_date':start,'end_date':end},'market_'+start)
        query('moneyflow_hsgt',{'start_date':start,'end_date':end},'north_'+start)
    for name,code in [('idx_mins','000001.SH'),('sw_mins','801010.SI')]:
        query(name,{'ts_code':code,'freq':'5min','start_date':'2026-09-30 09:00:00','end_date':'2026-09-30 15:10:00'},name+'_probe')
