#!/usr/bin/env python3
"""AI compute supply-chain atlas. Chinese typesetting, vector PDF and 3840px PNG.
Fonts: Noto Sans SC, https://github.com/google/fonts/tree/main/ofl/notosanssc
Run from the task workspace; Python dependencies: reportlab, PyMuPDF, Pillow.
"""
from pathlib import Path
from math import atan2, cos, sin, pi
import json, re, zipfile
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor
import fitz
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output'
DIAG = OUT / 'diagrams'
SRC = OUT / 'source'
for p in [OUT, DIAG, SRC]: p.mkdir(parents=True, exist_ok=True)
for name in ['Regular', 'Bold']:
    pdfmetrics.registerFont(TTFont('Noto'+name, str(ROOT/'tmp/fonts'/f'NotoSansSC-{name}.ttf')))
REG, BOLD = 'NotoRegular', 'NotoBold'
C = dict(bg='#F5F7FB', ink='#17263C', muted='#53657C', line='#72859D', border='#D9E2EE',
         blue='#2760AD', purple='#6852A3', teal='#15796F', orange='#AC6522', gray='#627285',
         pale_blue='#EAF1FC', pale_purple='#F0EBF8', pale_teal='#E7F4F0', pale_orange='#FFF2E4', pale_gray='#EDF1F5', white='#FFFFFF')
W, H = 1440, 1180
pdf_path = OUT / '美国AI算力产业链_流程图册_20261018.pdf'
cv = canvas.Canvas(str(pdf_path), pagesize=(W,H), pageCompression=1)
cv.setTitle('美国AI算力产业链：制造流程、服务器与云服务关系图册')
cv.setAuthor('Research and diagram synthesis')
page_meta, text_checks = [], []
current_h = H

def color(k): return HexColor(C.get(k,k))
def rect(x,y,w,h,fill='white',stroke=None,r=14,lw=1):
    cv.setFillColor(color(fill)); cv.setStrokeColor(color(stroke or fill)); cv.setLineWidth(lw)
    cv.roundRect(x,current_h-y-h,w,h,r,fill=1,stroke=bool(stroke))

def wrap(s,width,size=18,font=REG):
    result=[]
    for para in str(s).split('\n'):
        if not para: result.append(''); continue
        tokens = re.findall(r'[A-Za-z0-9][A-Za-z0-9_./+®×-]*|\s+|.',para)
        line=''
        for tok in tokens:
            if pdfmetrics.stringWidth(line+tok,font,size)<=width:
                line+=tok
            else:
                if line: result.append(line.rstrip()); line=''
                if pdfmetrics.stringWidth(tok,font,size)>width:
                    for char in tok:
                        if pdfmetrics.stringWidth(line+char,font,size)>width:
                            result.append(line);line=''
                        line+=char
                else: line=tok.lstrip()
        if line: result.append(line.rstrip())
    return result

def text(x,y,s,size=18,fill='ink',font=REG,width=None,leading=None,max_h=None):
    lines=wrap(s,width,size,font) if width else str(s).split('\n')
    leading=leading or size*1.43
    if max_h is not None and (len(lines)-1)*leading+size > max_h+1:
        raise ValueError(f'Text overflow at {x,y}: {s} | {len(lines)} lines in {max_h}')
    cv.setFillColor(color(fill));cv.setFont(font,size)
    for i,l in enumerate(lines):
        cv.drawString(x,current_h-y-size-i*leading,l)
        text_checks.append(dict(page=len(page_meta)+1,x=x,y=y+i*leading,w=pdfmetrics.stringWidth(l,font,size),h=size,text=l))
    return len(lines)*leading

def label(x,y,s,size=15,fill='muted'):
    wid=pdfmetrics.stringWidth(s,REG,size)+18
    rect(x-wid/2,y-3,wid,size+10,'bg',r=4)
    text(x-wid/2+9,y,s,size,fill)

def section(x,y,s,fill='blue'):
    rect(x,y+4,5,20,fill,r=2)
    text(x+15,y,s,18,fill,BOLD)

def node(x,y,w,h,title,body='',kind='blue',fs=18,ts=23,tag=None):
    rect(x,y,w,h,'pale_'+kind,'border',14)
    rect(x,y,5,h,kind,r=2)
    pad=20
    title_h=text(x+pad,y+15,title,ts,'ink',BOLD,w-pad*2,leading=ts*1.25)
    if body:
        top=y+20+title_h
        text(x+pad,top,body,fs,'muted',REG,w-pad*2,leading=fs*1.43,max_h=h-(top-y)-14)
    return dict(x=x,y=y,w=w,h=h)

def pt(n,side='b',f=.5):
    if side=='b': return n['x']+n['w']*f,n['y']+n['h']
    if side=='t': return n['x']+n['w']*f,n['y']
    if side=='l': return n['x'],n['y']+n['h']*f
    return n['x']+n['w'],n['y']+n['h']*f

def arrow(points,kind='blue',dash=False,width=2.4,head=9):
    cv.saveState();cv.setStrokeColor(color(kind));cv.setFillColor(color(kind));cv.setLineWidth(width)
    if dash: cv.setDash(6,5)
    p=cv.beginPath();p.moveTo(points[0][0],current_h-points[0][1])
    for x,y in points[1:]:p.lineTo(x,current_h-y)
    cv.drawPath(p,stroke=1,fill=0);cv.setDash()
    a,b=points[-2],points[-1];ang=atan2(b[1]-a[1],b[0]-a[0])
    hp=cv.beginPath();hp.moveTo(b[0],current_h-b[1])
    for q in [ang+pi*.83,ang-pi*.83]:hp.lineTo(b[0]+head*cos(q),current_h-(b[1]+head*sin(q)))
    hp.close();cv.drawPath(hp,fill=1,stroke=0);cv.restoreState()

def down(a,b,kind='blue',dash=False,mid=None):
    aa,bb=pt(a),pt(b,'t')
    if abs(aa[0]-bb[0])<1: arrow([aa,bb],kind,dash)
    else:
        mid=mid if mid is not None else (aa[1]+bb[1])/2
        arrow([aa,(aa[0],mid),(bb[0],mid),bb],kind,dash)

def right(a,b,kind='blue',dash=False): arrow([pt(a,'r'),pt(b,'l')],kind,dash)

def header(num,title,subtitle,height=H):
    global current_h
    current_h=height; cv.setPageSize((W,height))
    rect(0,0,W,height,'bg',r=0)
    text(48,27,'AI COMPUTE VALUE CHAIN   /   2026.10.18',13,'blue',BOLD)
    text(48,55,title,36,'ink',BOLD)
    text(49,111,subtitle,18,'muted',width=1270)
    rect(1320,41,72,57,'ink',r=10)
    text(1336,47,num,28,'white',BOLD)

def footer(sources,note='箭头表示工序或交付方向；同框列代表性参与者，并不表示器件可互换或存在所有两两供货关系。'):
    y=current_h-66
    cv.setStrokeColor(color('border'));cv.setLineWidth(1);cv.line(48,current_h-y,1392,current_h-y)
    text(48,y+10,note,12.8,'muted',width=1344)
    text(48,y+34,'来源：'+sources+'。完整标题、链接及证据边界见图册附录。',12.2,'muted',width=1300)

def finish(slug,title,height=H):
    page_meta.append(dict(slug=slug,title=title,width=W,height=height));cv.showPage()

def note(x,y,w,title,body,kind='gray',h=112):
    return node(x,y,w,h,title,body,kind,fs=17,ts=20)

def foundation():
    header('01','芯片的共同底座：设计 → 晶圆 → 封装','美国设计和设备企业连接全球晶圆厂；逻辑芯片、DRAM 与模拟/功率器件在制造时分流。')
    section(48,160,'设计流：交付芯片版图与制造数据','purple')
    a=node(48,197,410,138,'EDA 软件 / IP 授权','Synopsys、Cadence；Siemens EDA（德）\nArm（英）、Rambus、SiFive','purple',17.4)
    b=node(515,197,410,138,'架构与电路设计','NVIDIA、AMD、Broadcom、云厂商\n存储原厂和模拟芯片厂也自行设计','purple',17.4)
    d=node(982,197,410,138,'验证、物理设计、流片','RTL / 仿真 → 布局布线 → 签核\n向所选晶圆厂交付制造数据','purple',17.4)
    right(a,b,'gray',True);right(b,d)
    m=node(48,415,410,216,'硅片与工艺材料','硅片：信越、SUMCO（日本）\n材料/过滤：Entegris、Qnity\n光刻胶、气体、CMP 材料等\n输入晶圆厂的洁净制造过程','gray',17.6)
    f=node(515,415,410,216,'晶圆制造：反复加工','薄膜沉积 → 光刻 → 刻蚀/掺杂\n清洗 / CMP → 金属互连\n上述步骤按设计多次循环\n量测与缺陷控制贯穿全过程','blue',18)
    e=node(982,415,410,216,'制造设备与工艺控制','Applied Materials：沉积、CMP 等\nLam Research：刻蚀、沉积、清洗\nASML（荷兰）：光刻；TEL（日）\nKLA：检测、量测、良率控制','gray',17.4)
    right(m,f,'gray',True);arrow([pt(e,'l'),pt(f,'r')],'gray',True)
    arrow([pt(d,'b'),(1187,375),(720,375),pt(f,'t')])
    label(888,347,'版图 / 工艺数据')
    l=node(48,711,410,144,'逻辑晶圆：GPU / CPU / ASIC','TSMC（中国台湾）是关键参与者\nIntel Foundry、Samsung（韩）亦供代工\n具体产品按已披露代际判断','blue',17.1)
    r=node(515,711,410,144,'存储晶圆：DRAM / NAND','Micron（美国）\nSK hynix、Samsung（韩国）\n存储原厂负责自己的芯片制造','teal',17.1)
    p=node(982,711,410,144,'模拟 / 互连 / 功率器件','TI、MPS 等芯片企业；部分外包\nGlobalFoundries 等特色工艺厂\n芯片功能决定工艺，并非全用最小节点','orange',17.1)
    down(f,l,mid=672);down(f,r);down(f,p,mid=672)
    z=node(280,930,880,113,'晶圆电测 → 切割 → 封装集成 → 成品测试','封装：TSMC、Amkor、ASE/SPIL（中国台湾）等；载板见附录\n测试设备/探针卡：Teradyne、FormFactor、Advantest（日本）','blue',17.6)
    for n in [l,r,p]:down(n,z,mid=892)
    footer('S01-S10、S54-S60','简化流程：测试贯穿多个阶段；TSMC 的先进逻辑代工不等于替各存储原厂制造全部 DRAM。')
    finish('01-chip-foundation','01 芯片共同底座')

def dimm():
    header('02','内存条如何制造：从 DRAM 颗粒到服务器 DIMM','先制造存储芯片，再将芯片、接口器件与 PCB 装成模组；金士顿与美光承担的角色不同。')
    section(48,163,'A  存储芯片原厂：提供容量','teal')
    xs=[48,391,734,1077];ww=315
    top=[]
    for x,t,b in zip(xs,['DRAM 电路设计','DRAM 晶圆制造','晶圆电测 / 切割','颗粒封装 / 测试'],[
        'Micron\nSK hynix / Samsung（韩）','存储原厂晶圆厂\n沉积、光刻、刻蚀等反复加工','筛选良品与速度等级\n使用测试机、探针卡','BGA 等 DRAM 封装\n部分高容量产品采用堆叠裸片']):
        top.append(node(x,202,ww,151,t,b,'teal',17.7,22))
    for a,b in zip(top,top[1:]):right(a,b)
    section(48,403,'B  模组厂：把颗粒变成一根可插拔的内存条','blue')
    pcb=node(48,452,410,205,'PCB / 结构 / 平台规格','多层电路板、金手指、被动器件\n按 Intel / AMD 等平台要求设计\n容量、布线、供电和信号完整性\n部件兼容性需逐项验证','gray',17.8)
    ass=node(515,452,410,205,'模组设计与物料齐套','原厂模组：Micron 等\n独立模组：Kingston、SMART Modular\nSMART 为 Penguin Solutions 品牌\n合并 DRAM、PCB 和配套芯片','blue',17.6)
    chipset=node(982,452,410,205,'接口与管理芯片供料','Rambus（美）、Renesas（日）\nMontage / 澜起（中国）\nRDIMM：RCD、PMIC、SPD Hub、TS\nMRDIMM：MRCD、MDB\n同样需要 PMIC、SPD Hub、TS','purple',17.6)
    right(pcb,ass,'gray',True);arrow([pt(chipset,'l'),pt(ass,'r')])
    arrow([pt(top[-1]),(1234,385),(720,385),pt(ass,'t')])
    label(1001,366,'合格 DRAM 颗粒')
    bottom=[]
    for x,t,b in zip(xs,['SMT 贴装 / 回流焊','配置写入 / 电性测试','平台验证 / 老化','成品内存条'],[
        '锡膏印刷 → 贴装芯片\n回流焊 → 光学检查','写入 SPD 配置\n检查容量、时序、速度和功能','检查主板 / CPU / BIOS 兼容\n服务器负载与可靠性测试','DDR5 RDIMM / MRDIMM\n插入主板，作为 CPU 主机内存']):
        bottom.append(node(x,751,ww,172,t,b,'blue',17.8,22))
    arrow([pt(ass),(720,704),(205,704),pt(bottom[0],'t')])
    for a,b in zip(bottom,bottom[1:]):right(a,b)
    note(48,973,1344,'可公开核对的供货关系','Kingston 官方列出 Micron、SK hynix、Samsung 为 DRAM 供应商。模组厂采购颗粒后完成设计、装配与验证；不能据此认定某一型号同时使用三家的颗粒。','teal',104)
    footer('S11-S15','RCD 缓冲命令/地址/时钟；PMIC 管电源；SPD 存配置；TS 测温；MRCD/MDB 用于多 Rank 复用。')
    finish('02-ddr-memory-module','02 DDR5 内存条制造')

def hbm():
    header('03','HBM 如何制造：先堆存储，再与计算芯片封装','HBM 也是 DRAM；它通常集成在高端 AI 加速器封装中，连接方式与 CPU 内存条不同。')
    a=node(48,191,410,162,'HBM 专用 DRAM 晶圆','Micron（美国）\nSK hynix / Samsung（韩国）\n按 HBM 带宽、容量、功耗协同设计','teal',18)
    b=node(515,191,410,162,'基础裸片：并行制造','接口、逻辑及测试等功能\n已公开例子：SK hynix HBM4\n基础裸片采用 TSMC 逻辑工艺','purple',18)
    c=node(982,191,410,162,'测试设备与探针卡','FormFactor（美）：探针卡\nTeradyne（美）/ Advantest（日）\n提供 HBM 电性测试设备','gray',17.8)
    d=node(48,430,410,179,'TSV / 晶圆电测 / 减薄','形成垂直连接的硅通孔\n筛选良品、背面处理、互连加工\n减薄与切割；顺序随工艺变化\n减薄/切割设备：DISCO（日本）','teal',18)
    e=node(515,430,410,179,'堆叠 / 键合 / 填充','多层 DRAM + 基础裸片\n对准、键合、形成垂直电连接\nSK hynix MR-MUF 为一种公开路线','teal',18)
    f=node(982,430,410,179,'HBM 堆栈测试','功能、速度、互连与可靠性验证\n输出经过筛选的 HBM 堆栈\n在此前后的多个阶段均有测试','teal',18)
    down(a,d);down(b,e);right(d,e);right(e,f)
    down(c,f,'gray',True)
    g=node(48,704,410,156,'GPU / ASIC 逻辑裸片','来自计算芯片制造链\nNVIDIA、AMD、Google / 云厂 ASIC\n设计方与代工方承担不同职责','purple',18)
    z=node(515,704,410,156,'先进封装：多路汇合','逻辑裸片 + HBM + 中介层/载板\n代表：TSMC CoWoS\n封装后测试，再进入板卡/模组','blue',18)
    sub=node(982,704,410,156,'中介层 / 封装载板','TSMC 中介层/局部互连技术等\n载板：IBIDEN（日）、欣兴（台）等\nABF 绝缘材料：味之素（日本）','gray',17.8)
    right(g,z);arrow([pt(sub,'l'),pt(z,'r')])
    arrow([pt(f),(1187,657),(720,657),pt(z,'t')])
    label(968,637,'合格 HBM 堆栈')
    o=node(515,944,410,115,'AI 加速器封装 / 模组','送入 GPU/ASIC 板卡、计算托盘及服务器','blue',18)
    down(z,o)
    note(48,921,410,'公开产品采用','Micron HBM4 → NVIDIA Vera Rubin\nSK hynix HBM3E → NVIDIA GB300\n仅为供货例子，不代表独家。','teal',144)
    note(982,921,410,'三类内存的典型位置','DDR5 DIMM：CPU 主板插槽\nGDDR：通常焊在显卡 PCB\nHBM：计算裸片旁的高密度封装','gray',144)
    footer('S07、S10、S16-S20、S54','此图为常见 HBM 工艺的简化合并，不能把 MR-MUF、堆叠层数或具体设备视为所有厂商的统一工艺。')
    finish('03-hbm-manufacturing','03 HBM 制造与封装')

def gpu():
    header('04','GPU 如何成为显卡与 AI 加速器','共同经历芯片设计与制造；之后按产品走 GDDR 板卡或 HBM 高密度封装等路线。')
    xs=[48,391,734,1077];ww=315
    row=[]
    for x,t,b in zip(xs,['NVIDIA / AMD 设计','EDA / 验证 / 流片','晶圆代工','晶圆电测 / 切割'],[
        '计算架构、芯粒、显存接口\nCUDA / ROCm 配套开发','逻辑实现、布局布线\n签核后交付版图','关键参与者：TSMC（台）\nBlackwell Ultra：TSMC 4NP','取得合格 GPU 裸片 / Chiplet\n进入不同产品封装路线']):
        row.append(node(x,193,ww,144,t,b,'purple',17.5,21.5))
    for a,b in zip(row,row[1:]):right(a,b)
    section(48,394,'路线 A  GDDR 显卡 / 专业或推理 GPU','orange')
    section(758,394,'路线 B  HBM 高端 AI 加速器','teal')
    a=node(48,438,628,158,'GPU 封装 + 板级 GDDR 颗粒','GPU 先完成自身封装；GDDR 来自 Micron / SK hynix / Samsung\nGDDR 颗粒独立封装后，与 GPU 一同焊在显卡 PCB 上\n另需 PCB、供电芯片、连接器与被动器件','orange',17.8)
    b=node(764,438,628,158,'GPU 裸片 + HBM + 中介层/载板','GPU 逻辑裸片与 HBM 堆栈在先进封装中汇合\n代表方案：TSMC CoWoS；封装后再次测试\nHBM 的 DRAM 制造及堆叠见图 03','teal',17.8)
    arrow([pt(row[-1]),(1234,366),(362,366),pt(a,'t')])
    arrow([(1128,366),(1078,366),pt(b,'t')])
    aa=node(48,653,628,156,'显卡制造：SMT、散热器、固件与整卡测试','NVIDIA 公版；PNY（美）；ASUS / MSI / GIGABYTE（台）等\n示例：GeForce RTX 50 使用 GDDR7\n具体 GPU 伙伴名单和颗粒来源随品牌、型号变化','orange',17.7)
    bb=node(764,653,628,156,'加速模组 → 底板 / 计算托盘','NVIDIA SXM → HGX；AMD OAM → UBB\n也有采用 PCIe 形态的数据中心加速卡\n加上 CPU、主机内存、网络、SSD、供电与散热','teal',17.7)
    down(a,aa);down(b,bb)
    aaa=node(48,871,628,122,'PCIe 显卡 → PC / 工作站 / 部分服务器','用途覆盖图形、内容创作、本地 AI 与部分推理工作负载','orange',18)
    bbb=node(764,871,628,122,'Dell / HPE / Supermicro / ODM → AI 机架','系统集成与验证后，交付算力运营商、综合云和企业','blue',18)
    down(aa,aaa);down(bb,bbb)
    text(48,1038,'边界：数据中心 GPU 并非全部采用 HBM；例如 NVIDIA RTX PRO 6000 Blackwell Server Edition 采用 GDDR7。',16.5,'muted',width=1344)
    footer('S07、S19、S21-S24','GPU 是芯片/处理器；显卡是板级产品；SXM/OAM 是模组形态；HGX/UBB 是更高一层的系统底板。')
    finish('04-gpu-graphics-card','04 GPU 与显卡制造')

def tpu():
    header('05','Google TPU：定制 ASIC → 托盘 → Pod → 云','TPU 属于定制 AI ASIC。公司级合作已公开，但不能据此补全每代 TPU 未披露的制造清单。')
    a=node(48,194,410,158,'Google：需求 / 架构 / 软件','定义模型工作负载、计算与互连\n协同开发编译器和运行时\nTPU 是专用 AI 加速器产品线','purple',18)
    b=node(515,194,410,158,'Broadcom：定制 TPU 合作','2026-04 SEC 文件确认：\n为 Google 未来多代 TPU 开发与供应\n并供应下一代 AI 机架的网络等组件','purple',17.8)
    c=node(982,194,410,158,'逻辑实现 / 验证 / 流片','芯片设计团队与 EDA / IP 生态\n完成物理设计、签核\n交付晶圆制造数据','purple',18)
    right(a,b,'gray',True);right(b,c)
    fab=node(48,447,410,186,'晶圆制造 / 测试 / 封装','外部晶圆制造 → 逻辑裸片\n合格 TPU ASIC + HBM → 封装\n具体代际的代工、HBM、OSAT 分工\n需要按产品公开资料进一步确认','blue',17.8)
    pool=node(515,447,877,186,'已披露的是 Broadcom 公司级制造伙伴池','FY2025 年报披露 TSMC 等晶圆制造伙伴。\n组测伙伴包括 TSMC、ASE、Amkor、SPIL、Foxconn 等。\n这份公司级名单没有将每一家绑定到某一款 TPU，不等于型号级供货清单。','gray',18)
    arrow([pt(c),(1187,391),(253,391),pt(fab,'t')])
    arrow([pt(pool,'l'),pt(fab,'r')],'gray',True)
    section(48,682,'公开物理架构实例：TPU v4，统一使用同一代数据','teal')
    ns=[];xs=[48,391,734,1077]
    for x,t,b in zip(xs,['1 个 TPU 封装','1 块液冷 PCB','1 个机架','完整 TPU v4 系统'],[
        '中央 ASIC + 4 个 HBM 堆栈\n论文披露 7nm 工艺','4 个 TPU 封装\n配套 CPU Host / 托盘','16 组托盘 / Host\n共 64 个 TPU','64 个机架 / 4096 个 TPU\nICI 与光交换 OCS 互联']):
        ns.append(node(x,722,315,150,t,b,'teal',17.5,21.7))
    for x,y in zip(ns,ns[1:]):right(x,y)
    cloud=node(48,958,825,117,'TPU Pod / Slice → Google Cloud','Cloud TPU VM、GKE、Vertex AI；也支持 Google 内部模型和业务使用','purple',18)
    down(ns[-1],cloud,mid=914)
    note(929,958,463,'产品代际说明','v4 数量只作制造到系统层级的完整例子；\n不表示它是最新 TPU，也不套用到其他代。','gray',117)
    footer('S25-S28','Google 与 Broadcom 的开发/供应合作有直接披露；制造伙伴池是公司级信息，不能代替 TPU 的具体 BOM。')
    finish('05-google-tpu','05 Google TPU 制作与部署')

def custom_asic():
    header('06','其他定制 AI 芯片：云厂商自研 + 产业伙伴','AWS、Microsoft、Meta 的需求和服务出口不同；定制芯片也不必统一采用 HBM。')
    a=node(48,191,312,136,'需求 / 架构定义','云厂商定义计算、能效和成本\n结合模型与软件栈设计','purple',17.7,22)
    b=node(392,191,312,136,'设计 / IP / 验证','自研 + 按项目引入设计伙伴\n片上 SRAM 与内存接口设计','purple',17.7,22)
    c=node(736,191,312,136,'流片 / 晶圆 / 封装','代工、裸片测试与封装\nHBM/LPDDR 按封装或板级配置','blue',17.3,22)
    d=node(1080,191,312,136,'板卡 / 系统 / 软件','服务器与互连、供电、散热\n编译器、运行时、集群验证','blue',17.7,22)
    for x,y in zip([a,b,c],[b,c,d]):right(x,y)
    section(48,381,'三条公开产品路径：每列内部是同一体系','purple')
    aa=node(48,421,410,157,'AWS · Annapurna Labs','Trainium：训练与推理\nInferentia：推理\nMarvell 有 AWS 定制 AI 产品合作','purple',18)
    bb=node(515,421,410,157,'Microsoft · Maia','微软定义并自研 AI 加速器\nMaia 200：推理用途的公开例子\n不补入未披露的设计外包方','purple',18)
    cc=node(982,421,410,157,'Meta · MTIA','Meta 自研 AI 计算体系\n2026 年已公布 Broadcom 合作\n覆盖芯片设计、封装与网络','purple',18)
    aaa=node(48,634,410,184,'制造与内存：Trainium 体系','TSMC 已确认 Trainium 使用 CoWoS\nTrainium2 / Trn2 采用 HBM3\n16 芯片实例 / 64 芯片 UltraServer\nNeuronLink、EFA 组成集群','blue',17.5)
    bbb=node(515,634,410,184,'Maia 200 公开结构','TSMC 3nm；HBM3e\n加速器托盘与 Ethernet 集群\n按 Azure 数据中心整体设计部署\n软件工具与硬件同步优化','blue',17.8)
    ccc=node(982,634,410,184,'MTIA 的内存随代际变化','2024 年公开 MTIA：\nTSMC 5nm + LPDDR5\n板卡 → 机架 → 自用集群\n这一配置不套用至后续代际','blue',17.8)
    for x,y in zip([aa,bb],[aaa,bbb]):down(x,y)
    down(cc,ccc,'gray',True);label(1187,598,'2024 年结构示例',13)
    a4=node(48,874,410,112,'AWS 云服务','EC2 / SageMaker 等\nNeuron 软件栈配套','purple',18)
    b4=node(515,874,410,112,'Microsoft 云与应用','Azure / Foundry、Copilot\n及内部模型业务','purple',18)
    c4=node(982,874,410,112,'Meta 内部业务','推荐、广告及其他 AI 业务\n自用角色，不是通用云实例商','purple',18)
    for x,y in zip([aaa,bbb,ccc],[a4,b4,c4]):down(x,y,'purple')
    text(48,1030,'新进入者例子：OpenAI 与 Broadcom 已宣布自研加速器合作；规划部署不等于已完成交付，未披露制造分工不作补全。',16.4,'muted',width=1344)
    footer('S07、S29-S34','合作范围不能扩大解释：Marvell-AWS 公告并未据此确认某代 Trainium 由 Marvell 独家设计。')
    finish('06-custom-ai-asics','06 定制 AI ASIC')

def server():
    header('07','AI 服务器如何组成：部件 → 节点 → 机架 → 集群','加速器之外，还需要主机、存储、互连、供电、散热，以及系统软件和整机验证。')
    xs=[48,391,734,1077]
    top=[]
    for x,t,b,k in zip(xs,['计算与主机 CPU','加速器与 HBM','主机内存','SSD / 共享存储'],[
        'Intel Xeon、AMD EPYC\nNVIDIA Grace / Vera\n操作系统、调度与数据预处理',
        'NVIDIA / AMD GPU\nGoogle TPU / 云厂 ASIC\n主计算任务与高速本地内存',
        'DDR5 RDIMM / MRDIMM\n部分平台用 LPDDR / SOCAMM\nMicron、Kingston、SMART 等',
        'Micron、Samsung（韩）\nSolidigm（SK hynix 旗下）等\n系统：DDN、NetApp、VAST 等'],['purple','teal','teal','orange']):
        top.append(node(x,190,315,166,t,b,k,17.2,22))
    low=[]
    for x,t,b in zip(xs,['板级互连 / 信号调理','网络芯片 / NIC / 光电','PCB / 连接 / 机械件','板级供电 / 热管理'],[
        'Broadcom、Astera Labs\nMarvell、Credo\nPCIe / CXL、Switch、Retimer',
        'NVIDIA、Broadcom、Marvell\nCredo：AEC / DSP\nCoherent、Lumentum：光电',
        'TTM：多层高速 PCB\nAmphenol：连接器/线缆\n以及全球机箱、背板制造商',
        'TI、MPS：电源控制/功率器件\nPSU、风扇或液冷冷板\n为各芯片与板卡供电、散热']):
        low.append(node(x,401,315,166,t,b,'gray',17.1,21.6))
    integ=node(243,647,954,130,'整机 / 机架集成：多种供货路径并行','品牌与系统：Dell、HPE、Supermicro；ODM：Quanta/QCT、Wiwynn、Foxconn、Wistron（台）等\nODM 可供品牌商，也可直接服务云厂；装配、布线、固件、散热及负载测试后交付','blue',18)
    for n in low:down(n,integ,mid=607)
    # Each upper component feeds the integration bus via the clear column gaps.
    for i,n in enumerate(top):
        rail=[378,720,1063,1406][i]
        arrow([pt(n,'r'),(rail,273),(rail,607),(720,607),pt(integ,'t')],width=1.7)
    net=node(48,840,410,167,'集群网络设备与系统','Arista、Cisco、NVIDIA\nHPE / Juniper\nInfiniBand 或 Ethernet 等\n交换芯片 / NIC / 光铜连接共同配合','orange',17.5)
    cl=node(515,840,410,167,'AI 机架 / 服务器集群','机内与跨机架互连\n节点调度、共享存储、故障管理\n驱动/固件、CUDA/ROCm/厂商栈\n交付自用或云端运营','blue',17.5)
    infra=node(982,840,410,167,'机房供电 / 冷却 / 空间','Vertiv；Eaton（爱尔兰注册）\nSchneider Electric（法）等\nEquinix、Digital Realty 等机房\n电力、UPS、配电、制冷与托管','gray',17.3)
    down(integ,cl);right(net,cl);arrow([pt(infra,'l'),pt(cl,'r')],'gray',True)
    text(48,1046,'明确供货例子：Broadcom Tomahawk 6 → Arista 交换机；NVIDIA 平台 → Dell PowerEdge 机架 → CoreWeave。',16.5,'muted',width=1344)
    footer('S18、S35-S46','网络器件不等于整台交换机；板级电源芯片不等于机房 UPS/供配电。主机内存类型需与 CPU 平台匹配。')
    finish('07-ai-server-assembly','07 AI 服务器与集群集成')

def cloud():
    header('08','CoreWeave 在哪里：服务器变成算力，再变成服务','硬件交付、机房托管、云算力和模型 API 是不同业务；下图按交付内容连接。')
    hw=node(48,192,410,161,'硬件交付','NVIDIA 平台 + Dell 机架\n公开实例：PowerEdge XE9712\nGB200 NVL72 液冷集成机架','blue',18)
    dc=node(515,192,410,161,'机房 / 托管服务','Core Scientific → CoreWeave\n提供 HPC 数据中心基础设施\n这是托管合同关系','gray',18)
    soft=node(982,192,410,161,'运营软件与工程','GPU 集群、存储网络、监控\nKubernetes / Slurm 调度\n把硬件变成可租用、可运维的服务','gray',18)
    cw=node(48,448,410,178,'AI 专用云：CoreWeave','整合服务器 + 机房 + 运营能力\n向 AI 企业和其他客户出售算力\n同类角色：Lambda、Crusoe 等\n它本身已经是云服务厂商','purple',18)
    hyper=node(515,448,410,178,'综合云：自建与采购并存','AWS、Microsoft Azure\nGoogle Cloud、Oracle OCI\n直接购 GPU / 服务器；部分自研芯片\n也可按项目采购外部算力','purple',17.8)
    own=node(982,448,410,178,'企业自用算力','Meta 等企业自有集群\n运营自己的训练与推理任务\n也可采购第三方算力\n不必对外出售通用云实例','purple',18)
    arrow([pt(hw),(253,380),(171,380),pt(cw,'t',.3)])
    arrow([pt(dc),(720,396),(335,396),pt(cw,'t',.7)],'gray',True)
    arrow([pt(soft),(1187,375),(23,375),(23,536),pt(cw,'l')],'gray',True)
    # Specific cross-layer cloud relationship, not a mandatory sequence.
    model=node(48,730,628,147,'模型研发 / 训练与推理','OpenAI、Anthropic、Google DeepMind 等\n从一家或多家算力运营商采购，或结合自建资源\n完成模型开发与持续运行','purple',18)
    ent=node(764,730,628,147,'企业 / 开发者直接租用云资源','GPU / TPU / Trainium 实例、裸金属、托管集群\n企业可以自行训练、微调和部署开源或自有模型\n也可直接使用模型 API','purple',18)
    down(cw,model,'purple',mid=677);down(hyper,model,'purple',mid=677);down(hyper,ent,'purple',mid=698)
    api=node(48,954,628,113,'模型 API / 托管模型平台','模型厂直供 API；云厂通过 Bedrock、Vertex AI、Foundry 等提供服务','purple',17.7)
    app=node(764,954,628,113,'AI 应用 / 企业流程 / 最终用户','助手、搜索、编码、广告、客服、内容生成\n例如 Microsoft、Google、Salesforce、ServiceNow 等','purple',17.7)
    down(model,api,'purple');right(api,app,'purple');down(ent,app,'purple')
    arrow([pt(own,'r'),(1414,537),(1414,1010),pt(app,'r')],'purple')
    label(250,648,'训练 / 推理算力',14)
    label(745,648,'公开合作：CoreWeave → Microsoft（部分算力）',13)
    label(858,679,'云实例 / 集群',14)
    label(718,936,'模型 API',14)
    footer('S25、S44、S47-S53','具体证据：CoreWeave → OpenAI / Microsoft；OCI → OpenAI；AWS / Google 的算力支持 Anthropic。云之间并非固定串行。')
    finish('08-cloud-services','08 CoreWeave 与云服务')

def overview():
    ht=1510
    header('总图','美国 AI 算力全产业链：从芯片底座到应用','阅读顺序：设计与制造 → 器件汇合 → 服务器/数据中心 → 三类算力运营者 → 模型与应用。',ht)
    # Foundation: three roles, with correctly typed entry paths.
    ed=node(48,178,410,132,'设计底座：EDA / IP','Synopsys、Cadence、Rambus、SiFive\nSiemens EDA（德）、Arm（英）','purple',17.3)
    ma=node(515,178,410,132,'工艺材料 / 硅片','Entegris、Qnity\n信越、SUMCO、味之素（日本）等','gray',17.3)
    eq=node(982,178,410,132,'设备 / 量测 / 测试','Applied Materials、Lam、KLA\nTeradyne、FormFactor；ASML（荷）等','gray',17.1)
    log=node(48,376,410,163,'计算芯片：设计 → 晶圆','NVIDIA / AMD GPU、CPU\nGoogle TPU；AWS / Microsoft / Meta ASIC\nBroadcom / Marvell：定制合作\n代工：TSMC 等；逻辑裸片输出','purple',16.9)
    mem=node(515,376,410,163,'存储原厂：DRAM / NAND','Micron（美国）\nSK hynix / Samsung（韩国）等\nDDR / LPDDR、GDDR、HBM、SSD\n具体存储形态按产品分流','teal',17.3)
    aux=node(982,376,410,163,'互连 / 网络 / 电源器件','Broadcom、Marvell、Astera Labs\nCredo、Coherent、Lumentum\nTI、MPS；PCB / 连接器等\n各自经过设计、晶圆与封测','orange',17.1)
    # Common upstream enablement bus, covering each manufacturing branch.
    for n in [ed,ma,eq]:arrow([pt(n),(pt(n)[0],342)],'gray',True,width=1.7,head=0)
    arrow([(253,342),(1187,342)],'gray',True,width=1.7,head=0)
    for n in [log,mem,aux]:arrow([(pt(n,'t')[0],342),pt(n,'t')],'gray',True,width=1.7)
    # Manufacturing-to-components convergence.
    acc=node(48,615,410,146,'CPU / AI 加速器封装与模组','CPU 封装；GPU/ASIC + HBM 先进封装\nTSMC、Amkor、ASE/SPIL 等参与\nGPU 亦可走封装 + 板级 GDDR 路线','blue',17.1,21)
    dim=node(515,615,410,146,'CPU 主机内存 / 存储','DDR → Micron / Kingston / SMART 模组\n部分平台用 LPDDR / SOCAMM\nNAND → SSD / 共享存储系统','teal',17.1)
    nw=node(982,615,410,146,'网络 / 板卡 / 供电系统','Arista、Cisco、NVIDIA、HPE/Juniper\nPCB、线缆、连接器、PSU 等\n组件与系统按平台配套','orange',17.1)
    down(log,acc);down(mem,dim);down(aux,nw)
    arrow([pt(mem,'b',.25),(617,579),(253,579),pt(acc,'t')],'teal');label(427,550,'HBM / GDDR')
    srv=node(48,838,877,121,'服务器 / 机架集成：OEM、ODM 与云厂共同参与','Dell、HPE、Supermicro；Quanta/QCT、Wiwynn、Foxconn、Wistron（台）等\nCPU + 加速器 + 内存 + SSD + 网络 + 供电/散热 → 系统验证与交付','blue',17.5)
    fac=node(982,838,410,121,'机房设施 / 电力 / 冷却','Vertiv、Eaton、Schneider Electric 等\nEquinix、Digital Realty、Core Scientific','gray',16.7)
    for a in [acc,dim,nw]:down(a,srv,mid=802)
    ops=[]
    for x,t,b in zip([48,515,982],['AI 专用云','综合云','企业自用集群'],[
        'CoreWeave、Lambda、Crusoe 等\n以商用 GPU 集群为主，运营与出租',
        'AWS、Azure、Google Cloud、OCI\nGPU 与各家自有 ASIC 路线并存',
        'Meta 等企业\n自建与外部采购可同时存在']):
        ops.append(node(x,1035,410,123,t,b,'purple',17.1))
    for o in ops:down(srv,o,mid=995)
    arrow([pt(fac,'r'),(1420,898),(1420,1017),(335,1017)],'gray',True,width=1.7,head=0)
    for o in ops:arrow([(pt(o,'t',.7)[0],1017),pt(o,'t',.7)],'gray',True,width=1.7)
    # Service outlets remain parallel; owned cluster goes directly to applications.
    api=node(48,1243,628,134,'模型公司 / 模型 API / 云 AI 平台','OpenAI、Anthropic、Google 等模型厂\n模型直供 API；Bedrock / Vertex AI / Foundry 分发\n训练与推理可以采购一家或多家的算力','purple',17.1)
    app=node(764,1243,628,134,'企业应用 / 开发者 / 最终用户','直接租算力自建模型，或调用模型 API\n搜索、助手、编码、广告、客服、业务流程\nMicrosoft、Google、Salesforce、ServiceNow 等','purple',17.1)
    down(ops[0],api,'purple',mid=1204);down(ops[1],api,'purple',mid=1204)
    down(ops[1],app,'purple',mid=1221);down(ops[2],app,'purple')
    right(api,app,'purple')
    label(719,1394,'TPU / Trainium / Maia 等各归其平台；CoreWeave 与综合云存在部分横向容量合作，详见分图 08。',13.4)
    footer('分图 01-08 与全部来源目录','蓝/青实线＝器件与硬件工序；紫实线＝算力/模型服务；灰虚线＝工具、材料、设施支持。同行参与者不表示可直接互换。')
    finish('00-overall-supply-chain','总图 美国AI算力全产业链',ht)

# The reference directory is populated as part of the reproducible source bundle.
SOURCES = []
CATALOG = []

def table_page(title,subtitle,rows,num):
    header(num,title,subtitle)
    xpos=[48,231,652,1076,1392]
    labels=['模块','美国代表 / 美国业务主体','境外关键参与者 / 特别归属','向下游交付什么']
    y=185
    rect(48,y,1344,47,'ink',r=7)
    for i,s in enumerate(labels):text(xpos[i]+13,y+10,s,17.8,'white',BOLD)
    y+=47
    for row in rows:
        heights=[]
        for i,s in enumerate(row):heights.append(len(wrap(s,xpos[i+1]-xpos[i]-28,17))*24.3)
        rh=max(heights)+31
        if y+rh>1080:raise ValueError('Catalog too long '+title)
        rect(48,y,1344,rh,'white' if (rows.index(row)%2==0) else 'pale_gray',r=0)
        for i,s in enumerate(row):text(xpos[i]+13,y+14,s,17,'ink' if i==0 else 'muted',BOLD if i==0 else REG,xpos[i+1]-xpos[i]-28,24.3)
        y+=rh
    footer('各分图引用及来源目录','本目录列重要代表与分工，覆盖主要模块，不是全市场公司穷举、收入份额排名或特定产品的完整 BOM。')
    finish('appendix-'+num,title)

def references():
    np=(len(SOURCES)+8)//9
    counts=[len(SOURCES)//np+(i<len(SOURCES)%np) for i in range(np)]
    chunks=[];start=0
    for count in counts:chunks.append(SOURCES[start:start+count]);start+=count
    for i,items in enumerate(chunks):
        header('R'+str(i+1),'资料来源与证据边界',f'官方公告、公司产品文档、监管披露和原作者论文；检索截至 2026-10-18。来源目录 {i+1}/{len(chunks)}。')
        y=178
        for sid,title,url,claim in items:
            text(48,y,sid,17,'blue',BOLD)
            text(118,y,title,17.5,'ink',BOLD,width=1274)
            text(118,y+27,claim,15.4,'muted',width=1274)
            ls=wrap(url,1274,12.8)
            text(118,y+51,url,12.8,'blue',width=1274,leading=17)
            hh=max(91,75+17*(len(ls)-1))
            cv.linkURL(url,(118,current_h-y-hh+8,1392,current_h-y),relative=0,thickness=0)
            y+=hh
        if y>1110:raise ValueError('References overflow')
        footer('以上为可点击原始链接','公告中的合作和规划保留原有状态；公司级伙伴名单不自动等同于具体型号的实际采购或独家供货。')
        finish('references-'+str(i+1),'资料来源 '+str(i+1))

def main():
    global SOURCES, CATALOG
    data=json.loads((SRC/'reference_data.json').read_text())
    SOURCES=data['sources'];CATALOG=data['catalog']
    overview();foundation();dimm();hbm();gpu();tpu();custom_asic();server();cloud()
    for i,g in enumerate(CATALOG):table_page(g['title'],g['subtitle'],g['rows'],'A'+str(i+1))
    references();cv.save()
    doc=fitz.open(pdf_path)
    for i,meta in enumerate(page_meta[:9]):
        page=doc[i];scale=3840/page.rect.width
        pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
        png=DIAG/(meta['slug']+'.png')
        png_tmp=png.with_suffix('.tmp.png')
        png_tmp.write_bytes(pix.tobytes('png'))
        with Image.open(png_tmp) as exported: exported.verify()
        png_tmp.replace(png)
        svg=DIAG/(meta['slug']+'.svg');svg.write_text(page.get_svg_image(text_as_path=True))
        meta.update(png=str(png),svg=str(svg),pixel_width=pix.width,pixel_height=pix.height)
    # Review thumbnails for every page, not only the charts.
    review=ROOT/'tmp/review';review.mkdir(parents=True,exist_ok=True)
    for i,page in enumerate(doc):
        pix=page.get_pixmap(matrix=fitz.Matrix(1000/page.rect.width,1000/page.rect.width),alpha=False)
        pix.save(review/f'page-{i+1:02}.png')
    thumbs=[]
    for i in range(len(doc)):
        im=Image.open(review/f'page-{i+1:02}.png').convert('RGB')
        im.thumbnail((350,380))
        base=Image.new('RGB',(374,413),'#DCE2E9');base.paste(im,((374-im.width)//2,20))
        ImageDraw.Draw(base).text((10,391),f'PAGE {i+1:02}',fill='#15263C')
        thumbs.append(base)
    cw=374*3;ch=413*((len(thumbs)+2)//3)
    contact=Image.new('RGB',(cw,ch),'#DCE2E9')
    for i,im in enumerate(thumbs):contact.paste(im,((i%3)*374,(i//3)*413))
    contact.save(review/'contact-sheet.jpg',quality=90)
    (SRC/'manifest.json').write_text(json.dumps({'date':'2026-10-18','pages':page_meta,'sources':SOURCES},ensure_ascii=False,indent=2))
    # Programmatic bounds check supplements visual review.
    errors=[]
    for t in text_checks:
        ph=page_meta[t['page']-1]['height']
        if t['x']<0 or t['y']<0 or t['x']+t['w']>W+1 or t['y']+t['h']>ph+1:errors.append(t)
    (review/'layout-check.json').write_text(json.dumps({'pages':len(doc),'text_runs':len(text_checks),'out_of_bounds':errors},ensure_ascii=False,indent=2))
    if errors:raise ValueError(f'{len(errors)} out of bounds text runs')
    print(json.dumps({'pdf':str(pdf_path),'pages':len(doc),'diagram_images':[{'name':x['slug'],'width':x['pixel_width'],'height':x['pixel_height']} for x in page_meta[:9]],'review':str(review/'contact-sheet.jpg')},ensure_ascii=False))

if __name__=='__main__':main()
