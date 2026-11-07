#!/usr/bin/env python3
"""Pair the nine supply-chain charts with verified product/field photographs.

Dependencies: reportlab, PyMuPDF, Pillow. Font setup matches build_atlas.py.
Photographs are kept whole and placed at their original aspect ratios.
"""
from pathlib import Path
from math import ceil
import json, shutil, re, csv
import fitz
from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'output'
SRC=OUT/'source'
TMP=ROOT/'tmp/photo-atlas'
FIG=OUT/'photo-diagrams'
ASSET=OUT/'photos/assets'
REVIEW=TMP/'review'
for p in [FIG,ASSET,REVIEW]:p.mkdir(parents=True,exist_ok=True)
for name in ['Regular','Bold']:
    pdfmetrics.registerFont(TTFont('Noto'+name,str(ROOT/'tmp/fonts'/('NotoSansSC-'+name+'.ttf'))))
REG,BOLD='NotoRegular','NotoBold'
W=1440
COL={'ink':'#17263C','muted':'#52647B','blue':'#2760AD','teal':'#15796F','purple':'#6852A3','orange':'#AC6522','bg':'#F5F7FB','border':'#D9E2EE','white':'#FFFFFF','pale':'#EAF1FC'}
H=1830
cv=None
checks=[]
page_meta=[]
sources={}

def col(x):return HexColor(COL.get(x,x))
def box(x,y,w,h,fill='white',stroke=None,r=14):
    cv.setFillColor(col(fill));cv.setStrokeColor(col(stroke or fill));cv.setLineWidth(1)
    cv.roundRect(x,H-y-h,w,h,r,fill=1,stroke=bool(stroke))
def wrap(t,w,size=18,font=REG):
    lines=[]
    for para in str(t).split('\n'):
        s=''
        for tok in re.findall(r'[A-Za-z0-9][A-Za-z0-9_./+×:&-]*|\s+|.',para):
            if pdfmetrics.stringWidth(s+tok,font,size)>w:
                if tok in '，。；：、？！）》】' and s:
                    prev=s.rstrip()
                    lines.append(prev[:-1]);s=prev[-1]+tok
                    continue
                if s:lines.append(s.rstrip());s=''
                if pdfmetrics.stringWidth(tok,font,size)>w:
                    for c in tok:
                        if pdfmetrics.stringWidth(s+c,font,size)>w:lines.append(s);s=''
                        s+=c
                else:s=tok.lstrip()
            else:s+=tok
        if s:lines.append(s.rstrip())
        elif not para:lines.append('')
    return lines
def text(x,y,t,size=18,fill='ink',font=REG,width=1300,leading=None,max_lines=None):
    lines=wrap(t,width,size,font);leading=leading or size*1.42
    if max_lines and len(lines)>max_lines:raise ValueError('Text overflow: '+str(t))
    cv.setFillColor(col(fill));cv.setFont(font,size)
    for i,s in enumerate(lines):
        cv.drawString(x,H-y-size-i*leading,s)
        checks.append({'page':len(page_meta)+1,'x':x,'y':y+i*leading,'w':pdfmetrics.stringWidth(s,font,size),'h':size,'page_h':H,'text':s})
    return len(lines)*leading
def link(x,y,w,h,url):cv.linkURL(url,(x,H-y-h,x+w,H-y),relative=0,thickness=0)
def picture(path,x,y,w,h):
    with Image.open(path) as im:
        im.load();iw,ih=im.size
        if im.mode not in ['RGB','RGBA']:im=im.convert('RGBA' if 'transparency' in im.info else 'RGB')
        reader=ImageReader(str(path)) if im.format=='JPEG' and im.mode=='RGB' else ImageReader(im)
        scale=min(w/iw,h/ih);pw,ph=iw*scale,ih*scale
        cv.drawImage(reader,x+(w-pw)/2,H-y-(h+ph)/2,width=pw,height=ph,mask='auto')
def header(code,title,sub,route,height=1830):
    global H
    H=height;cv.setPageSize((W,H));box(0,0,W,H,'bg',r=0)
    text(48,28,'AI COMPUTE VALUE CHAIN  /  PHOTO COMPANION  /  2026.10.18',13,'blue',BOLD)
    text(48,59,title,36,'ink',BOLD,width=1255,max_lines=1)
    text(49,115,sub,18,'muted',width=1280,max_lines=2)
    box(1322,43,70,58,'ink',r=10);text(1335,52,code,22,'white',BOLD,width=62)
    box(48,167,1344,54,'pale',r=10)
    text(67,181,route,18.5,'blue',BOLD,width=1306,max_lines=1)
def footer(note='全幅原图等比呈现，图片不按同一比例；各图为工序/产品实例，不代表同一批次或同一型号的完整供应链。'):
    cv.setStrokeColor(col('border'));cv.line(48,59,1392,59)
    text(48,H-47,note,12.8,'muted',width=1344,max_lines=2)
def short_kind(t):
    if '示意' in t:return '结构示意'
    if '渲染' in t:return '产品渲染图'
    if '非机房现场' in t or '非现场' in t:return '官方产品图'
    if '视频' in t:return '视频实拍画面'
    if '现场' in t:return '现场实拍'
    if '实拍' in t or '实物照片' in t:return '实物照片'
    if '实物图' in t:return '产品实物图'
    return '官方产品图'
def card(x,y,w,h,sid,title,caption=None,company=None,step=None,color='blue'):
    s=sources[sid]
    box(x,y,w,h,'white','border',r=14)
    box(x,y,5,h,color,r=2)
    text(x+20,y+15,(step or '')+'  '+s['ref'],13.5,color,BOLD,width=w-240,max_lines=1)
    kind=short_kind(s['type']);kw=pdfmetrics.stringWidth(kind,BOLD,13)+20
    box(x+w-kw-19,y+13,kw,24,'pale',r=6)
    text(x+w-kw-9,y+16,kind,13,color,BOLD,width=kw-15,max_lines=1)
    text(x+20,y+46,title,25,'ink',BOLD,width=w-40,max_lines=1)
    text(x+20,y+82,company or s['company'],17.5,'muted',width=w-40,max_lines=1)
    ih=h-234
    box(x+18,y+112,w-36,ih,'#FBFCFE',r=4)
    picture(ROOT/s['asset_path'],x+21,y+115,w-42,ih-6)
    cap=caption or s['caption']
    text(x+20,y+h-110,cap,18.2,'ink',width=w-40,leading=25.1,max_lines=3)
    credit=s.get('credit') or ('图片：'+s['company'])
    text(x+20,y+h-28,credit,12.2,'muted',width=w-40,max_lines=1)
    link(x+20,y+h-32,w-40,25,s['source_page'])
def finish(slug,title):
    page_meta.append({'slug':slug,'title':title,'width':W,'height':H});cv.showPage()
def plate(code,title,sub,route,cards,slug,height=None):
    n=len(cards)
    if n not in [4,6]:raise ValueError('Use four or six cards')
    ph=height or (1550 if n==4 else 1830)
    header(code,title,sub,route,ph)
    h=600 if n==4 else 482
    ys=[246+i*(h+22) for i in range(n//2)]
    for i,c in enumerate(cards):
        sid,ct,cap,company,step=c
        card([48,744][i%2],ys[i//2],648,h,sid,ct,cap,company,step,color='teal' if code in ['P2','P3'] else 'blue')
    footer();finish(slug,title)

def load_sources():
    rows=[]
    persisted=SRC/'photo_sources.json'
    raw=[TMP/g/(g+'-images.json') for g in ['equipment','memory','accelerator','server']]
    if not all(p.exists() for p in raw) and persisted.exists():
        for d in json.loads(persisted.read_text()):
            asset=ROOT/d['asset_path']
            with Image.open(asset) as im:im.verify()
            sources[d['id']]=d
        return
    for g in ['equipment','memory','accelerator','server']:
        p=TMP/g/(g+'-images.json')
        data=json.loads(p.read_text());data=data['images'] if isinstance(data,dict) else data
        rows += [d for d in data if d.get('selected',True) and d['id']!='eq-wafer']
    for i,d in enumerate(rows):
        src=Path(d['local_path'])
        with Image.open(src) as im:im.load();wh=im.size
        target=ASSET/(d['id']+src.suffix.lower())
        shutil.copyfile(src,target)
        company=d.get('company',d.get('provider',''))
        rec=dict(d)
        rec.update(ref=f'P{i+1:02}',company=company,caption=d.get('caption_zh',d.get('caption_cn','')),asset_path=str(target.relative_to(ROOT)),width=wh[0],height=wh[1])
        rec['credit']=d.get('attribution_text',d.get('attribution',d.get('credit','图片：'+company)))
        if company=='ASML':rec['credit']='图片：©ASML'
        if len(rec['credit'])>50:rec['credit']='图片：'+company
        sources[d['id']]=rec
    (SRC/'photo_sources.json').write_text(json.dumps(list(sources.values()),ensure_ascii=False,indent=2))
    with (SRC/'photo_sources.csv').open('w',encoding='utf-8-sig',newline='') as f:
        wr=csv.writer(f);wr.writerow(['编号','ID','公司/提供方','型号','图像类型','原始宽度','原始高度','来源页面','原图地址'])
        for s in sources.values():wr.writerow([s['ref'],s['id'],s['company'],s.get('model',s.get('model_era','')),s['type'],s['width'],s['height'],s['source_page'],s.get('original_image_url',s.get('image_url',''))])

def overview_photos():
    plate('P0','看见 AI 算力产业链：从晶圆到机房','把原总图中的抽象节点，对应到可辨认的实物和现场。','阅读层级：晶圆 → 封装颗粒 / 计算模组 → 服务器 → 机架 → 持续运营',[
      ('mem-dram-wafer','01  晶圆：许多芯片的共同起点','圆盘上有重复排列的芯片区域。图为美光 1β DRAM 晶圆，只作为晶圆形态示例。','Micron；图片由 IEEE Spectrum 发布','前道制造'),
      ('mem-dram-package','02  封装：内存颗粒的正反面','左边是封装顶面，右边是底部焊球；真正的 DRAM 裸片封在内部。','Samsung DDR5 DRAM','封装后的器件'),
      ('ACC01','03  加速模组：GPU 与 HBM','中央封装里有 GPU 与 HBM，外围电路板承担供电和连接；图为 H100 SXM 模组。','NVIDIA H100 SXM5','加速器模块'),
      ('server-internal','04  整机：多种部件汇合','CPU、主机内存、GPU 板卡、存储和风扇进入同一服务器；这里采用 PCIe GPU 服务器实例。','Supermicro SYS-421GE-TNRT','系统集成'),
      ('coreweave-liquid-racks','05  机架：计算与液冷连接','机架前方可见液冷软管、红蓝快接头和地板下管路，服务于整架设备的散热。','CoreWeave 现场；可见 Dell 标识','数据中心设施'),
      ('coreweave-cooling-maintenance','06  运营：把设备变成算力服务','技术人员持续检查设备和冷却系统；调度、网络、存储与运维共同支持云服务交付。','CoreWeave 机房运维现场','AI 云运营')
    ],'photo-00-overview')
def equipment_photos():
    plate('P1','半导体设备长什么样：六类关键现场与设备','设备外观用于认识分工；光刻、沉积、刻蚀与检测会在制造中多轮配合。','对应分图 01：设备装配 / 光刻 / 薄膜沉积 / 刻蚀 / 缺陷检测 / 电性测试',[
      ('eq-lithography','光刻机：把图形转移到光刻胶',None,'ASML TWINSCAN NXE:3400C','图形化'),
      ('eq-deposition','沉积设备：在表面形成薄膜',None,'Applied Materials Endura PVD','薄膜制造'),
      ('eq-etch','刻蚀机：有选择地去除材料',None,'Lam Research Versys Kiyo45','图形转移'),
      ('eq-inspection','检测设备：寻找晶圆上的缺陷',None,'KLA 3935 / 2965 BBP','过程控制'),
      ('eq-test','测试机：检查电信号与功能',None,'Teradyne Magnum 7H','器件测试'),
      ('eq-cleanroom','洁净室：设备制造现场',None,'ASML 设备装配现场','设备生产')
    ],'photo-01-equipment')
def ddr_photos():
    plate('P2','内存颗粒怎样变成一根服务器内存条','看清四个层级：晶圆、封装颗粒、模组电路板、主板内存插槽。','对应分图 02：晶圆 → 切割封装 → 模组装配 / 测试 → RDIMM → 服务器插槽',[
      ('mem-dram-wafer','01  切割前：DRAM 晶圆','许多 DRAM 芯片区域排在一张晶圆上。图为 1β DRAM 形态示例，原报道介绍 LPDDR5X。','Micron；图片由 IEEE Spectrum 发布','制造输出'),
      ('mem-dram-package','02  切割封装后：单颗 DRAM','正面有厂商与批次标识，底面有 BGA 焊球。内存条上常见的黑色方块就是这一类封装。','Samsung 12nm 级 DDR5 产品图','颗粒'),
      ('mem-module-production','03  模组生产与测试现场','图中是一批内存模组及生产设备。装配后还要完成相应功能、兼容性和可靠性检查。','Kingston Technology','模组制造'),
      ('mem-rdimm','04  成品：DDR5 RDIMM','PCB 上有 DRAM 颗粒及配套器件；下方金手指用于连接主板。本图用于辨认外观。','Micron 128GB DDR5 RDIMM','服务器内存条'),
      ('mem-ddr5-in-server','05  内存条放到主板哪里','实际内存插槽排在 CPU 散热器旁；散热器上方横放的两条是展品，不能当作安装位置。','SK hynix 展示的 Dell PowerEdge R770','整机安装'),
      ('mem-hbm4-wafer-exhibit','06  同场对照：晶圆与多种内存','展台同时展示 HBM 晶圆、HBM 产品、DDR5 模组和 GDDR 颗粒；它们处于不同层级。','SK hynix / DTF 2026','尺寸与形态对照')
    ],'photo-02-ddr-memory')
def hbm_photos():
    plate('P3','HBM 长什么样：外观、内部堆叠与计算封装','产品外观通常看不到 TSV 和层间连接，因此加入一张明确标注的结构示意。','对应分图 03：晶圆 → 减薄 / 堆叠 / 键合 → HBM 测试 → 与 GPU / ASIC 封装集成',[
      ('mem-hbm4-wafer-exhibit','01  实际 HBM 晶圆展品','左侧是官方确认的 HBM4 晶圆实物；展台展示颗粒和模组，用来观察不同形态。','SK hynix / DTF 2026','晶圆'),
      ('mem-hbm-stack-schematic','02  里面为何有多层芯片','示意图对比 TC-NCF 与 MR-MUF 的堆叠填充方式。不同厂家和产品不必使用同一方案。','SK hynix 官方结构图','堆叠 / 键合'),
      ('mem-hbm-product','03  完成堆叠后的 HBM 外观','黑色小方块是 HBM3E 产品。内部的多层 DRAM 与连接结构，在外观照片中看不到。','SK hynix HBM3E','HBM 成品'),
      ('eq-test','04  制造过程中仍然需要测试','Magnum 7H 用于 HBM 基础裸片及堆叠相关测试；图中是测试设备，不是存储器本体。','Teradyne Magnum 7H','电性测试'),
      ('ACC04','05  HBM 与计算芯片放在一起','TPU v4 封装实拍：中央为 ASIC，两边共四个 HBM 堆栈。这里展示封装内的并排关系。','Google / Jouppi 等，TPU v4','先进封装'),
      ('ACC01','06  封装进入加速模组','H100 的 GPU 与 HBM 封装进入 SXM 模组，再与底板和服务器集成；外围器件负责供电等。','NVIDIA H100 SXM5','模组 / 服务器')
    ],'photo-03-hbm')
def gpu_photos():
    cards=[
      ('ACC01','GPU + HBM：SXM 加速模组','中央 GPU 与周围 HBM 形成计算封装，再装到带供电和连接电路的 SXM 模组上。','NVIDIA H100 SXM5','数据中心路线'),
      ('ACC02','完整显卡：外壳与散热器','成卡的散热器遮住 GPU 与显存。RTX 5090 属于 GDDR7 显存路线。','NVIDIA RTX 5090 Founders Edition','GDDR 显卡路线'),
      ('ACC03','CPU、GPU 与网络的板级组合','原图标出两颗 Blackwell Ultra GPU、Grace CPU 和 ConnectX-8 SuperNIC；这是一套系统模组。','NVIDIA GB300 Grace Blackwell Ultra','另一代系统实例'),
      ('server-chassis','加速器进入服务器整机','整机把加速器与主机、内存、存储、供电及风扇组织起来，再进入机架部署。','Supermicro SYS-421GE-TNRT','整机交付')
    ]
    plate('P4','显卡与 AI 加速器：从封装看到整机','同属 GPU 系统，消费显卡、SXM 模组与超级芯片板的外形差别很大。','对应分图 04：GPU + GDDR → 显卡；GPU + HBM → 加速模组 → 系统',cards,'photo-04-gpu')
def tpu_photos():
    header('P5','Google TPU：同一代产品的三个物理层级','以下三张都来自 TPU v4 作者论文，保持封装、板卡、机架的代际一致。','对应分图 05：TPU v4 封装 → 四芯片液冷板 → 托盘与机架 → Pod / Slice',1690)
    card(48,246,648,640,'ACC04','01  单个 TPU v4 封装','中央是计算 ASIC，两侧共有四个 HBM 堆栈。封装表面能直接看出二者的相邻关系。','Google / Jouppi 等，ISCA 2023','Figure 2 左图')
    card(744,246,648,640,'ACC05','02  一块板上有四个 TPU','四颗封装通过板卡、液冷管路和连接接口形成下一层级的计算单元。','Google / Jouppi 等，ISCA 2023','Figure 2 右图')
    card(48,914,1344,646,'ACC06','03  机架组成更大的 TPU 系统','图中是八个机架，占论文所述 64 机架、4096 芯片 TPU v4 系统的八分之一。','Google / Jouppi 等，ISCA 2023','Figure 3')
    footer('TPU v4 用于完整展示物理层级；不是最新代际。作者论文完整引文与许可说明见本图册首页。')
    finish('photo-05-tpu','Google TPU 的封装、板卡与机架')
def asic_photos():
    c4=('ACC04','另一种定制 ASIC：Google TPU','TPU v4 的封装实例也说明：TPU 属于定制 AI ASIC，同样要进入板卡和服务器。','Google TPU v4','定制芯片对照')
    if 'ACC10' in sources:c4=('ACC10','Meta MTIA：内部业务用加速器','图为 Meta 官方公开的第二代 MTIA 实物，手指提供大小参照；照片不能证明内部采用 HBM。','Meta 第二代 MTIA，2024 年公布','Meta 产品实例')
    plate('P6','定制 AI 芯片的实物：芯片封装与服务器托盘','AWS、Microsoft、Meta 等公司围绕自己的工作负载定义芯片与系统。','对应分图 06：需求 / 设计 → 晶圆与封装 → 板卡 / 托盘 → 各自云平台或内部业务',[
      ('ACC07','AWS Trainium2：手中的芯片','这是 Trainium2 芯片封装实拍。双手提供直观大小参照，不能从照片推断全部内部规格。','Amazon / AWS Annapurna Labs','AWS 产品实例'),
      ('ACC08','Microsoft Maia 200：芯片近景','图中是微软自研 AI 推理加速器的封装外观，品牌标识与封装基板清晰可见。','Microsoft Maia 200','Microsoft 芯片'),
      ('ACC09','Maia 200：从芯片到托盘','同一代产品的服务器托盘：计算组件、液冷管路、连接接口与供电共同构成系统。','Microsoft Maia 200 server blade','Microsoft 系统'),
      c4
    ],'photo-06-custom-asic')
def server_photos():
    header('P7','服务器怎样装起来：内部、网络与机架','从服务器内部往外看，最后连接到集群网络和机房冷却。','对应分图 07：CPU / 内存 / 加速器 + 存储 / 网络 / 电源 → 整机 → 机架与集群',2068)
    cards=[
      ('server-internal','01  服务器内部的部件位置','上方是 GPU 扩展区域，中间是 CPU 与两侧内存插槽，下方可见成排风扇和前端存储区域。','Supermicro SYS-421GE-TNRT','内部结构'),
      ('server-chassis','02  完成装配的服务器','机箱内包含主机与加速器系统；前部有存储和进风区域。整机可上架部署。','Supermicro SYS-421GE-TNRT','整机'),
      ('nvidia-bluefield-3','03  DPU / 网卡的板卡形态','可看到 PCIe 金手指、网络接口和处理芯片；DPU 承担网络、存储、安全等卸载任务。','NVIDIA BlueField-3','服务器网络'),
      ('coreweave-switch','04  机架之间靠网络连接','光纤接入交换设备，把计算节点组织成集群。这张图来自 CoreWeave 的网络部署现场。','CoreWeave / NVIDIA SN6600-LD','集群互连'),
      ('coreweave-liquid-racks','05  机架中的液冷管路','粗软管、红蓝快接头与地板下管路，把机架内热量输送到设施冷却系统。','CoreWeave 液冷机架现场','散热'),
      ('vertiv-cdu','06  冷却液分配单元 CDU','CDU 在设施冷却回路与服务器回路之间管理换热和流体；它属于机房配套设备。','Vertiv CoolChip CDU 2300','冷却设施')
    ]
    for i,(sid,title,caption,company,step) in enumerate(cards):
        row=i//2
        card([48,744][i%2],[246,988,1492][row],648,[720,482,482][row],sid,title,caption,company,step)
    footer();finish('photo-07-server','服务器怎样装起来：内部、网络与机架')
def cloud_photos():
    plate('P8','CoreWeave 的算力云：服务器背后的真实现场','硬件需要持续的网络、冷却、调度与工程运维，才能成为可交付的云服务。','对应分图 08：硬件 + 机房设施 + 运营能力 → 云算力 → 模型 / 企业 / 开发者',[
      ('coreweave-rack-servers','服务器集群：密集的连接与设备','图为 CoreWeave 官方视频中的服务器后部，可看到扩展卡、线缆、网络连接和指示灯。','CoreWeave 机房视频实拍','算力基础'),
      ('coreweave-switch','网络集群：连接多个计算机架','交换设备与密集光纤为集群提供数据通路；模型任务通常需要多节点协同。','CoreWeave / NVIDIA 网络现场','集群连接'),
      ('coreweave-liquid-racks','液冷设施：把热量带走','计算设备的运行需要持续供电和散热。照片展示了机架端管路和地板下的冷却连接。','CoreWeave 液冷机架现场','基础设施'),
      ('coreweave-cooling-maintenance','运维现场：持续保持集群可用','技术人员检查液冷系统；运维、监控和调度与硬件一起构成云运营商的交付能力。','CoreWeave 工程运维现场','云运营')
    ],'photo-08-cloud')

def source_pages():
    rows=list(sources.values())
    for k in range(0,len(rows),8):
        global H
        H=1560;cv.setPageSize((W,H));box(0,0,W,H,'bg',r=0)
        text(48,35,'PHOTO SOURCES / 2026.10.18',14,'blue',BOLD)
        text(48,70,'实物配图来源与识别说明',34,'ink',BOLD)
        text(48,124,'图片旁的 P 编号对应这里；网页标题与原始图片地址另附于源文件表。',18,'muted')
        y=194
        for s in rows[k:k+8]:
            text(48,y,s['ref'],18,'blue',BOLD,width=62)
            text(123,y,s.get('model',s.get('title_zh',s.get('model_era',s['id']))),20,'ink',BOLD,width=1269,max_lines=2)
            meta=s['company']+' | '+short_kind(s['type'])+' | 原图 '+str(s['width'])+' × '+str(s['height'])
            text(123,y+38,meta,15.3,'muted',width=1269,max_lines=1)
            text(123,y+65,s['source_page'],13.8,'blue',width=1269,leading=19,max_lines=3)
            link(123,y+61,1269,62,s['source_page'])
            y+=155
        footer('保留原图内容、纵横比、厂商标识与出处；结构示意和产品渲染不标成生产现场照片。')
        finish('photo-sources-'+str(k//8+1),'配图来源 '+str(k//8+1))

def cover(pdf_path):
    global cv,H
    cv=canvas.Canvas(str(pdf_path),pagesize=(W,1560));H=1560
    box(0,0,W,H,'bg',r=0)
    text(48,39,'PHOTO-ILLUSTRATED EDITION  /  2026.10.18',15,'blue',BOLD)
    text(48,84,'美国 AI 算力产业链',47,'ink',BOLD)
    text(48,151,'流程图 + 实物照片 + 公司关系',33,'ink',BOLD)
    text(48,218,'9 张流程图与 9 页对应配图相邻编排：先看关联，再看实物。',22,'muted')
    for i,(sid,lab) in enumerate([('mem-dram-package','内存颗粒'),('eq-deposition','半导体设备'),('coreweave-cooling-maintenance','算力运营现场')]):
        x=48+i*458;box(x,283,428,325,'white','border')
        picture(ROOT/sources[sid]['asset_path'],x+14,299,400,246)
        text(x+18,563,lab,22,'ink',BOLD,width=390)
        text(x+18,594,sources[sid]['ref']+'  '+sources[sid]['credit'],11.5,'muted',width=390,max_lines=1)
    text(48,662,'怎么阅读',25,'ink',BOLD)
    text(48,710,'总图 → 制造底座 → DDR5 内存条 → HBM → GPU / 显卡 → TPU → 其他定制 ASIC → 服务器 → 云与应用。',20,'ink',width=1300,leading=30)
    text(48,798,'图像标识',25,'ink',BOLD)
    text(48,844,'实物 / 现场照片用于观察外观；官方产品图可能包含渲染；结构示意解释照片看不到的内部。所有图像保持原始比例。',20,'ink',width=1300,leading=30)
    text(48,937,'来源与使用说明',23,'ink',BOLD)
    text(48,980,'每张配图保留提供方和可点击来源。型号用作工序与形态实例；不同代际、厂商和展品不自动构成同一产品的供应清单。',17.5,'muted',width=1300,leading=26)
    text(48,1065,'TPU v4 图片完整引文',17.5,'ink',BOLD)
    citation=sources['ACC04']['full_citation']
    text(48,1098,citation,13.5,'muted',width=1344,leading=20,max_lines=6)
    text(48,1240,'TPU v4 作者论文许可说明：个人/课堂学习用途，保留作者与出处；其他再利用需遵循原论文许可。',15,'muted',width=1344)
    text(48,1280,'来源论文许可的中文说明（以原文为准）：',13,'ink',BOLD)
    notice='作者允许免费为个人或课堂用途制作该文全部或部分的数字或纸质副本，条件是副本不用于盈利或商业利益，且须在首页保留许可说明及完整引文。第三方组件的版权应受到尊重；其他用途应联系权利人。'
    text(48,1308,notice,13.5,'muted',width=1344,leading=22,max_lines=5)
    link(48,1098,1344,126,'https://doi.org/10.1145/3579371.3589350')
    text(48,1433,'原论文：TPU v4，Jouppi 等，ISCA 2023。图片来自作者公开稿；许可原文见来源首页。',13,'muted',width=1344)
    link(48,1430,1344,28,'https://suvinay.github.io/pubs/2023.tpu.isca.pdf')
    cv.showPage();cv.save()

def main():
    global cv
    load_sources()
    cv=canvas.Canvas(str(TMP/'photo-pages.pdf'),pagesize=(W,H),pageCompression=1)
    cv.setTitle('美国 AI 算力产业链：实物配图页')
    overview_photos();equipment_photos();ddr_photos();hbm_photos();gpu_photos();tpu_photos();asic_photos();server_photos();cloud_photos();source_pages();cv.save()
    photo=fitz.open(TMP/'photo-pages.pdf')
    for i,m in enumerate(page_meta[:9]):
        p=photo[i];pix=p.get_pixmap(matrix=fitz.Matrix(3840/p.rect.width,3840/p.rect.width),alpha=False)
        final=FIG/(m['slug']+'.png');temp=final.with_suffix('.tmp.png');temp.write_bytes(pix.tobytes('png'))
        with Image.open(temp) as im:im.verify()
        temp.replace(final);m.update(png=str(final),pixel_width=pix.width,pixel_height=pix.height)
    cover(TMP/'photo-cover.pdf')
    base=fitz.open(SRC/'base-atlas.pdf');cover_doc=fitz.open(TMP/'photo-cover.pdf');combined=fitz.open()
    combined.insert_pdf(cover_doc)
    toc=[[1,'配图版阅读导航',1]]
    for i in range(9):
        toc.append([1,page_meta[i]['title'],len(combined)+1])
        combined.insert_pdf(base,from_page=i,to_page=i)
        combined.insert_pdf(photo,from_page=i,to_page=i)
    toc.append([1,'公司角色与产业来源',len(combined)+1])
    combined.insert_pdf(base,from_page=9,to_page=len(base)-1)
    toc.append([1,'实物配图来源',len(combined)+1])
    combined.insert_pdf(photo,from_page=9,to_page=len(photo)-1)
    combined.set_toc(toc);combined.set_metadata({'title':'美国AI算力产业链 - 流程图与实物配图版','author':'Research and diagram synthesis','subject':'9 张流程图、9 页配图、公司目录与原始来源'})
    final=OUT/'美国AI算力产业链_流程图册_20261018.pdf'
    combined.save(TMP/'combined-final.pdf',garbage=4,deflate=True)
    shutil.copyfile(TMP/'combined-final.pdf',final)
    # Render every new page and the combined document contact sheet for visual review.
    for i,p in enumerate(photo):
        px=p.get_pixmap(matrix=fitz.Matrix(1200/p.rect.width,1200/p.rect.width),alpha=False);(REVIEW/f'photo-{i:02}.png').write_bytes(px.tobytes('png'))
    thumbs=[]
    for i,p in enumerate(combined):
        px=p.get_pixmap(matrix=fitz.Matrix(420/p.rect.width,420/p.rect.width),alpha=False)
        im=Image.frombytes('RGB',[px.width,px.height],px.samples);im.thumbnail((350,445))
        t=Image.new('RGB',(374,480),'#DCE2E9');t.paste(im,((374-im.width)//2,12));ImageDraw.Draw(t).text((14,458),f'PAGE {i+1:02}',fill='#142333');thumbs.append(t)
    sheet=Image.new('RGB',(4*374,ceil(len(thumbs)/4)*480),'#DCE2E9')
    for i,t in enumerate(thumbs):sheet.paste(t,((i%4)*374,(i//4)*480))
    sheet.save(REVIEW/'contact-sheet.jpg',quality=90)
    bad=[t for t in checks if t['x']<0 or t['y']<0 or t['x']+t['w']>W+1 or t['y']+t['h']>t['page_h']+1]
    (REVIEW/'layout-check.json').write_text(json.dumps({'pages':len(combined),'photo_sources':len(sources),'out_of_bounds':bad},ensure_ascii=False,indent=2))
    if bad:raise ValueError('Page bounds failure: '+str(bad[:2]))
    manifest={'date':'2026-10-18','combined_pdf':str(final),'page_count':len(combined),'photo_count':len(sources),'photo_pages':page_meta[:9],'source_pages':len(photo)-9,'base_pages':len(base)}
    (SRC/'photo_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    print(json.dumps({'pdf':str(final),'pages':len(combined),'unique_photo_sources':len(sources),'photo_pages':9,'review':str(REVIEW/'contact-sheet.jpg')},ensure_ascii=False))
if __name__=='__main__':main()
