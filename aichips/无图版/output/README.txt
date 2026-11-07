美国 AI 算力产业链：流程图与公司关系图册
资料截至：2026-10-18

文件内容
- output/美国AI算力产业链_流程图册_20261018.pdf：21 页矢量图册，含 9 张图、4 页公司目录和 8 页来源索引。
- output/diagrams/*.png：9 张独立高清图，宽度均为 3840 像素。
- output/diagrams/*.svg：9 张矢量图，可任意放大；文字已转为路径以保证跨设备显示。
- output/source/reference_data.json：公司角色与 67 项原始来源。
- output/source/manifest.json：图册页面与文件索引。
- output/source/build_atlas.py：图册生成脚本。

阅读顺序
00 总图 → 01 芯片底座 → 02 DDR5 内存条 → 03 HBM → 04 GPU/显卡 → 05 TPU → 06 其他定制 ASIC → 07 服务器 → 08 云与应用。
蓝/青实线表示器件工序及硬件交付；紫色实线表示算力/模型服务；灰色虚线表示工具、材料、设施或明确标注的技术支持关系。
同一节点内列出的是代表参与者，并不意味着所有公司互相供货、每家公司都参与每个型号，或所有产品可以互换。

范围
以美国设计、设备、系统和云公司为主线，同时列出不可忽略的全球制造、存储、材料和装配伙伴。
这是一份主要模块和代表公司的产业结构图，不是全市场公司穷举、收入排名或特定产品的完整物料清单。
历史产品结构例子和未来合作公告均在图中区分；具体参数不可跨代混用。

重新生成（可选）
Python 依赖：reportlab、PyMuPDF、Pillow。
需要另备 Noto Sans SC 的 Regular/Bold 静态 TTF 字体，放在解压根目录 tmp/fonts/NotoSansSC-Regular.ttf 与 tmp/fonts/NotoSansSC-Bold.ttf。
字体官方来源：https://github.com/google/fonts/tree/main/ofl/notosanssc
若使用可变字体，可用 fontTools 实例化为 400 与 650 字重；字体依其 SIL Open Font License 使用。
在解压根目录运行：python3 output/source/build_atlas.py
脚本会重建 output 下图册、PNG、SVG 与 tmp/review 下的审阅图。
